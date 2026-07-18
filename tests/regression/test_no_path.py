from pathlib import Path

import numpy as np
import pytest

from path_planning.algorithms.astar import AStarConfig, AStarPlanner
from path_planning.algorithms.dijkstra import DijkstraConfig, DijkstraPlanner
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.maps.io import load_scenario

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NO_PATH_SCENARIO = PROJECT_ROOT / "maps" / "handcrafted" / "no_path_20.json"


@pytest.mark.parametrize(
    "movement",
    [
        MovementConfig(4),
        MovementConfig(8),
        MovementConfig(8, allow_corner_cutting=True),
    ],
)
def test_deterministic_planners_terminate_with_matching_no_path_results(
    movement: MovementConfig,
) -> None:
    scenario = load_scenario(NO_PATH_SCENARIO)
    results = (
        DijkstraPlanner().plan(
            scenario.grid,
            scenario.start,
            scenario.goal,
            DijkstraConfig(movement),
        ),
        AStarPlanner().plan(
            scenario.grid,
            scenario.start,
            scenario.goal,
            AStarConfig(movement),
        ),
    )

    for result in results:
        assert not result.success
        assert result.path == ()
        assert result.path_length is None
        assert result.failure_reason == "no_path"
        assert result.expanded_nodes is not None and result.expanded_nodes > 0


@pytest.mark.parametrize(
    ("start", "goal", "expected_reason"),
    [
        ((-1, 0), (1, 1), "start_out_of_bounds"),
        ((0, 0), (2, 1), "goal_out_of_bounds"),
        ((0, 0), (1, 1), "start_blocked"),
        ((1, 1), (0, 0), "goal_blocked"),
    ],
)
def test_deterministic_planners_share_endpoint_failure_semantics(
    start: tuple[int, int],
    goal: tuple[int, int],
    expected_reason: str,
) -> None:
    grid = GridMap(np.array([[1, 0], [0, 0]], dtype=bool))
    movement = MovementConfig(4)
    results = (
        DijkstraPlanner().plan(grid, start, goal, DijkstraConfig(movement)),
        AStarPlanner().plan(grid, start, goal, AStarConfig(movement)),
    )

    assert all(result.failure_reason == expected_reason for result in results)
    assert all(result.expanded_nodes == 0 for result in results)
