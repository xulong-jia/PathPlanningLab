import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from path_planning.core.grid import GridMap
from path_planning.core.types import JsonValue, Point, validated_json_value
from path_planning.core.validation import validate_endpoints

SCHEMA_VERSION = 1
_SCHEMA_KEYS = {"schema_version", "name", "cells", "start", "goal", "metadata"}


@dataclass(frozen=True, slots=True)
class MapScenario:
    name: str
    grid: GridMap
    start: Point
    goal: Point
    metadata: dict[str, JsonValue]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("scenario name must not be empty")
        endpoint_failure = validate_endpoints(self.grid, self.start, self.goal)
        if endpoint_failure is not None:
            raise ValueError(endpoint_failure)
        metadata = validated_json_value(self.metadata)
        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a JSON object")
        object.__setattr__(self, "metadata", metadata)


def save_scenario(path: Path, scenario: MapScenario) -> None:
    rows = [
        [int(value) for value in row]
        for row in scenario.grid.cells.astype(int).tolist()
    ]
    payload: dict[str, JsonValue] = {
        "schema_version": SCHEMA_VERSION,
        "name": scenario.name,
        "cells": cast(JsonValue, rows),
        "start": cast(JsonValue, list(scenario.start)),
        "goal": cast(JsonValue, list(scenario.goal)),
        "metadata": validated_json_value(scenario.metadata),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, allow_nan=False, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_scenario(path: Path) -> MapScenario:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid scenario JSON: {error.msg}") from error

    if not isinstance(payload, dict) or set(payload) != _SCHEMA_KEYS:
        raise ValueError("invalid scenario schema keys")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported scenario schema version")
    if not isinstance(payload["name"], str):
        raise TypeError("scenario schema name must be a string")
    if not isinstance(payload["cells"], list):
        raise TypeError("scenario schema cells must be a list")
    if not isinstance(payload["metadata"], dict):
        raise TypeError("scenario schema metadata must be an object")

    return MapScenario(
        name=payload["name"],
        grid=GridMap(payload["cells"]),
        start=_parse_point(payload["start"], "start"),
        goal=_parse_point(payload["goal"], "goal"),
        metadata=cast(dict[str, JsonValue], payload["metadata"]),
    )


def _parse_point(value: object, field: str) -> Point:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(item, bool) or not isinstance(item, int) for item in value)
    ):
        raise ValueError(f"scenario schema {field} must be two integers")
    return value[0], value[1]


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON numeric constant: {value}")
