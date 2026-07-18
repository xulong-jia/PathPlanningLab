import json
from pathlib import Path

import numpy as np
import pytest

from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.validation import is_reachable
from path_planning.maps.io import MapScenario, load_scenario, save_scenario
from path_planning.maps.suites import (
    generate_configured_suites,
    load_suite,
    suite_seeds,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HANDCRAFTED = PROJECT_ROOT / "maps" / "handcrafted"
GENERATED = PROJECT_ROOT / "maps" / "generated"
GENERATION_CONFIG = PROJECT_ROOT / "configs" / "map_generation.yaml"

EXPECTED_REACHABILITY = {
    "open_20": True,
    "narrow_channel_20": True,
    "maze_30": True,
    "dead_ends_30": True,
    "bottleneck_50": True,
    "no_path_20": False,
}


@pytest.mark.parametrize("name", EXPECTED_REACHABILITY)
def test_handcrafted_map_features_and_reachability(name: str) -> None:
    path = HANDCRAFTED / f"{name}.json"
    scenario = load_scenario(path)
    expected = EXPECTED_REACHABILITY[name]

    assert scenario.name == name
    assert scenario.metadata["source"] == "handcrafted"
    assert scenario.metadata["expected_reachable"] is expected
    assert scenario.metadata["rows"] == scenario.grid.shape[0]
    assert scenario.metadata["columns"] == scenario.grid.shape[1]
    assert (
        is_reachable(
            scenario.grid,
            scenario.start,
            scenario.goal,
            MovementConfig(4),
        )
        is expected
    )
    assert "/Users/" not in path.read_text(encoding="utf-8")


def test_special_handcrafted_map_structures() -> None:
    open_map = load_scenario(HANDCRAFTED / "open_20.json")
    channel = load_scenario(HANDCRAFTED / "narrow_channel_20.json")
    bottleneck = load_scenario(HANDCRAFTED / "bottleneck_50.json")
    no_path = load_scenario(HANDCRAFTED / "no_path_20.json")

    assert open_map.grid.free_cell_count == 400
    assert channel.grid.free_cell_count == 39
    assert sum(not bottleneck.grid.is_blocked((row, 25)) for row in range(50)) == 1
    assert all(no_path.grid.is_blocked((row, 10)) for row in range(20))


def test_config_rebuilds_committed_generated_suites(tmp_path: Path) -> None:
    generated = generate_configured_suites(GENERATION_CONFIG, tmp_path)

    assert len(generated["evaluation"]) == 9
    assert len(generated["tuning"]) == 4
    for suite_name, paths in generated.items():
        for path in paths:
            committed = GENERATED / suite_name / path.name
            assert path.read_bytes() == committed.read_bytes()


def test_generated_suites_have_disjoint_fixed_seeds() -> None:
    evaluation = load_suite(GENERATED / "evaluation")
    tuning = load_suite(GENERATED / "tuning")
    evaluation_seeds = suite_seeds(evaluation)
    tuning_seeds = suite_seeds(tuning)

    assert len(evaluation) == 9
    assert len(tuning) == 4
    assert tuning_seeds == {4101, 4201, 4301, 4401}
    assert evaluation_seeds.isdisjoint(tuning_seeds)


@pytest.mark.parametrize("suite_name", ["evaluation", "tuning"])
def test_all_generated_maps_match_density_and_reachability(suite_name: str) -> None:
    scenarios = load_suite(GENERATED / suite_name)

    for scenario in scenarios:
        rows, columns = scenario.grid.shape
        blocked = int(np.count_nonzero(scenario.grid.cells))
        target_density = scenario.metadata["target_density"]
        assert isinstance(target_density, float)
        assert abs(blocked / (rows * columns) - target_density) <= 1 / (rows * columns)
        assert scenario.metadata["suite"] == suite_name
        assert is_reachable(
            scenario.grid,
            scenario.start,
            scenario.goal,
            MovementConfig(4),
        )


def _valid_generation_entry() -> dict[str, object]:
    return {
        "name": "generated",
        "rows": 2,
        "columns": 2,
        "target_density": 0.0,
        "seed": 1,
        "start": [0, 0],
        "goal": [1, 1],
        "guarantee_reachable": True,
    }


def _write_generation_config(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"schema_version": 2, "evaluation": [], "tuning": []},
        {"schema_version": 1, "evaluation": [], "tuning": []},
        {
            "schema_version": 1,
            "evaluation": [{"name": "incomplete"}],
            "tuning": [_valid_generation_entry()],
        },
    ],
)
def test_generation_config_rejects_invalid_structure(
    tmp_path: Path,
    payload: object,
) -> None:
    config_path = tmp_path / "invalid.json"
    _write_generation_config(config_path, payload)

    with pytest.raises(ValueError):
        generate_configured_suites(config_path, tmp_path / "output")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("rows", True),
        ("target_density", "0.2"),
        ("guarantee_reachable", 1),
        ("start", [0]),
    ],
)
def test_generation_config_rejects_invalid_entry_values(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    entry = _valid_generation_entry()
    entry[field] = value
    payload = {
        "schema_version": 1,
        "evaluation": [entry],
        "tuning": [_valid_generation_entry()],
    }
    config_path = tmp_path / "invalid_entry.json"
    _write_generation_config(config_path, payload)

    with pytest.raises(ValueError):
        generate_configured_suites(config_path, tmp_path / "output")


def test_load_suite_rejects_empty_and_duplicate_scenarios(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="empty"):
        load_suite(empty)

    duplicates = tmp_path / "duplicates"
    scenario = MapScenario(
        "duplicate",
        GridMap(np.zeros((1, 1), dtype=bool)),
        (0, 0),
        (0, 0),
        {"seed": 1},
    )
    save_scenario(duplicates / "first.json", scenario)
    save_scenario(duplicates / "second.json", scenario)
    with pytest.raises(ValueError, match="duplicate"):
        load_suite(duplicates)


def test_suite_seeds_rejects_invalid_seed_metadata() -> None:
    scenario = MapScenario(
        "invalid_seed",
        GridMap(np.zeros((1, 1), dtype=bool)),
        (0, 0),
        (0, 0),
        {"seed": True},
    )

    with pytest.raises(ValueError, match="seed"):
        suite_seeds((scenario,))
