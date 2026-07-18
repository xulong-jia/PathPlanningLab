from pathlib import Path

import numpy as np
import pytest

from path_planning.algorithms.aco import ACOConfig, AntColonyPlanner
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.validation import validate_path
from path_planning.maps.io import load_scenario

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HANDCRAFTED = PROJECT_ROOT / "maps" / "handcrafted"


def _config(grid: GridMap, movement: MovementConfig) -> ACOConfig:
    return ACOConfig(
        movement=movement,
        ants=2,
        alpha=1.0,
        beta=3.0,
        evaporation_rate=0.2,
        pheromone_deposit=1.0,
        elite_weight=2.0,
        min_pheromone=0.01,
        max_pheromone=10.0,
        iterations=2,
        max_steps=grid.free_cell_count,
        max_restarts=0,
        max_backtracks=grid.free_cell_count,
        stagnation_iterations=3,
    )


@pytest.mark.parametrize("map_name", ["narrow_channel_20", "dead_ends_30"])
def test_aco_finds_valid_paths_on_complex_handcrafted_maps(map_name: str) -> None:
    scenario = load_scenario(HANDCRAFTED / f"{map_name}.json")
    config = _config(scenario.grid, MovementConfig(4))

    result = AntColonyPlanner().plan(
        scenario.grid,
        scenario.start,
        scenario.goal,
        config,
        seed=17,
    )

    validation = validate_path(
        scenario.grid,
        result.path,
        scenario.start,
        scenario.goal,
        config.movement,
    )
    assert result.success
    assert validation.valid
    assert result.path_length == pytest.approx(validation.path_length)


def test_aco_no_path_map_stops_in_shared_precheck() -> None:
    scenario = load_scenario(HANDCRAFTED / "no_path_20.json")
    config = _config(scenario.grid, MovementConfig(4))

    result = AntColonyPlanner().plan(
        scenario.grid,
        scenario.start,
        scenario.goal,
        config,
        seed=19,
    )

    assert not result.success
    assert result.failure_reason == "no_path_precheck"
    assert result.evaluations == 0
    assert result.iterations == 0
    assert result.convergence_history == ()


@pytest.mark.parametrize("allow_corner_cutting", [False, True])
def test_aco_obeys_shared_corner_cutting_rule(allow_corner_cutting: bool) -> None:
    grid = GridMap(np.array([[0, 1], [1, 0]], dtype=bool))
    movement = MovementConfig(8, allow_corner_cutting=allow_corner_cutting)

    result = AntColonyPlanner().plan(
        grid,
        (0, 0),
        (1, 1),
        _config(grid, movement),
        seed=23,
    )

    assert result.success is allow_corner_cutting
    if allow_corner_cutting:
        assert validate_path(grid, result.path, (0, 0), (1, 1), movement).valid
    else:
        assert result.failure_reason == "no_path_precheck"
