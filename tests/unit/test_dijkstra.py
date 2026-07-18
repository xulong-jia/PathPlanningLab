import math

import numpy as np
import pytest

from path_planning.algorithms.dijkstra import DijkstraConfig, DijkstraPlanner
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.validation import validate_path


@pytest.mark.parametrize(
    ("movement", "expected_cost"),
    [
        (MovementConfig(4), 8.0),
        (MovementConfig(8), 4 * math.sqrt(2)),
    ],
)
def test_dijkstra_finds_hand_calculated_cost_on_open_five_by_five(
    movement: MovementConfig,
    expected_cost: float,
) -> None:
    grid = GridMap(np.zeros((5, 5), dtype=bool))
    planner = DijkstraPlanner()

    result = planner.plan(grid, (0, 0), (4, 4), DijkstraConfig(movement))

    validation = validate_path(grid, result.path, (0, 0), (4, 4), movement)
    assert result.success
    assert validation.valid
    assert result.path_length == pytest.approx(expected_cost)
    assert result.path_length == pytest.approx(validation.path_length)
    assert result.expanded_nodes is not None and result.expanded_nodes > 0
    assert result.evaluations is None


def test_dijkstra_handles_start_equal_to_goal() -> None:
    grid = GridMap(np.zeros((1, 1), dtype=bool))

    result = DijkstraPlanner().plan(
        grid,
        (0, 0),
        (0, 0),
        DijkstraConfig(MovementConfig(4)),
        seed=123,
    )

    assert result.success
    assert result.path == ((0, 0),)
    assert result.path_length == 0.0
    assert result.expanded_nodes == 1
    assert result.seed is None


def test_dijkstra_returns_explicit_failure_when_no_path_exists() -> None:
    grid = GridMap(
        np.array(
            [
                [0, 1, 0],
                [0, 1, 0],
                [0, 1, 0],
            ],
            dtype=bool,
        )
    )

    result = DijkstraPlanner().plan(
        grid,
        (0, 0),
        (0, 2),
        DijkstraConfig(MovementConfig(4)),
    )

    assert not result.success
    assert result.path == ()
    assert result.path_length is None
    assert result.failure_reason == "no_path"
    assert result.expanded_nodes == 3


@pytest.mark.parametrize(
    ("start", "goal", "expected_reason"),
    [
        ((-1, 0), (1, 1), "start_out_of_bounds"),
        ((0, 0), (2, 1), "goal_out_of_bounds"),
        ((0, 0), (1, 1), "start_blocked"),
        ((1, 1), (0, 0), "goal_blocked"),
    ],
)
def test_dijkstra_returns_endpoint_validation_failures(
    start: tuple[int, int],
    goal: tuple[int, int],
    expected_reason: str,
) -> None:
    grid = GridMap(np.array([[1, 0], [0, 0]], dtype=bool))

    result = DijkstraPlanner().plan(
        grid,
        start,
        goal,
        DijkstraConfig(MovementConfig(4)),
    )

    assert not result.success
    assert result.failure_reason == expected_reason
    assert result.expanded_nodes == 0


def test_dijkstra_stops_when_goal_is_removed_from_frontier() -> None:
    grid = GridMap(np.zeros((5, 5), dtype=bool))

    result = DijkstraPlanner().plan(
        grid,
        (0, 0),
        (0, 1),
        DijkstraConfig(MovementConfig(4)),
    )

    assert result.success
    assert result.expanded_nodes == 2
    assert result.expanded_nodes < grid.free_cell_count
    assert result.iterations == 0
    assert result.convergence_history == ()
    assert result.metadata == {
        "movement": {
            "allow_corner_cutting": False,
            "connectivity": 4,
            "diagonal_cost": math.sqrt(2),
        }
    }
