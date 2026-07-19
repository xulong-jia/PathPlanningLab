import json
from copy import deepcopy
from dataclasses import fields
from pathlib import Path

import pytest
import yaml

from path_planning.benchmark.schemas import (
    BenchmarkArtifacts,
    BenchmarkConfig,
    BenchmarkRunRecord,
    BenchmarkTask,
    load_benchmark_config,
    parse_benchmark_config,
)
from path_planning.core.movement import MovementConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SMOKE_CONFIG = PROJECT_ROOT / "configs" / "benchmark_smoke.yaml"
STANDARD_CONFIG = PROJECT_ROOT / "configs" / "benchmark_standard.yaml"


def _valid_config_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "valid",
        "algorithm_configs": {
            "dijkstra": "configs/dijkstra.yaml",
            "astar": "configs/astar_benchmark.yaml",
            "aco": "configs/aco_baseline.yaml",
            "ga": "configs/ga_baseline.yaml",
        },
        "deterministic": {"warmup_runs": 0, "measurement_runs": 1},
        "stochastic": {"seeds": [11]},
        "tasks": [
            {
                "map": "maps/handcrafted/open_20.json",
                "movement": {
                    "connectivity": 4,
                    "diagonal_cost": 2**0.5,
                    "allow_corner_cutting": False,
                },
            }
        ],
    }


def _valid_run_record_values() -> dict[str, object]:
    return {
        "algorithm": "dijkstra",
        "map_name": "open_20",
        "map_path": "maps/handcrafted/open_20.json",
        "start_row": 0,
        "start_column": 0,
        "goal_row": 19,
        "goal_column": 19,
        "connectivity": 4,
        "diagonal_cost": 2**0.5,
        "allow_corner_cutting": False,
        "config_name": "configs/dijkstra.yaml",
        "seed": None,
        "status": "success",
        "error": None,
        "wall_runtime_ms": 1.6,
        "result_algorithm": "dijkstra",
        "success": True,
        "path_json": "[[0,0],[19,19]]",
        "path_length": 2**0.5 * 19,
        "runtime_ms": 1.5,
        "expanded_nodes": 400,
        "evaluations": None,
        "iterations": 0,
        "convergence_history_json": "[]",
        "result_seed": None,
        "failure_reason": None,
        "result_metadata_json": "{}",
    }


def _run_record(**overrides: object) -> BenchmarkRunRecord:
    values = _valid_run_record_values()
    values.update(overrides)
    return BenchmarkRunRecord(**values)  # type: ignore[arg-type]


def test_benchmark_schema_fields_are_serializable_and_complete() -> None:
    assert {field.name for field in fields(BenchmarkConfig)} == {
        "name",
        "tasks",
        "algorithm_configs",
        "deterministic_warmup_runs",
        "deterministic_measurement_runs",
        "stochastic_seeds",
    }
    assert {field.name for field in fields(BenchmarkRunRecord)} == {
        "algorithm",
        "map_name",
        "map_path",
        "start_row",
        "start_column",
        "goal_row",
        "goal_column",
        "connectivity",
        "diagonal_cost",
        "allow_corner_cutting",
        "config_name",
        "seed",
        "status",
        "error",
        "wall_runtime_ms",
        "result_algorithm",
        "success",
        "path_json",
        "path_length",
        "runtime_ms",
        "expanded_nodes",
        "evaluations",
        "iterations",
        "convergence_history_json",
        "result_seed",
        "failure_reason",
        "result_metadata_json",
    }
    assert {field.name for field in fields(BenchmarkArtifacts)} == {
        "records_csv",
        "records_json",
        "metadata_json",
        "summary_csv",
        "summary_json",
        "best_worst_json",
        "manifest_json",
        "figures",
    }

    record = BenchmarkRunRecord(
        algorithm="dijkstra",
        map_name="open_20",
        map_path="maps/handcrafted/open_20.json",
        start_row=0,
        start_column=0,
        goal_row=19,
        goal_column=19,
        connectivity=4,
        diagonal_cost=2**0.5,
        allow_corner_cutting=False,
        config_name="configs/dijkstra.yaml",
        seed=None,
        status="success",
        error=None,
        wall_runtime_ms=1.6,
        result_algorithm="dijkstra",
        success=True,
        path_json="[[0,0],[19,19]]",
        path_length=2**0.5 * 19,
        runtime_ms=1.5,
        expanded_nodes=400,
        evaluations=None,
        iterations=0,
        convergence_history_json="[]",
        result_seed=None,
        failure_reason=None,
        result_metadata_json="{}",
    )

    assert json.loads(record.to_json()) == {
        "algorithm": "dijkstra",
        "map_name": "open_20",
        "map_path": "maps/handcrafted/open_20.json",
        "start_row": 0,
        "start_column": 0,
        "goal_row": 19,
        "goal_column": 19,
        "connectivity": 4,
        "diagonal_cost": pytest.approx(2**0.5),
        "allow_corner_cutting": False,
        "config_name": "configs/dijkstra.yaml",
        "seed": None,
        "status": "success",
        "error": None,
        "wall_runtime_ms": 1.6,
        "result_algorithm": "dijkstra",
        "success": True,
        "path_json": "[[0,0],[19,19]]",
        "path_length": pytest.approx(2**0.5 * 19),
        "runtime_ms": 1.5,
        "expanded_nodes": 400,
        "evaluations": None,
        "iterations": 0,
        "convergence_history_json": "[]",
        "result_seed": None,
        "failure_reason": None,
        "result_metadata_json": "{}",
    }


def test_benchmark_task_rejects_an_absolute_map_path() -> None:
    with pytest.raises(ValueError, match="relative"):
        BenchmarkTask(Path("/outside/map.json"), MovementConfig(4))


@pytest.mark.parametrize(
    "field",
    [
        "records_csv",
        "records_json",
        "metadata_json",
        "summary_csv",
        "summary_json",
        "best_worst_json",
        "manifest_json",
    ],
)
def test_benchmark_artifacts_reject_absolute_artifact_paths(field: str) -> None:
    paths: dict[str, object] = {
        "records_csv": Path("records.csv"),
        "records_json": Path("records.json"),
        "metadata_json": Path("metadata.json"),
        "summary_csv": Path("summary.csv"),
        "summary_json": Path("summary.json"),
        "best_worst_json": Path("best_worst.json"),
        "manifest_json": Path("manifest.json"),
        "figures": (),
    }
    paths[field] = Path("/outside/artifact")

    with pytest.raises(ValueError, match="relative"):
        BenchmarkArtifacts(**paths)  # type: ignore[arg-type]


def test_benchmark_artifacts_reject_absolute_figure_paths() -> None:
    with pytest.raises(ValueError, match="relative"):
        BenchmarkArtifacts(
            records_csv=Path("records.csv"),
            records_json=Path("records.json"),
            metadata_json=Path("metadata.json"),
            summary_csv=Path("summary.csv"),
            summary_json=Path("summary.json"),
            best_worst_json=Path("best_worst.json"),
            manifest_json=Path("manifest.json"),
            figures=(Path("/outside/figure.png"),),
        )


def test_benchmark_artifacts_serialize_uncreated_paths_as_null() -> None:
    artifacts = BenchmarkArtifacts(
        records_csv=None,
        records_json=Path("raw_runs.json"),
        metadata_json=None,
        summary_csv=None,
        summary_json=None,
        best_worst_json=None,
        manifest_json=None,
    )

    assert artifacts.to_dict() == {
        "records_csv": None,
        "records_json": "raw_runs.json",
        "metadata_json": None,
        "summary_csv": None,
        "summary_json": None,
        "best_worst_json": None,
        "manifest_json": None,
        "figures": [],
    }


def test_run_record_serializes_exception_with_null_result_fields() -> None:
    record = BenchmarkRunRecord(
        algorithm="aco",
        map_name="open_20",
        map_path="maps/handcrafted/open_20.json",
        start_row=0,
        start_column=0,
        goal_row=19,
        goal_column=19,
        connectivity=4,
        diagonal_cost=2**0.5,
        allow_corner_cutting=False,
        config_name="configs/aco_baseline.yaml",
        seed=11,
        status="failed",
        error="RuntimeError: failed",
        wall_runtime_ms=0.5,
        result_algorithm=None,
        success=None,
        path_json=None,
        path_length=None,
        runtime_ms=None,
        expanded_nodes=None,
        evaluations=None,
        iterations=None,
        convergence_history_json=None,
        result_seed=None,
        failure_reason=None,
        result_metadata_json=None,
    )

    payload = json.loads(record.to_json())
    assert tuple(payload) == tuple(field.name for field in fields(BenchmarkRunRecord))
    assert payload["wall_runtime_ms"] == 0.5
    assert all(
        payload[name] is None
        for name in (
            "result_algorithm",
            "success",
            "path_json",
            "path_length",
            "runtime_ms",
            "expanded_nodes",
            "evaluations",
            "iterations",
            "convergence_history_json",
            "result_seed",
            "failure_reason",
            "result_metadata_json",
        )
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "schema_version": 1,
            "name": "invalid",
            "algorithm_configs": {},
            "deterministic": {"warmup_runs": 0, "measurement_runs": 1},
            "stochastic": {"seeds": [11]},
            "tasks": [],
        },
        {
            "schema_version": 1,
            "name": "invalid",
            "algorithm_configs": {
                "dijkstra": "configs/dijkstra.yaml",
                "astar": "configs/astar.yaml",
                "aco": "configs/aco_baseline.yaml",
                "ga": "configs/ga_baseline.yaml",
            },
            "deterministic": {"warmup_runs": 0, "measurement_runs": 1},
            "stochastic": {"seeds": [11, 11]},
            "tasks": [
                {
                    "map": "maps/handcrafted/open_20.json",
                    "movement": {
                        "connectivity": 4,
                        "diagonal_cost": 2**0.5,
                        "allow_corner_cutting": False,
                    },
                }
            ],
        },
        {
            "schema_version": True,
            "name": "invalid",
            "algorithm_configs": {
                "dijkstra": "configs/dijkstra.yaml",
                "astar": "configs/astar.yaml",
                "aco": "configs/aco_baseline.yaml",
                "ga": "configs/ga_baseline.yaml",
            },
            "deterministic": {"warmup_runs": 0, "measurement_runs": 1},
            "stochastic": {"seeds": [11]},
            "tasks": [
                {
                    "map": "maps/handcrafted/open_20.json",
                    "movement": {
                        "connectivity": 4,
                        "diagonal_cost": 2**0.5,
                        "allow_corner_cutting": False,
                    },
                }
            ],
        },
    ],
)
def test_load_benchmark_config_rejects_invalid_config(
    tmp_path: Path,
    payload: object,
) -> None:
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        load_benchmark_config(config_path)


def test_smoke_config_expands_three_four_way_tasks_with_three_random_seeds() -> None:
    config = load_benchmark_config(SMOKE_CONFIG)

    assert config.name == "smoke"
    assert [task.map_path.name for task in config.tasks] == [
        "open_20.json",
        "maze_30.json",
        "no_path_20.json",
    ]
    assert {task.movement.connectivity for task in config.tasks} == {4}
    assert config.deterministic_warmup_runs == 0
    assert config.deterministic_measurement_runs == 1
    assert config.stochastic_seeds == (11, 29, 47)


def test_standard_config_expands_twenty_one_tasks_and_twenty_random_seeds() -> None:
    config = load_benchmark_config(STANDARD_CONFIG)

    assert len(config.tasks) == 21
    assert sum(task.movement.connectivity == 4 for task in config.tasks) == 15
    assert sum(task.movement.connectivity == 8 for task in config.tasks) == 6
    assert config.deterministic_warmup_runs == 3
    assert config.deterministic_measurement_runs == 10
    assert len(config.stochastic_seeds) == 20
    assert len(set(config.stochastic_seeds)) == 20


def test_benchmark_configs_name_each_algorithm_configuration() -> None:
    smoke_expected = {
        "dijkstra": "configs/dijkstra.yaml",
        "astar": "configs/astar_benchmark.yaml",
        "aco": "configs/aco_smoke.yaml",
        "ga": "configs/ga_smoke.yaml",
    }
    standard_expected = {
        "dijkstra": "configs/dijkstra.yaml",
        "astar": "configs/astar_benchmark.yaml",
        "aco": "configs/aco_baseline.yaml",
        "ga": "configs/ga_baseline.yaml",
    }

    assert dict(load_benchmark_config(SMOKE_CONFIG).algorithm_configs) == smoke_expected
    assert dict(load_benchmark_config(STANDARD_CONFIG).algorithm_configs) == (
        standard_expected
    )

    astar_config = PROJECT_ROOT / smoke_expected["astar"]
    assert astar_config.read_text(encoding="utf-8") == "heuristic: auto\n"


@pytest.mark.parametrize(
    ("smoke_name", "baseline_name", "budget_fields"),
    [
        (
            "aco_smoke.yaml",
            "aco_baseline.yaml",
            {
                "ants",
                "iterations",
                "max_steps",
                "max_restarts",
                "max_backtracks",
                "stagnation_iterations",
            },
        ),
        (
            "ga_smoke.yaml",
            "ga_baseline.yaml",
            {
                "population_size",
                "generations",
                "max_initialization_steps",
                "initialization_attempts",
                "stagnation_generations",
            },
        ),
    ],
)
def test_smoke_algorithm_configs_only_reduce_explicit_execution_budgets(
    smoke_name: str,
    baseline_name: str,
    budget_fields: set[str],
) -> None:
    smoke = yaml.safe_load((PROJECT_ROOT / "configs" / smoke_name).read_text())
    baseline = yaml.safe_load((PROJECT_ROOT / "configs" / baseline_name).read_text())

    assert set(smoke) == set(baseline)
    assert all(smoke[field] < baseline[field] for field in budget_fields)
    assert {
        field: value for field, value in smoke.items() if field not in budget_fields
    } == {
        field: value for field, value in baseline.items() if field not in budget_fields
    }


def test_benchmark_config_and_task_serialize_the_valid_public_contract() -> None:
    config = parse_benchmark_config(json.dumps(_valid_config_payload()).encode())

    assert config.to_dict() == _valid_config_payload()


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": " "},
        {"tasks": ()},
        {
            "algorithm_configs": (
                ("dijkstra", "configs/dijkstra.yaml"),
                ("astar", "configs/astar_benchmark.yaml"),
                ("aco", "configs/aco_baseline.yaml"),
            )
        },
        {
            "algorithm_configs": (
                ("dijkstra", "configs/dijkstra.yaml"),
                ("astar", "configs/astar_benchmark.yaml"),
                ("aco", "configs/aco_baseline.yaml"),
                ("ga", "configs/ga_baseline.yaml"),
                ("dijkstra", "configs/dijkstra.yaml"),
            )
        },
        {
            "algorithm_configs": (
                ("dijkstra", "/absolute/dijkstra.yaml"),
                ("astar", "configs/astar_benchmark.yaml"),
                ("aco", "configs/aco_baseline.yaml"),
                ("ga", "configs/ga_baseline.yaml"),
            )
        },
        {"deterministic_warmup_runs": -1},
        {"deterministic_measurement_runs": 0},
        {"stochastic_seeds": ()},
        {"stochastic_seeds": (-1,)},
    ],
)
def test_direct_benchmark_config_rejects_invalid_invariants(
    overrides: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "name": "valid",
        "tasks": (BenchmarkTask(Path("map.json"), MovementConfig(4)),),
        "algorithm_configs": (
            ("dijkstra", "configs/dijkstra.yaml"),
            ("astar", "configs/astar_benchmark.yaml"),
            ("aco", "configs/aco_baseline.yaml"),
            ("ga", "configs/ga_baseline.yaml"),
        ),
        "deterministic_warmup_runs": 0,
        "deterministic_measurement_runs": 1,
        "stochastic_seeds": (11,),
    }
    values.update(overrides)

    with pytest.raises(ValueError):
        BenchmarkConfig(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"algorithm": " "},
        {"config_name": "/absolute/config.yaml"},
        {"start_row": -1},
        {"connectivity": 6},
        {"diagonal_cost": True},
        {"diagonal_cost": 0.0},
        {"allow_corner_cutting": 0},
        {"status": "unknown"},
        {"error": "unexpected"},
        {"status": "failed", "error": None},
        {"result_algorithm": None},
        {"result_algorithm": " "},
        {"result_algorithm": "astar"},
        {"success": None},
        {"path_json": None},
        {"wall_runtime_ms": None},
        {"wall_runtime_ms": "slow"},
        {"wall_runtime_ms": -1.0},
        {"expanded_nodes": -1},
    ],
)
def test_run_record_rejects_invalid_field_combinations(
    overrides: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        _run_record(**overrides)


def test_run_record_allows_null_optional_path_cost_for_a_failed_result() -> None:
    record = _run_record(
        status="failed",
        error="no_path",
        success=False,
        path_json="[]",
        path_length=None,
        failure_reason="no_path",
    )

    assert record.path_length is None


def test_success_record_rejects_a_completely_null_result_payload() -> None:
    values = _valid_run_record_values()
    values.update(
        {
            "status": "success",
            "error": None,
            "result_algorithm": None,
            "success": None,
            "path_json": None,
            "path_length": None,
            "runtime_ms": None,
            "expanded_nodes": None,
            "evaluations": None,
            "iterations": None,
            "convergence_history_json": None,
            "result_seed": None,
            "failure_reason": None,
            "result_metadata_json": None,
        }
    )

    with pytest.raises(ValueError, match="successful records require a result"):
        BenchmarkRunRecord(**values)  # type: ignore[arg-type]


def test_success_status_requires_a_successful_planning_result() -> None:
    with pytest.raises(
        ValueError,
        match="successful record requires a successful result",
    ):
        _run_record(
            success=False,
            path_json="[]",
            path_length=None,
            failure_reason="no_path",
        )


def test_parser_rejects_each_nested_schema_boundary() -> None:
    invalid_payloads: list[dict[str, object]] = []

    deterministic = deepcopy(_valid_config_payload())
    deterministic["deterministic"] = {"warmup_runs": 0}
    invalid_payloads.append(deterministic)

    stochastic = deepcopy(_valid_config_payload())
    stochastic["stochastic"] = {"seeds": [11], "unexpected": True}
    invalid_payloads.append(stochastic)

    tasks = deepcopy(_valid_config_payload())
    tasks["tasks"] = "not-a-list"
    invalid_payloads.append(tasks)

    task_schema = deepcopy(_valid_config_payload())
    task_schema["tasks"] = [{"map": "map.json"}]
    invalid_payloads.append(task_schema)

    movement_schema = deepcopy(_valid_config_payload())
    movement_schema["tasks"] = [{"map": "map.json", "movement": {"connectivity": 4}}]
    invalid_payloads.append(movement_schema)

    seeds = deepcopy(_valid_config_payload())
    seeds["stochastic"] = {"seeds": "not-a-list"}
    invalid_payloads.append(seeds)

    mapping = deepcopy(_valid_config_payload())
    mapping["algorithm_configs"] = []
    invalid_payloads.append(mapping)

    name = deepcopy(_valid_config_payload())
    name["name"] = " "
    invalid_payloads.append(name)

    absolute = deepcopy(_valid_config_payload())
    algorithm_configs = absolute["algorithm_configs"]
    assert isinstance(algorithm_configs, dict)
    algorithm_configs["dijkstra"] = "/absolute/dijkstra.yaml"
    invalid_payloads.append(absolute)

    for payload in invalid_payloads:
        with pytest.raises(ValueError):
            parse_benchmark_config(json.dumps(payload).encode())
