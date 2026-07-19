import csv
import hashlib
import importlib.metadata
import json
import re
import subprocess
import tomllib
from dataclasses import fields
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from path_planning.algorithms import AntColonyPlanner, DijkstraPlanner
from path_planning.benchmark import metadata as benchmark_metadata
from path_planning.benchmark.runner import run_benchmark
from path_planning.benchmark.schemas import BenchmarkRunRecord
from tests.integration.test_benchmark_runner import _write_benchmark_fixture

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_FIELDS = tuple(field.name for field in fields(BenchmarkRunRecord))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def test_run_benchmark_persists_matching_raw_rows_and_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_benchmark_fixture(tmp_path)
    original_plan = AntColonyPlanner.plan

    def fail_one_seed(self, grid, start, goal, config, seed=None):
        if seed == 5:
            raise RuntimeError("retained failure")
        return original_plan(self, grid, start, goal, config, seed)

    monkeypatch.setattr(AntColonyPlanner, "plan", fail_one_seed)
    output_dir = tmp_path / "output"

    artifacts = run_benchmark(config_path, output_dir)

    assert artifacts.to_dict() == {
        "records_csv": "raw_runs.csv",
        "records_json": "raw_runs.json",
        "metadata_json": "run_metadata.json",
        "summary_csv": "summary.csv",
        "summary_json": "summary.json",
        "best_worst_json": "best_worst.json",
        "manifest_json": "manifest.json",
        "figures": [],
    }
    assert {path.name for path in output_dir.iterdir()} == {
        "raw_runs.csv",
        "raw_runs.json",
        "run_metadata.json",
        "summary.csv",
        "summary.json",
        "best_worst.json",
        "manifest.json",
    }

    json_rows = json.loads((output_dir / "raw_runs.json").read_text())
    assert len(RAW_FIELDS) == 27
    with (output_dir / "raw_runs.csv").open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        csv_rows = list(reader)
        assert tuple(reader.fieldnames or ()) == RAW_FIELDS

    assert len(csv_rows) == len(json_rows) == 8
    assert all(tuple(row) == RAW_FIELDS for row in json_rows)
    assert all(
        not isinstance(value, (list, dict))
        for row in json_rows
        for value in row.values()
    )
    for csv_row, json_row in zip(csv_rows, json_rows, strict=True):
        assert {
            field: "" if value is None else str(value)
            for field, value in json_row.items()
        } == csv_row

    failure = next(
        row for row in json_rows if row["error"] == "RuntimeError: retained failure"
    )
    assert failure["status"] == "failed"
    assert failure["seed"] == 5
    assert failure["wall_runtime_ms"] >= 0
    assert all(
        failure[field] is None
        for field in RAW_FIELDS
        if field.startswith("result_")
        or field
        in {
            "success",
            "path_json",
            "path_length",
            "runtime_ms",
            "expanded_nodes",
            "evaluations",
            "iterations",
            "convergence_history_json",
            "failure_reason",
        }
    )
    success = next(row for row in json_rows if row["status"] == "success")
    assert isinstance(json.loads(success["path_json"]), list)
    assert isinstance(json.loads(success["convergence_history_json"]), list)
    assert isinstance(json.loads(success["result_metadata_json"]), dict)

    summary_rows = json.loads((output_dir / "summary.json").read_text())
    with (output_dir / "summary.csv").open(newline="", encoding="utf-8") as stream:
        summary_csv_rows = list(csv.DictReader(stream))
    assert len(summary_csv_rows) == len(summary_rows) == 4
    for csv_row, json_row in zip(summary_csv_rows, summary_rows, strict=True):
        assert {
            field: "" if value is None else str(value)
            for field, value in json_row.items()
        } == csv_row
    aco_summary = next(row for row in summary_rows if row["algorithm"] == "aco")
    assert aco_summary["run_count"] == 2
    assert aco_summary["success_count"] == 1
    assert aco_summary["success_rate"] == 0.5

    extrema = json.loads((output_dir / "best_worst.json").read_text())
    aco_extrema = next(row for row in extrema["cohorts"] if row["algorithm"] == "aco")
    assert aco_extrema["best"]["seed"] == 9
    assert aco_extrema["worst"]["seed"] == 9


def test_run_benchmark_records_environment_metadata_and_verifiable_manifest(
    tmp_path: Path,
) -> None:
    config_path = _write_benchmark_fixture(tmp_path)
    output_dir = tmp_path / "output"
    before = datetime.now().astimezone().astimezone(tz=None)

    run_benchmark(config_path, output_dir)

    metadata = json.loads((output_dir / "run_metadata.json").read_text())
    assert set(metadata) == {
        "schema_version",
        "run_id",
        "config_sha256",
        "git_commit",
        "git_dirty",
        "python_version",
        "platform",
        "direct_dependencies",
        "resolved_dependencies",
        "requirements_lock_sha256",
        "source_snapshot",
        "executed_at_utc",
    }
    assert metadata["schema_version"] == 1
    assert re.fullmatch(r"[0-9a-f]{32}", metadata["run_id"])
    assert metadata["config_sha256"] == _sha256(config_path)
    assert (
        metadata["git_commit"]
        == subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    executed_at = datetime.fromisoformat(metadata["executed_at_utc"])
    assert executed_at.utcoffset() == timedelta(0)
    assert executed_at >= before.astimezone(executed_at.tzinfo)
    assert metadata["python_version"]
    assert metadata["platform"]
    assert metadata["git_dirty"] == bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )

    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    direct_names = {
        _normalized_name(dependency)
        for dependency in project["project"]["dependencies"]
    }
    assert metadata["direct_dependencies"] == {
        name: importlib.metadata.version(name) for name in sorted(direct_names)
    }
    locked = {
        _normalized_name(name): version
        for line in (PROJECT_ROOT / "requirements.lock").read_text().splitlines()
        if line and not line.startswith("#")
        for name, version in [line.split("==", maxsplit=1)]
    }
    assert metadata["resolved_dependencies"] == {
        name: {
            "locked": locked[name],
            "installed": importlib.metadata.version(name),
        }
        for name in sorted(locked)
    }
    assert metadata["requirements_lock_sha256"] == _sha256(
        PROJECT_ROOT / "requirements.lock"
    )

    snapshot_files = {
        path.relative_to(PROJECT_ROOT).as_posix(): _sha256(path)
        for pattern in (
            "src/path_planning/**/*.py",
            "configs/**/*.yaml",
            "maps/**/*.json",
            "pyproject.toml",
            "requirements.lock",
        )
        for path in PROJECT_ROOT.glob(pattern)
        if path.is_file()
    }
    snapshot = metadata["source_snapshot"]
    assert snapshot["files"] == dict(sorted(snapshot_files.items()))
    canonical_snapshot = json.dumps(
        snapshot["files"],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    assert snapshot["sha256"] == hashlib.sha256(canonical_snapshot).hexdigest()
    assert not any(Path(path).is_absolute() for path in snapshot["files"])

    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert manifest == {
        "schema_version": 1,
        "run_id": metadata["run_id"],
        "config_sha256": metadata["config_sha256"],
        "files": {
            filename: _sha256(output_dir / filename)
            for filename in (
                "raw_runs.csv",
                "raw_runs.json",
                "run_metadata.json",
                "summary.csv",
                "summary.json",
                "best_worst.json",
            )
        },
    }
    assert "manifest.json" not in manifest["files"]
    assert not any(
        Path(value).is_absolute()
        for value in metadata.values()
        if isinstance(value, str)
    )


def test_run_benchmark_never_overwrites_a_completed_run(tmp_path: Path) -> None:
    config_path = _write_benchmark_fixture(tmp_path)
    output_dir = tmp_path / "output"
    run_benchmark(config_path, output_dir)
    hashes_before = {path.name: _sha256(path) for path in output_dir.iterdir()}

    with pytest.raises(FileExistsError, match="output directory already exists"):
        run_benchmark(tmp_path / "missing.yaml", output_dir)

    assert {path.name: _sha256(path) for path in output_dir.iterdir()} == hashes_before


def test_dependency_mismatch_fails_before_output_or_planner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_benchmark_fixture(tmp_path)
    planner_called = False
    installed_version = importlib.metadata.version

    def mismatched_version(name: str) -> str:
        if _normalized_name(name) == "numpy":
            return "0.0.0-mismatch"
        return installed_version(name)

    def track_planner(*args, **kwargs):
        nonlocal planner_called
        planner_called = True
        raise AssertionError("planner must not run")

    monkeypatch.setattr(importlib.metadata, "version", mismatched_version)
    monkeypatch.setattr(DijkstraPlanner, "plan", track_planner)
    output_dir = tmp_path / "output"

    with pytest.raises(RuntimeError, match="dependency version mismatch.*numpy"):
        run_benchmark(config_path, output_dir)

    assert not planner_called
    assert not output_dir.exists()


def test_config_hash_uses_bytes_parsed_before_planner_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_benchmark_fixture(tmp_path, warmup_runs=0)
    original_bytes = config_path.read_bytes()
    original_plan = DijkstraPlanner.plan
    mutated = False

    def mutate_config(self, grid, start, goal, config, seed=None):
        nonlocal mutated
        if not mutated:
            config_path.write_bytes(original_bytes + b"\n# changed during run\n")
            mutated = True
        return original_plan(self, grid, start, goal, config, seed)

    monkeypatch.setattr(DijkstraPlanner, "plan", mutate_config)
    output_dir = tmp_path / "output"

    run_benchmark(config_path, output_dir)

    metadata = json.loads((output_dir / "run_metadata.json").read_text())
    manifest = json.loads((output_dir / "manifest.json").read_text())
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    assert mutated
    assert hashlib.sha256(config_path.read_bytes()).hexdigest() != original_hash
    assert metadata["config_sha256"] == original_hash
    assert manifest["config_sha256"] == original_hash


def test_source_snapshot_uses_supplied_config_bytes_without_rereading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "configs" / "benchmark.yaml"
    config_path.parent.mkdir()
    config_path.write_bytes(b"changed bytes must not be read")
    original_read_bytes = Path.read_bytes

    def reject_config_reread(path: Path) -> bytes:
        if path == config_path:
            raise AssertionError("benchmark config was reread")
        return original_read_bytes(path)

    monkeypatch.setattr(benchmark_metadata, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        benchmark_metadata,
        "_SOURCE_PATTERNS",
        ("configs/**/*.yaml",),
    )
    monkeypatch.setattr(Path, "read_bytes", reject_config_reread)

    snapshot = benchmark_metadata._source_snapshot(
        {"configs/benchmark.yaml": b"original parsed bytes"}
    )

    assert snapshot["files"] == {
        "configs/benchmark.yaml": hashlib.sha256(b"original parsed bytes").hexdigest()
    }


def test_collect_metadata_snapshots_project_relative_config_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "configs" / "benchmark.yaml"
    config_path.parent.mkdir()
    config_path.write_bytes(b"bytes currently on disk")
    (tmp_path / "requirements.lock").write_bytes(b"package==1.0\n")
    captured: dict[str, bytes] = {}

    def capture_snapshot(overrides):
        captured.update(overrides)
        return {"files": {}, "sha256": "0" * 64}

    monkeypatch.setattr(benchmark_metadata, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(benchmark_metadata, "_git_commit", lambda: "commit")
    monkeypatch.setattr(benchmark_metadata, "_git_dirty", lambda: True)
    monkeypatch.setattr(benchmark_metadata, "_direct_dependencies", dict)
    monkeypatch.setattr(
        benchmark_metadata,
        "_resolved_dependencies",
        lambda lock_bytes: {},
    )
    monkeypatch.setattr(benchmark_metadata, "_source_snapshot", capture_snapshot)

    metadata = benchmark_metadata.collect_run_metadata(
        b"original parsed bytes",
        config_path,
    )

    assert (
        metadata["config_sha256"]
        == hashlib.sha256(b"original parsed bytes").hexdigest()
    )
    assert captured == {
        "requirements.lock": b"package==1.0\n",
        "configs/benchmark.yaml": b"original parsed bytes",
    }


def test_metadata_validation_helpers_reject_malformed_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\ndependencies = 'not-a-list'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(benchmark_metadata, "_PROJECT_ROOT", tmp_path)

    with pytest.raises(ValueError, match="dependencies must be a list"):
        benchmark_metadata._direct_dependencies()
    with pytest.raises(ValueError, match="pin exact versions"):
        benchmark_metadata._resolved_dependencies(b"\n# comment\nmalformed\n")
    with pytest.raises(ValueError, match="invalid project dependency"):
        benchmark_metadata._dependency_name("!invalid")
    with pytest.raises(ValueError, match="string-keyed mapping"):
        benchmark_metadata._mapping([], "field")


def test_missing_dependency_is_reported_as_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_version(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing_version)

    with pytest.raises(RuntimeError, match="dependency is not installed"):
        benchmark_metadata._installed_version("missing-package")
