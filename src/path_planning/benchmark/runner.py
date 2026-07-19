"""Serial, fair execution of benchmark tasks."""

import csv
import importlib
import io
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Protocol, cast

import pandas as pd  # type: ignore[import-untyped]

from path_planning.algorithms import (
    ACOConfig,
    AntColonyPlanner,
    AStarConfig,
    AStarPlanner,
    DijkstraConfig,
    DijkstraPlanner,
    GAConfig,
    GeneticPlanner,
    HeuristicName,
)
from path_planning.algorithms.genetic import (
    CrossoverMethod,
    MutationMethod,
    SelectionMethod,
)
from path_planning.benchmark.metadata import collect_run_metadata, sha256_bytes
from path_planning.benchmark.schemas import (
    BenchmarkArtifacts,
    BenchmarkRunRecord,
    BenchmarkTask,
    parse_benchmark_config,
)
from path_planning.benchmark.statistics import best_worst_runs, summarize_runs
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.result import PlanningResult
from path_planning.core.types import JsonValue, Point, validated_json_value
from path_planning.core.validation import validate_path
from path_planning.maps.io import MapScenario, load_scenario


class _YamlModule(Protocol):
    def safe_load(self, stream: str) -> object: ...


_yaml = cast(_YamlModule, importlib.import_module("yaml"))
_RunPlanner = Callable[[GridMap, Point, Point, int | None], PlanningResult]
_PATH_LENGTH_REL_TOLERANCE = 1e-12
_PATH_LENGTH_ABS_TOLERANCE = 1e-12


@dataclass(frozen=True, slots=True)
class _ConfiguredPlanner:
    name: str
    config_name: str
    run: _RunPlanner


@dataclass(frozen=True, slots=True)
class _PreparedTask:
    map_path: str
    scenario: MapScenario
    movement: MovementConfig
    planners: tuple[_ConfiguredPlanner, ...]


def run_benchmark(config_path: Path, output_dir: Path) -> BenchmarkArtifacts:
    """Run every configured task serially and retain every recorded result."""
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")

    config_bytes = config_path.read_bytes()
    benchmark = parse_benchmark_config(config_bytes)
    metadata = collect_run_metadata(config_bytes, config_path)
    context = config_path.resolve().parent.parent
    algorithm_configs = dict(benchmark.algorithm_configs)
    prepared = tuple(
        _prepare_task(task, algorithm_configs, context) for task in benchmark.tasks
    )

    output_dir.mkdir(parents=True)
    records: list[BenchmarkRunRecord] = []
    deterministic = {"dijkstra", "astar"}
    for task in prepared:
        for planner in task.planners:
            if planner.name in deterministic:
                for _ in range(benchmark.deterministic_warmup_runs):
                    warmup_result = planner.run(
                        task.scenario.grid,
                        task.scenario.start,
                        task.scenario.goal,
                        None,
                    )
                    warmup_error = _result_protocol_error(task, warmup_result, None)
                    if warmup_error is not None:
                        raise RuntimeError(f"warmup {warmup_error}")
                seeds: tuple[int | None, ...] = (
                    None,
                ) * benchmark.deterministic_measurement_runs
            else:
                seeds = benchmark.stochastic_seeds
            for seed in seeds:
                records.append(_execute(task, planner, seed))

    records_csv = Path("raw_runs.csv")
    records_json = Path("raw_runs.json")
    metadata_json = Path("run_metadata.json")
    summary_csv = Path("summary.csv")
    summary_json = Path("summary.json")
    best_worst_json = Path("best_worst.json")
    manifest_json = Path("manifest.json")
    rows = [record.to_dict() for record in records]
    runs = pd.DataFrame(rows)
    summary = summarize_runs(runs)
    summary_rows = [
        cast(dict[str, JsonValue], validated_json_value(row))
        for row in cast(list[dict[str, object]], summary.to_dict(orient="records"))
    ]
    extrema = best_worst_runs(runs)
    raw_csv = _csv_bytes(rows, BenchmarkRunRecord.field_names())
    raw_json = _json_bytes(rows)
    metadata_content = _json_bytes(metadata, sort_keys=True)
    summary_csv_content = _csv_bytes(
        summary_rows,
        tuple(str(column) for column in summary.columns),
    )
    summary_json_content = _json_bytes(summary_rows)
    best_worst_content = _json_bytes(extrema)
    files = {
        records_csv.as_posix(): raw_csv,
        records_json.as_posix(): raw_json,
        metadata_json.as_posix(): metadata_content,
        summary_csv.as_posix(): summary_csv_content,
        summary_json.as_posix(): summary_json_content,
        best_worst_json.as_posix(): best_worst_content,
    }
    manifest = {
        "schema_version": 1,
        "run_id": metadata["run_id"],
        "config_sha256": metadata["config_sha256"],
        "files": {name: sha256_bytes(content) for name, content in files.items()},
    }
    for name, content in files.items():
        (output_dir / name).write_bytes(content)
    (output_dir / manifest_json).write_bytes(_json_bytes(manifest, sort_keys=True))
    return BenchmarkArtifacts(
        records_csv=records_csv,
        records_json=records_json,
        metadata_json=metadata_json,
        summary_csv=summary_csv,
        summary_json=summary_json,
        best_worst_json=best_worst_json,
        manifest_json=manifest_json,
    )


def _prepare_task(
    task: BenchmarkTask,
    algorithm_configs: Mapping[str, str],
    context: Path,
) -> _PreparedTask:
    scenario = load_scenario(_resolve(context, task.map_path))
    planners = tuple(
        _load_planner(
            algorithm,
            config_name,
            _resolve(context, Path(config_name)),
            task.movement,
        )
        for algorithm, config_name in algorithm_configs.items()
    )
    return _PreparedTask(task.map_path.as_posix(), scenario, task.movement, planners)


def _load_planner(
    algorithm: str,
    config_name: str,
    config_path: Path,
    movement: MovementConfig,
) -> _ConfiguredPlanner:
    raw = _yaml.safe_load(config_path.read_text(encoding="utf-8"))
    values = _mapping(raw, f"{algorithm} config")
    if algorithm == "dijkstra":
        _keys(values, {"movement"}, algorithm)
        dijkstra_config = DijkstraConfig(movement)
        dijkstra = DijkstraPlanner()
        return _ConfiguredPlanner(
            algorithm,
            config_name,
            lambda grid, start, goal, seed: dijkstra.plan(
                grid, start, goal, dijkstra_config, seed
            ),
        )
    if algorithm == "astar":
        if set(values) not in ({"heuristic"}, {"movement", "heuristic"}):
            raise ValueError("invalid astar config schema")
        heuristic = _task_heuristic(values["heuristic"])
        astar_config = AStarConfig(movement, heuristic)
        astar = AStarPlanner()
        return _ConfiguredPlanner(
            algorithm,
            config_name,
            lambda grid, start, goal, seed: astar.plan(
                grid, start, goal, astar_config, seed
            ),
        )
    if algorithm == "aco":
        aco_config = _aco_config(values, movement)
        aco = AntColonyPlanner()
        return _ConfiguredPlanner(
            algorithm,
            config_name,
            lambda grid, start, goal, seed: aco.plan(
                grid, start, goal, aco_config, seed
            ),
        )
    if algorithm == "ga":
        ga_config = _ga_config(values, movement)
        ga = GeneticPlanner()
        return _ConfiguredPlanner(
            algorithm,
            config_name,
            lambda grid, start, goal, seed: ga.plan(grid, start, goal, ga_config, seed),
        )
    raise ValueError(f"unknown benchmark algorithm: {algorithm}")


def _execute(
    task: _PreparedTask,
    planner: _ConfiguredPlanner,
    seed: int | None,
) -> BenchmarkRunRecord:
    result: PlanningResult | None = None
    error: str | None = None
    started = perf_counter()
    try:
        result = planner.run(
            task.scenario.grid,
            task.scenario.start,
            task.scenario.goal,
            seed,
        )
    except Exception as exception:
        wall_runtime_ms = (perf_counter() - started) * 1000.0
        error = f"{type(exception).__name__}: {exception}"
    else:
        wall_runtime_ms = (perf_counter() - started) * 1000.0
        error = _result_error(task, result, seed)

    result_payload = result.to_dict() if result is not None else None
    return BenchmarkRunRecord(
        algorithm=planner.name,
        map_name=task.scenario.name,
        map_path=task.map_path,
        start_row=task.scenario.start[0],
        start_column=task.scenario.start[1],
        goal_row=task.scenario.goal[0],
        goal_column=task.scenario.goal[1],
        connectivity=task.movement.connectivity,
        diagonal_cost=task.movement.diagonal_cost,
        allow_corner_cutting=task.movement.allow_corner_cutting,
        config_name=planner.config_name,
        seed=seed,
        status="failed" if error is not None else "success",
        error=error,
        wall_runtime_ms=wall_runtime_ms,
        result_algorithm=result.algorithm if result is not None else None,
        success=result.success if result is not None else None,
        path_json=_json_text(result_payload["path"])
        if result_payload is not None
        else None,
        path_length=result.path_length if result is not None else None,
        runtime_ms=result.runtime_ms if result is not None else None,
        expanded_nodes=result.expanded_nodes if result is not None else None,
        evaluations=result.evaluations if result is not None else None,
        iterations=result.iterations if result is not None else None,
        convergence_history_json=_json_text(result_payload["convergence_history"])
        if result_payload is not None
        else None,
        result_seed=result.seed if result is not None else None,
        failure_reason=result.failure_reason if result is not None else None,
        result_metadata_json=_json_text(result_payload["metadata"])
        if result_payload is not None
        else None,
    )


def _csv_bytes(
    records: list[dict[str, JsonValue]],
    fieldnames: tuple[str, ...],
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=fieldnames,
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(records)
    return stream.getvalue().encode("utf-8")


def _json_bytes(value: object, *, sort_keys: bool = False) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=sort_keys,
        )
        + "\n"
    ).encode("utf-8")


def _json_text(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _result_error(
    task: _PreparedTask,
    result: PlanningResult,
    requested_seed: int | None,
) -> str | None:
    protocol_error = _result_protocol_error(task, result, requested_seed)
    if protocol_error is not None:
        return protocol_error
    if not result.success:
        return result.failure_reason
    return None


def _result_protocol_error(
    task: _PreparedTask,
    result: PlanningResult,
    requested_seed: int | None,
) -> str | None:
    if result.seed != requested_seed:
        return "result_protocol_failed: seed_mismatch"
    if not result.success:
        return None
    validation = validate_path(
        task.scenario.grid,
        result.path,
        task.scenario.start,
        task.scenario.goal,
        task.movement,
    )
    if not validation.valid:
        return f"path_validation_failed: {validation.failure_reason}"
    if validation.path_length is None or result.path_length is None:
        return "path_validation_failed: path_length_mismatch"
    if not math.isclose(
        result.path_length,
        validation.path_length,
        rel_tol=_PATH_LENGTH_REL_TOLERANCE,
        abs_tol=_PATH_LENGTH_ABS_TOLERANCE,
    ):
        return "path_validation_failed: path_length_mismatch"
    return None


def _aco_config(values: dict[str, object], movement: MovementConfig) -> ACOConfig:
    fields = {
        "movement",
        "ants",
        "alpha",
        "beta",
        "evaporation_rate",
        "pheromone_deposit",
        "elite_weight",
        "min_pheromone",
        "max_pheromone",
        "iterations",
        "max_steps",
        "max_restarts",
        "max_backtracks",
        "stagnation_iterations",
    }
    _keys(values, fields, "aco")
    return ACOConfig(
        movement=movement,
        ants=cast(int, values["ants"]),
        alpha=cast(float, values["alpha"]),
        beta=cast(float, values["beta"]),
        evaporation_rate=cast(float, values["evaporation_rate"]),
        pheromone_deposit=cast(float, values["pheromone_deposit"]),
        elite_weight=cast(float, values["elite_weight"]),
        min_pheromone=cast(float, values["min_pheromone"]),
        max_pheromone=cast(float, values["max_pheromone"]),
        iterations=cast(int, values["iterations"]),
        max_steps=cast(int, values["max_steps"]),
        max_restarts=cast(int, values["max_restarts"]),
        max_backtracks=cast(int, values["max_backtracks"]),
        stagnation_iterations=cast(int, values["stagnation_iterations"]),
    )


def _ga_config(values: dict[str, object], movement: MovementConfig) -> GAConfig:
    required = {
        "movement",
        "population_size",
        "generations",
        "crossover_probability",
        "mutation_probability",
        "tournament_size",
        "elite_size",
        "max_initialization_steps",
        "initialization_attempts",
        "stagnation_generations",
        "path_length_penalty",
        "turn_penalty",
        "repeat_penalty",
        "unreachable_base_penalty",
        "collision_penalty",
        "remaining_distance_penalty",
    }
    optional = {"crossover_method", "mutation_method", "selection_method"}
    if not required <= set(values) or not set(values) <= required | optional:
        raise ValueError("invalid ga config schema")
    return GAConfig(
        movement=movement,
        population_size=cast(int, values["population_size"]),
        generations=cast(int, values["generations"]),
        crossover_probability=cast(float, values["crossover_probability"]),
        mutation_probability=cast(float, values["mutation_probability"]),
        tournament_size=cast(int, values["tournament_size"]),
        elite_size=cast(int, values["elite_size"]),
        max_initialization_steps=cast(int, values["max_initialization_steps"]),
        initialization_attempts=cast(int, values["initialization_attempts"]),
        stagnation_generations=cast(int, values["stagnation_generations"]),
        path_length_penalty=cast(float, values["path_length_penalty"]),
        turn_penalty=cast(float, values["turn_penalty"]),
        repeat_penalty=cast(float, values["repeat_penalty"]),
        unreachable_base_penalty=cast(float, values["unreachable_base_penalty"]),
        collision_penalty=cast(float, values["collision_penalty"]),
        remaining_distance_penalty=cast(float, values["remaining_distance_penalty"]),
        crossover_method=cast(
            CrossoverMethod, values.get("crossover_method", "common_node")
        ),
        mutation_method=cast(
            MutationMethod, values.get("mutation_method", "reroute_segment")
        ),
        selection_method=cast(
            SelectionMethod, values.get("selection_method", "tournament")
        ),
    )


def _task_heuristic(value: object) -> HeuristicName | None:
    if value == "auto":
        return None
    return cast(HeuristicName, value)


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be a string-keyed mapping")
    return cast(dict[str, object], value)


def _keys(values: dict[str, object], expected: set[str], algorithm: str) -> None:
    if set(values) != expected:
        raise ValueError(f"invalid {algorithm} config schema")


def _resolve(context: Path, relative: Path) -> Path:
    resolved = (context / relative).resolve()
    try:
        resolved.relative_to(context)
    except ValueError as error:
        message = f"benchmark path escapes config context: {relative}"
        raise ValueError(message) from error
    return resolved
