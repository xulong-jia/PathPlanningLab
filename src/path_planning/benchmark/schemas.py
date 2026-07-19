"""Serializable benchmark configuration, task, record, and artifact schemas."""

import importlib
import json
import math
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Protocol, cast

from path_planning.core.movement import Connectivity, MovementConfig
from path_planning.core.types import JsonValue, validated_json_value

_ALGORITHMS = ("dijkstra", "astar", "aco", "ga")
_ROOT_KEYS = {
    "schema_version",
    "name",
    "algorithm_configs",
    "deterministic",
    "stochastic",
    "tasks",
}


class _YamlModule(Protocol):
    def safe_load(self, stream: str) -> object: ...


_yaml = cast(_YamlModule, importlib.import_module("yaml"))


@dataclass(frozen=True, slots=True)
class BenchmarkTask:
    map_path: Path
    movement: MovementConfig

    def __post_init__(self) -> None:
        _require_relative_path_object(self.map_path, "map_path")

    def to_dict(self) -> dict[str, object]:
        return {
            "map": self.map_path.as_posix(),
            "movement": _movement_dict(self.movement),
        }


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    name: str
    tasks: tuple[BenchmarkTask, ...]
    algorithm_configs: tuple[tuple[str, str], ...]
    deterministic_warmup_runs: int
    deterministic_measurement_runs: int
    stochastic_seeds: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("benchmark name must not be empty")
        if not self.tasks:
            raise ValueError("benchmark tasks must not be empty")
        if {name for name, _ in self.algorithm_configs} != set(_ALGORITHMS):
            raise ValueError("benchmark must configure every algorithm exactly once")
        if len(self.algorithm_configs) != len(_ALGORITHMS):
            raise ValueError("benchmark algorithm configs must not repeat algorithms")
        if any(
            not config_name or Path(config_name).is_absolute()
            for _, config_name in self.algorithm_configs
        ):
            raise ValueError("benchmark config names must be non-empty relative paths")
        _require_non_negative_int(
            self.deterministic_warmup_runs,
            "deterministic_warmup_runs",
        )
        _require_positive_int(
            self.deterministic_measurement_runs,
            "deterministic_measurement_runs",
        )
        if not self.stochastic_seeds:
            raise ValueError("stochastic_seeds must not be empty")
        if len(set(self.stochastic_seeds)) != len(self.stochastic_seeds):
            raise ValueError("stochastic_seeds must be unique")
        for seed in self.stochastic_seeds:
            _require_non_negative_int(seed, "stochastic seed")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "name": self.name,
            "algorithm_configs": dict(self.algorithm_configs),
            "deterministic": {
                "warmup_runs": self.deterministic_warmup_runs,
                "measurement_runs": self.deterministic_measurement_runs,
            },
            "stochastic": {"seeds": list(self.stochastic_seeds)},
            "tasks": [task.to_dict() for task in self.tasks],
        }


@dataclass(frozen=True, slots=True)
class BenchmarkRunRecord:
    algorithm: str
    map_name: str
    map_path: str
    start_row: int
    start_column: int
    goal_row: int
    goal_column: int
    connectivity: Connectivity
    diagonal_cost: float
    allow_corner_cutting: bool
    config_name: str
    seed: int | None
    status: str
    error: str | None
    wall_runtime_ms: float
    result_algorithm: str | None
    success: bool | None
    path_json: str | None
    path_length: float | None
    runtime_ms: float | None
    expanded_nodes: int | None
    evaluations: int | None
    iterations: int | None
    convergence_history_json: str | None
    result_seed: int | None
    failure_reason: str | None
    result_metadata_json: str | None

    def __post_init__(self) -> None:
        for name, text_value in (
            ("algorithm", self.algorithm),
            ("map_name", self.map_name),
            ("map_path", self.map_path),
            ("config_name", self.config_name),
            ("status", self.status),
        ):
            if not text_value.strip():
                raise ValueError(f"{name} must not be empty")
        for name, relative_path in (
            ("map_path", self.map_path),
            ("config_name", self.config_name),
        ):
            if Path(relative_path).is_absolute():
                raise ValueError(f"{name} must be a relative path")
        for name, coordinate in (
            ("start_row", self.start_row),
            ("start_column", self.start_column),
            ("goal_row", self.goal_row),
            ("goal_column", self.goal_column),
        ):
            _require_non_negative_int(coordinate, name)
        _require_connectivity(self.connectivity)
        _require_positive_float(self.diagonal_cost, "diagonal_cost")
        _require_bool(self.allow_corner_cutting, "allow_corner_cutting")
        if self.seed is not None:
            _require_non_negative_int(self.seed, "seed")
        if self.status not in {"success", "failed"}:
            raise ValueError("status must be success or failed")
        if self.status == "success" and self.error is not None:
            raise ValueError("successful records cannot have an error")
        if self.status == "failed" and not self.error:
            raise ValueError("failed records require an error")
        _require_optional_non_negative_float(
            self.wall_runtime_ms,
            "wall_runtime_ms",
            allow_none=False,
        )
        result_values = (
            self.success,
            self.path_json,
            self.path_length,
            self.runtime_ms,
            self.expanded_nodes,
            self.evaluations,
            self.iterations,
            self.convergence_history_json,
            self.result_seed,
            self.failure_reason,
            self.result_metadata_json,
        )
        if self.result_algorithm is None:
            if self.status == "success":
                raise ValueError("successful records require a result")
            if any(value is not None for value in result_values):
                raise ValueError("null result_algorithm requires null result fields")
            return
        if not self.result_algorithm.strip():
            raise ValueError("result_algorithm must not be empty")
        if self.result_algorithm != self.algorithm:
            raise ValueError("result_algorithm must match algorithm")
        if not isinstance(self.success, bool):
            raise ValueError("result success must be boolean")
        if self.status == "success" and not self.success:
            raise ValueError("successful record requires a successful result")
        for name, json_text in (
            ("path_json", self.path_json),
            ("convergence_history_json", self.convergence_history_json),
            ("result_metadata_json", self.result_metadata_json),
        ):
            if json_text is None:
                raise ValueError(f"{name} must not be null for a result")
            json.loads(json_text)
        _require_optional_non_negative_float(self.path_length, "path_length")
        _require_optional_non_negative_float(
            self.runtime_ms,
            "runtime_ms",
            allow_none=False,
        )
        for metric_name, value in (
            ("expanded_nodes", self.expanded_nodes),
            ("evaluations", self.evaluations),
            ("iterations", self.iterations),
            ("result_seed", self.result_seed),
        ):
            if value is not None:
                _require_non_negative_int(value, metric_name)

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(field.name for field in fields(cls))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            field.name: validated_json_value(getattr(self, field.name))
            for field in fields(self)
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), allow_nan=False)


@dataclass(frozen=True, slots=True)
class BenchmarkArtifacts:
    records_csv: Path | None
    records_json: Path | None
    metadata_json: Path | None
    summary_csv: Path | None
    summary_json: Path | None
    best_worst_json: Path | None
    manifest_json: Path | None
    figures: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        for name, path in (
            ("records_csv", self.records_csv),
            ("records_json", self.records_json),
            ("metadata_json", self.metadata_json),
            ("summary_csv", self.summary_csv),
            ("summary_json", self.summary_json),
            ("best_worst_json", self.best_worst_json),
            ("manifest_json", self.manifest_json),
        ):
            if path is not None:
                _require_relative_path_object(path, name)
        for figure in self.figures:
            _require_relative_path_object(figure, "figure")

    def to_dict(self) -> dict[str, object]:
        return {
            "records_csv": _optional_path(self.records_csv),
            "records_json": _optional_path(self.records_json),
            "metadata_json": _optional_path(self.metadata_json),
            "summary_csv": _optional_path(self.summary_csv),
            "summary_json": _optional_path(self.summary_json),
            "best_worst_json": _optional_path(self.best_worst_json),
            "manifest_json": _optional_path(self.manifest_json),
            "figures": [str(path) for path in self.figures],
        }


def load_benchmark_config(config_path: Path) -> BenchmarkConfig:
    return parse_benchmark_config(config_path.read_bytes())


def parse_benchmark_config(config_bytes: bytes) -> BenchmarkConfig:
    payload = _yaml.safe_load(config_bytes.decode("utf-8"))
    root = _require_mapping(payload, "benchmark config")
    schema_version = root.get("schema_version")
    if (
        set(root) != _ROOT_KEYS
        or isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != 1
    ):
        raise ValueError("invalid benchmark config schema")

    algorithm_configs = _require_algorithm_configs(root["algorithm_configs"])
    deterministic = _require_mapping(root["deterministic"], "deterministic")
    stochastic = _require_mapping(root["stochastic"], "stochastic")
    if set(deterministic) != {"warmup_runs", "measurement_runs"}:
        raise ValueError("invalid deterministic benchmark budget")
    if set(stochastic) != {"seeds"}:
        raise ValueError("invalid stochastic benchmark budget")

    return BenchmarkConfig(
        name=_require_string(root["name"], "name"),
        tasks=_require_tasks(root["tasks"]),
        algorithm_configs=algorithm_configs,
        deterministic_warmup_runs=_require_non_negative_int(
            deterministic["warmup_runs"],
            "warmup_runs",
        ),
        deterministic_measurement_runs=_require_positive_int(
            deterministic["measurement_runs"],
            "measurement_runs",
        ),
        stochastic_seeds=_require_seeds(stochastic["seeds"]),
    )


def _require_algorithm_configs(value: object) -> tuple[tuple[str, str], ...]:
    configs = _require_mapping(value, "algorithm_configs")
    if set(configs) != set(_ALGORITHMS):
        raise ValueError("algorithm_configs must name every algorithm")
    return tuple(
        (algorithm, _require_relative_path(configs[algorithm], algorithm))
        for algorithm in _ALGORITHMS
    )


def _require_tasks(value: object) -> tuple[BenchmarkTask, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("tasks must be a non-empty list")
    tasks: list[BenchmarkTask] = []
    for raw_task in value:
        task = _require_mapping(raw_task, "task")
        if set(task) != {"map", "movement"}:
            raise ValueError("invalid benchmark task schema")
        movement = _require_mapping(task["movement"], "movement")
        if set(movement) != {
            "connectivity",
            "diagonal_cost",
            "allow_corner_cutting",
        }:
            raise ValueError("invalid benchmark movement schema")
        tasks.append(
            BenchmarkTask(
                map_path=Path(_require_relative_path(task["map"], "map")),
                movement=MovementConfig(
                    _require_connectivity(movement["connectivity"]),
                    _require_positive_float(
                        movement["diagonal_cost"],
                        "diagonal_cost",
                    ),
                    _require_bool(
                        movement["allow_corner_cutting"],
                        "allow_corner_cutting",
                    ),
                ),
            )
        )
    return tuple(tasks)


def _require_seeds(value: object) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError("seeds must be a list")
    return tuple(_require_non_negative_int(seed, "seed") for seed in value)


def _require_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be a string-keyed mapping")
    return cast(dict[str, object], value)


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_relative_path(value: object, field: str) -> str:
    path = _require_string(value, field)
    if Path(path).is_absolute():
        raise ValueError(f"{field} must be a relative path")
    return path


def _require_relative_path_object(path: Path, field: str) -> None:
    if path.is_absolute():
        raise ValueError(f"{field} must be a relative path")


def _require_non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _require_positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _require_positive_float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be finite and positive")
    return number


def _require_optional_non_negative_float(
    value: object,
    field: str,
    *,
    allow_none: bool = True,
) -> None:
    if value is None:
        if allow_none:
            return
        raise ValueError(f"{field} must not be null")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field} must be finite and non-negative")


def _require_connectivity(value: object) -> Connectivity:
    if value not in (4, 8):
        raise ValueError("connectivity must be 4 or 8")
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def _movement_dict(movement: MovementConfig) -> dict[str, object]:
    return {
        "connectivity": movement.connectivity,
        "diagonal_cost": movement.diagonal_cost,
        "allow_corner_cutting": movement.allow_corner_cutting,
    }


def _optional_path(path: Path | None) -> str | None:
    return str(path) if path is not None else None
