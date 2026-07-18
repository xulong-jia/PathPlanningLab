import json
from pathlib import Path

import numpy as np
import pytest

from path_planning.core.grid import GridMap
from path_planning.maps.io import MapScenario, load_scenario, save_scenario

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "maps"


def test_map_scenario_round_trip(tmp_path: Path) -> None:
    scenario = MapScenario(
        name="round_trip",
        grid=GridMap(np.array([[0, 1], [0, 0]], dtype=bool)),
        start=(0, 0),
        goal=(1, 1),
        metadata={"source": "test", "expected_reachable": True},
    )
    target = tmp_path / "scenario.json"

    save_scenario(target, scenario)
    loaded = load_scenario(target)

    assert loaded.name == scenario.name
    assert np.array_equal(loaded.grid.cells, scenario.grid.cells)
    assert loaded.start == scenario.start
    assert loaded.goal == scenario.goal
    assert loaded.metadata == scenario.metadata


def test_load_scenario_accepts_valid_fixture() -> None:
    scenario = load_scenario(FIXTURES / "valid_scenario.json")

    assert scenario.name == "fixture_valid"
    assert scenario.grid.shape == (2, 3)


def test_load_scenario_rejects_invalid_fixture_schema() -> None:
    with pytest.raises((TypeError, ValueError), match="schema"):
        load_scenario(FIXTURES / "invalid_scenario.json")


def test_map_scenario_rejects_invalid_endpoints() -> None:
    grid = GridMap(np.array([[1, 0], [0, 0]], dtype=bool))

    with pytest.raises(ValueError, match="start_blocked"):
        MapScenario("invalid", grid, (0, 0), (1, 1), {})


def test_load_scenario_rejects_non_json_metadata(tmp_path: Path) -> None:
    source = tmp_path / "bad_metadata.json"
    source.write_text(
        '{"schema_version":1,"name":"bad","cells":[[0]],'
        '"start":[0,0],"goal":[0,0],"metadata":{"bad":NaN}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="JSON"):
        load_scenario(source)


def test_map_scenario_rejects_empty_name_and_non_object_metadata() -> None:
    grid = GridMap(np.zeros((1, 1), dtype=bool))

    with pytest.raises(ValueError, match="name"):
        MapScenario(" ", grid, (0, 0), (0, 0), {})
    with pytest.raises(TypeError, match="metadata"):
        MapScenario("bad", grid, (0, 0), (0, 0), [])  # type: ignore[arg-type]


def _valid_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "valid",
        "cells": [[0]],
        "start": [0, 0],
        "goal": [0, 0],
        "metadata": {},
    }


def test_load_scenario_rejects_invalid_json_syntax(tmp_path: Path) -> None:
    source = tmp_path / "invalid.json"
    source.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid scenario JSON"):
        load_scenario(source)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("schema_version", 2, "version"),
        ("name", 1, "name"),
        ("cells", "0", "cells"),
        ("metadata", [], "metadata"),
        ("start", [0], "start"),
    ],
)
def test_load_scenario_rejects_invalid_field_types(
    tmp_path: Path,
    field: str,
    value: object,
    expected: str,
) -> None:
    payload = _valid_payload()
    payload[field] = value
    source = tmp_path / "invalid_field.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises((TypeError, ValueError), match=expected):
        load_scenario(source)
