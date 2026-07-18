import math
from pathlib import Path

import numpy as np
import pytest

from path_planning.algorithms.astar import AStarConfig, AStarPlanner
from path_planning.algorithms.dijkstra import DijkstraConfig, DijkstraPlanner
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.validation import validate_path
from path_planning.maps.io import load_scenario

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HANDCRAFTED = PROJECT_ROOT / "maps" / "handcrafted"
MAP_NAMES = (
    "open_20",
    "narrow_channel_20",
    "maze_30",
    "dead_ends_30",
    "bottleneck_50",
    "no_path_20",
)


@pytest.mark.parametrize("map_name", MAP_NAMES)
@pytest.mark.parametrize("movement", [MovementConfig(4), MovementConfig(8)])
def test_deterministic_planners_share_map_movement_and_validation_contracts(
    map_name: str,
    movement: MovementConfig,
) -> None:
    scenario = load_scenario(HANDCRAFTED / f"{map_name}.json")
    dijkstra = DijkstraPlanner().plan(
        scenario.grid,
        scenario.start,
        scenario.goal,
        DijkstraConfig(movement),
    )
    astar = AStarPlanner().plan(
        scenario.grid,
        scenario.start,
        scenario.goal,
        AStarConfig(movement),
    )
    expected_reachable = scenario.metadata["expected_reachable"]
    assert isinstance(expected_reachable, bool)

    assert dijkstra.success is expected_reachable
    assert astar.success is expected_reachable
    if not expected_reachable:
        assert dijkstra.failure_reason == astar.failure_reason == "no_path"
        return

    for result in (dijkstra, astar):
        validation = validate_path(
            scenario.grid,
            result.path,
            scenario.start,
            scenario.goal,
            movement,
        )
        assert validation.valid
        assert result.path_length == pytest.approx(validation.path_length)
    assert astar.path_length == pytest.approx(dijkstra.path_length)


@pytest.mark.parametrize("allow_corner_cutting", [False, True])
def test_deterministic_planners_apply_the_same_corner_cutting_rule(
    allow_corner_cutting: bool,
) -> None:
    grid = GridMap(np.array([[0, 1], [1, 0]], dtype=bool))
    movement = MovementConfig(8, allow_corner_cutting=allow_corner_cutting)
    dijkstra = DijkstraPlanner().plan(
        grid,
        (0, 0),
        (1, 1),
        DijkstraConfig(movement),
    )
    astar = AStarPlanner().plan(
        grid,
        (0, 0),
        (1, 1),
        AStarConfig(movement),
    )

    assert dijkstra.success is allow_corner_cutting
    assert astar.success is allow_corner_cutting
    if allow_corner_cutting:
        assert dijkstra.path_length == pytest.approx(math.sqrt(2))
        assert astar.path_length == pytest.approx(dijkstra.path_length)
    else:
        assert dijkstra.failure_reason == astar.failure_reason == "no_path"
