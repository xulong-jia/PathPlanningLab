import importlib
from pathlib import Path
from typing import Protocol, cast

from path_planning.core.types import JsonValue, Point
from path_planning.maps.generation import RandomMapConfig, generate_random_scenario
from path_planning.maps.io import MapScenario, load_scenario, save_scenario

_SUITES = ("evaluation", "tuning")
_ENTRY_KEYS = {
    "name",
    "rows",
    "columns",
    "target_density",
    "seed",
    "start",
    "goal",
    "guarantee_reachable",
}


class _YamlModule(Protocol):
    def safe_load(self, stream: str) -> object: ...


_yaml = cast(_YamlModule, importlib.import_module("yaml"))


def generate_configured_suites(
    config_path: Path,
    output_root: Path,
) -> dict[str, tuple[Path, ...]]:
    payload = _yaml.safe_load(config_path.read_text(encoding="utf-8"))
    root = _require_mapping(payload, "root")
    if set(root) != {"schema_version", *_SUITES} or root["schema_version"] != 1:
        raise ValueError("invalid map generation config schema")

    generated: dict[str, tuple[Path, ...]] = {}
    for suite_name in _SUITES:
        entries = root[suite_name]
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"suite {suite_name} must be a non-empty list")
        paths: list[Path] = []
        for raw_entry in entries:
            entry = _require_mapping(raw_entry, f"suite {suite_name} entry")
            if set(entry) != _ENTRY_KEYS:
                raise ValueError(f"invalid map generation entry schema: {suite_name}")
            name = _require_string(entry["name"], "name")
            scenario = generate_random_scenario(
                _config_from_entry(entry),
                name=name,
            )
            metadata: dict[str, JsonValue] = {**scenario.metadata, "suite": suite_name}
            scenario = MapScenario(
                scenario.name,
                scenario.grid,
                scenario.start,
                scenario.goal,
                metadata,
            )
            path = output_root / suite_name / f"{name}.json"
            save_scenario(path, scenario)
            paths.append(path)
        generated[suite_name] = tuple(paths)
    return generated


def load_suite(directory: Path) -> tuple[MapScenario, ...]:
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise ValueError(f"map suite is empty: {directory}")
    scenarios = tuple(load_scenario(path) for path in paths)
    names = {scenario.name for scenario in scenarios}
    if len(names) != len(scenarios):
        raise ValueError(f"map suite contains duplicate scenario names: {directory}")
    return scenarios


def suite_seeds(scenarios: tuple[MapScenario, ...]) -> set[int]:
    seeds: set[int] = set()
    for scenario in scenarios:
        seed = scenario.metadata.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"scenario has invalid seed metadata: {scenario.name}")
        seeds.add(seed)
    return seeds


def _config_from_entry(entry: dict[str, object]) -> RandomMapConfig:
    return RandomMapConfig(
        rows=_require_int(entry["rows"], "rows"),
        columns=_require_int(entry["columns"], "columns"),
        target_density=_require_float(entry["target_density"], "target_density"),
        seed=_require_int(entry["seed"], "seed"),
        start=_require_point(entry["start"], "start"),
        goal=_require_point(entry["goal"], "goal"),
        guarantee_reachable=_require_bool(
            entry["guarantee_reachable"],
            "guarantee_reachable",
        ),
    )


def _require_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be a string-keyed mapping")
    return cast(dict[str, object], value)


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _require_float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    return float(value)


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def _require_point(value: object, field: str) -> Point:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(item, bool) or not isinstance(item, int) for item in value)
    ):
        raise ValueError(f"{field} must contain two integers")
    return value[0], value[1]
