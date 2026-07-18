import math
from typing import cast

import numpy as np
import pytest

from path_planning.algorithms.astar import (
    AStarConfig,
    AStarPlanner,
    HeuristicName,
    estimate_cost,
)
from path_planning.algorithms.dijkstra import DijkstraConfig, DijkstraPlanner
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.validation import validate_path


def test_astar_selects_connectivity_compatible_default_heuristics() -> None:
    assert AStarConfig(MovementConfig(4)).heuristic == "manhattan"
    assert AStarConfig(MovementConfig(8)).heuristic == "octile"


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (AStarConfig(MovementConfig(4), "manhattan"), 7.0),
        (AStarConfig(MovementConfig(4), "euclidean"), 5.0),
        (AStarConfig(MovementConfig(8), "octile"), 3 * math.sqrt(2) + 1),
        (AStarConfig(MovementConfig(8, diagonal_cost=1.5), "octile"), 5.5),
        (AStarConfig(MovementConfig(8, diagonal_cost=3.0), "octile"), 7.0),
        (AStarConfig(MovementConfig(8, diagonal_cost=0.5), "octile"), 2.5),
        (
            AStarConfig(MovementConfig(8, diagonal_cost=1.0), "euclidean"),
            5 / math.sqrt(2),
        ),
    ],
)
def test_astar_heuristics_return_admissible_costs_for_configured_movement(
    config: AStarConfig,
    expected: float,
) -> None:
    assert estimate_cost((0, 0), (3, 4), config) == pytest.approx(expected)


@pytest.mark.parametrize(
    "config",
    [
        AStarConfig(MovementConfig(4), "manhattan"),
        AStarConfig(MovementConfig(4), "euclidean"),
        AStarConfig(MovementConfig(8), "octile"),
        AStarConfig(MovementConfig(8), "euclidean"),
    ],
)
def test_astar_matches_dijkstra_cost_and_returns_a_valid_path(
    config: AStarConfig,
) -> None:
    grid = GridMap(np.zeros((5, 5), dtype=bool))
    start = (0, 0)
    goal = (4, 4)

    astar_result = AStarPlanner().plan(grid, start, goal, config, seed=99)
    dijkstra_result = DijkstraPlanner().plan(
        grid,
        start,
        goal,
        DijkstraConfig(config.movement),
    )
    validation = validate_path(
        grid,
        astar_result.path,
        start,
        goal,
        config.movement,
    )

    assert astar_result.success
    assert validation.valid
    assert astar_result.path_length == pytest.approx(dijkstra_result.path_length)
    assert astar_result.path_length == pytest.approx(validation.path_length)
    assert astar_result.expanded_nodes is not None
    assert astar_result.expanded_nodes > 0
    assert astar_result.evaluations is None
    assert astar_result.seed is None
    assert astar_result.metadata["heuristic"] == config.heuristic


@pytest.mark.parametrize(
    "heuristic",
    ["octile", "euclidean"],
)
def test_astar_custom_diagonal_cost_remains_optimal(
    heuristic: HeuristicName,
) -> None:
    grid = GridMap(np.zeros((5, 5), dtype=bool))
    movement = MovementConfig(8, diagonal_cost=0.5)
    config = AStarConfig(movement, heuristic)

    astar_result = AStarPlanner().plan(grid, (0, 0), (3, 4), config)
    dijkstra_result = DijkstraPlanner().plan(
        grid,
        (0, 0),
        (3, 4),
        DijkstraConfig(movement),
    )

    assert astar_result.path_length == pytest.approx(dijkstra_result.path_length)


@pytest.mark.parametrize(
    "config",
    [
        AStarConfig(MovementConfig(8), "octile"),
        AStarConfig(MovementConfig(8), "euclidean"),
    ],
)
def test_astar_returns_explicit_failure_when_no_path_exists(
    config: AStarConfig,
) -> None:
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

    result = AStarPlanner().plan(grid, (0, 0), (0, 2), config)

    assert not result.success
    assert result.path == ()
    assert result.path_length is None
    assert result.failure_reason == "no_path"
    assert result.expanded_nodes == 3


def test_astar_handles_start_equal_to_goal() -> None:
    grid = GridMap(np.zeros((1, 1), dtype=bool))

    result = AStarPlanner().plan(
        grid,
        (0, 0),
        (0, 0),
        AStarConfig(MovementConfig(4)),
    )

    assert result.path == ((0, 0),)
    assert result.path_length == 0.0
    assert result.expanded_nodes == 1


def test_astar_returns_endpoint_validation_failure() -> None:
    grid = GridMap(np.array([[1, 0], [0, 0]], dtype=bool))

    result = AStarPlanner().plan(
        grid,
        (0, 0),
        (1, 1),
        AStarConfig(MovementConfig(4)),
    )

    assert not result.success
    assert result.failure_reason == "start_blocked"
    assert result.expanded_nodes == 0


@pytest.mark.parametrize(
    ("movement", "heuristic"),
    [
        (MovementConfig(8), "manhattan"),
        (MovementConfig(4), "octile"),
        (MovementConfig(4), cast(HeuristicName, "unknown")),
    ],
)
def test_astar_rejects_incompatible_or_unknown_heuristics(
    movement: MovementConfig,
    heuristic: HeuristicName,
) -> None:
    with pytest.raises(ValueError):
        AStarConfig(movement, heuristic)
