import json
from pathlib import Path

import pytest

from path_planning.algorithms import (
    AntColonyPlanner,
    AStarPlanner,
    DijkstraPlanner,
    GeneticPlanner,
)
from path_planning.benchmark import runner as benchmark_runner
from path_planning.benchmark.runner import run_benchmark
from path_planning.core.result import PlanningResult
from tests.integration.test_benchmark_runner import _write_benchmark_fixture


def _success_result(
    algorithm: str,
    start: tuple[int, int],
    seed: int | None,
    *,
    invalid: bool = False,
    path_length: float = 0.0,
) -> PlanningResult:
    path = ((1, 1),) if invalid else (start,)
    return PlanningResult(
        algorithm=algorithm,
        success=True,
        path=path,
        path_length=path_length,
        runtime_ms=0.1,
        expanded_nodes=1 if algorithm in {"dijkstra", "astar"} else None,
        evaluations=1 if algorithm in {"aco", "ga"} else None,
        iterations=1,
        convergence_history=(),
        seed=seed,
        failure_reason=None,
        metadata={},
    )


def test_runner_reuses_inputs_and_keeps_every_recorded_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_benchmark_fixture(
        tmp_path,
        warmup_runs=2,
        measurement_runs=3,
    )
    calls: list[tuple[str, int, tuple[int, int], tuple[int, int], int, int | None]] = []

    def fake_plan(algorithm: str):
        def plan(self, grid, start, goal, config, seed=None):
            del self
            calls.append((algorithm, id(grid), start, goal, id(config.movement), seed))
            if algorithm == "aco" and seed == 5:
                raise RuntimeError("planned failure")
            return _success_result(
                algorithm,
                start,
                seed,
                invalid=algorithm == "ga" and seed == 9,
            )

        return plan

    for planner_type, algorithm in (
        (DijkstraPlanner, "dijkstra"),
        (AStarPlanner, "astar"),
        (AntColonyPlanner, "aco"),
        (GeneticPlanner, "ga"),
    ):
        monkeypatch.setattr(planner_type, "plan", fake_plan(algorithm))

    output_dir = tmp_path / "output"
    artifacts = run_benchmark(config_path, output_dir)
    rows = json.loads((output_dir / artifacts.records_json).read_text())

    assert len(calls) == 14
    assert [call[0] for call in calls].count("dijkstra") == 5
    assert [call[0] for call in calls].count("astar") == 5
    assert [call[0] for call in calls].count("aco") == 2
    assert [call[0] for call in calls].count("ga") == 2
    assert len({call[1] for call in calls}) == 1
    assert len({call[2] for call in calls}) == 1
    assert len({call[3] for call in calls}) == 1
    assert len({call[4] for call in calls}) == 1

    assert len(rows) == 10
    assert [row["algorithm"] for row in rows].count("dijkstra") == 3
    assert [row["algorithm"] for row in rows].count("astar") == 3
    assert [row["seed"] for row in rows if row["algorithm"] == "aco"] == [5, 9]
    assert [row["seed"] for row in rows if row["algorithm"] == "ga"] == [5, 9]
    assert {row["map_name"] for row in rows} == {"same-map"}
    assert {(row["start_row"], row["start_column"]) for row in rows} == {(0, 0)}
    assert {(row["goal_row"], row["goal_column"]) for row in rows} == {(0, 0)}
    assert {row["connectivity"] for row in rows} == {4}

    failures = [row for row in rows if row["status"] == "failed"]
    assert [row["algorithm"] for row in failures] == ["aco", "ga"]
    assert failures[0]["error"] == "RuntimeError: planned failure"
    assert failures[0]["result_algorithm"] is None
    assert failures[0]["wall_runtime_ms"] >= 0
    assert failures[0]["runtime_ms"] is None
    assert failures[1]["error"] == "path_validation_failed: wrong_start"
    assert failures[1]["success"] is True
    assert json.loads(failures[1]["path_json"]) == [[1, 1]]


def test_warmup_planner_exception_propagates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_benchmark_fixture(tmp_path, warmup_runs=1)
    (tmp_path / "configs" / "astar_benchmark.yaml").write_text(
        "movement: {}\nheuristic: manhattan\n",
        encoding="utf-8",
    )

    def fail_warmup(self, grid, start, goal, config, seed=None):
        del self, grid, start, goal, config, seed
        raise RuntimeError("warmup failed")

    monkeypatch.setattr(DijkstraPlanner, "plan", fail_warmup)

    with pytest.raises(RuntimeError, match="warmup failed"):
        run_benchmark(config_path, tmp_path / "output")


def test_unsuccessful_warmup_with_matching_seed_does_not_abort_formal_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_benchmark_fixture(
        tmp_path,
        warmup_runs=1,
        measurement_runs=1,
        seeds=(11,),
    )

    def no_path(self, grid, start, goal, config, seed=None):
        del self, grid, start, goal, config
        return PlanningResult(
            algorithm="dijkstra",
            success=False,
            path=(),
            path_length=None,
            runtime_ms=0.1,
            expanded_nodes=1,
            evaluations=None,
            iterations=0,
            convergence_history=(),
            seed=seed,
            failure_reason="no_path",
            metadata={},
        )

    monkeypatch.setattr(DijkstraPlanner, "plan", no_path)
    output_dir = tmp_path / "output"

    artifacts = run_benchmark(config_path, output_dir)

    rows = json.loads((output_dir / artifacts.records_json).read_text())
    dijkstra = next(row for row in rows if row["algorithm"] == "dijkstra")
    assert dijkstra["status"] == "failed"
    assert dijkstra["error"] == "no_path"


def test_shared_validator_exception_propagates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_benchmark_fixture(tmp_path, warmup_runs=0)
    (tmp_path / "configs" / "astar_benchmark.yaml").write_text(
        "movement: {}\nheuristic: manhattan\n",
        encoding="utf-8",
    )

    def fail_validation(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("validator failed")

    monkeypatch.setattr(benchmark_runner, "validate_path", fail_validation)

    with pytest.raises(RuntimeError, match="validator failed"):
        run_benchmark(config_path, tmp_path / "output")


def test_self_reported_path_length_mismatch_is_retained_as_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_benchmark_fixture(
        tmp_path,
        warmup_runs=0,
        measurement_runs=1,
        seeds=(11,),
    )

    def wrong_cost(self, grid, start, goal, config, seed=None):
        del self, grid, goal, config
        return _success_result("dijkstra", start, seed, path_length=999.0)

    monkeypatch.setattr(DijkstraPlanner, "plan", wrong_cost)
    output_dir = tmp_path / "output"

    artifacts = run_benchmark(config_path, output_dir)

    rows = json.loads((output_dir / artifacts.records_json).read_text())
    dijkstra = next(row for row in rows if row["algorithm"] == "dijkstra")
    assert dijkstra["status"] == "failed"
    assert dijkstra["error"] == "path_validation_failed: path_length_mismatch"
    assert dijkstra["path_length"] == 999.0
    summary = json.loads((output_dir / artifacts.summary_json).read_text())
    dijkstra_summary = next(row for row in summary if row["algorithm"] == "dijkstra")
    assert dijkstra_summary["success_count"] == 0
    assert dijkstra_summary["path_length_mean"] is None


def test_stochastic_result_seed_mismatch_is_not_attributed_to_requested_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_benchmark_fixture(
        tmp_path,
        warmup_runs=0,
        measurement_runs=1,
        seeds=(11,),
    )

    def wrong_seed(self, grid, start, goal, config, seed=None):
        del self, grid, goal, config, seed
        return _success_result("aco", start, 29)

    monkeypatch.setattr(AntColonyPlanner, "plan", wrong_seed)
    output_dir = tmp_path / "output"

    artifacts = run_benchmark(config_path, output_dir)

    rows = json.loads((output_dir / artifacts.records_json).read_text())
    aco = next(row for row in rows if row["algorithm"] == "aco")
    assert aco["seed"] == 11
    assert aco["result_seed"] == 29
    assert aco["status"] == "failed"
    assert aco["error"] == "result_protocol_failed: seed_mismatch"
    extrema = json.loads((output_dir / artifacts.best_worst_json).read_text())
    aco_extrema = next(row for row in extrema["cohorts"] if row["algorithm"] == "aco")
    assert aco_extrema["best"] is None
    assert aco_extrema["worst"] is None


def test_deterministic_formal_result_must_keep_requested_null_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_benchmark_fixture(
        tmp_path,
        warmup_runs=0,
        measurement_runs=1,
        seeds=(11,),
    )

    def wrong_seed(self, grid, start, goal, config, seed=None):
        del self, grid, goal, config, seed
        return _success_result("dijkstra", start, 29)

    monkeypatch.setattr(DijkstraPlanner, "plan", wrong_seed)
    output_dir = tmp_path / "output"

    artifacts = run_benchmark(config_path, output_dir)

    rows = json.loads((output_dir / artifacts.records_json).read_text())
    dijkstra = next(row for row in rows if row["algorithm"] == "dijkstra")
    assert dijkstra["seed"] is None
    assert dijkstra["result_seed"] == 29
    assert dijkstra["status"] == "failed"
    assert dijkstra["error"] == "result_protocol_failed: seed_mismatch"


def test_warmup_result_seed_mismatch_propagates_before_raw_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_benchmark_fixture(
        tmp_path,
        warmup_runs=1,
        measurement_runs=1,
        seeds=(11,),
    )

    def wrong_seed(self, grid, start, goal, config, seed=None):
        del self, grid, goal, config, seed
        return _success_result("dijkstra", start, 29)

    monkeypatch.setattr(DijkstraPlanner, "plan", wrong_seed)
    output_dir = tmp_path / "output"

    with pytest.raises(RuntimeError, match="warmup.*seed_mismatch"):
        run_benchmark(config_path, output_dir)

    assert not output_dir.joinpath("raw_runs.json").exists()
