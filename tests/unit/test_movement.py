import math

import numpy as np
import pytest

from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig, iter_neighbors


def test_four_way_neighbors_use_unit_cost_and_exclude_obstacles() -> None:
    grid = GridMap(np.array([[0, 0, 0], [0, 0, 1], [0, 0, 0]]))

    neighbors = set(iter_neighbors(grid, (1, 1), MovementConfig(4)))

    assert neighbors == {
        ((0, 1), 1.0),
        ((1, 0), 1.0),
        ((2, 1), 1.0),
    }


def test_neighbors_are_clipped_at_grid_boundary() -> None:
    grid = GridMap(np.zeros((2, 2), dtype=bool))

    neighbors = set(iter_neighbors(grid, (0, 0), MovementConfig(4)))

    assert neighbors == {((0, 1), 1.0), ((1, 0), 1.0)}


def test_eight_way_neighbors_use_configured_diagonal_cost() -> None:
    grid = GridMap(np.zeros((3, 3), dtype=bool))

    neighbors = dict(iter_neighbors(grid, (1, 1), MovementConfig(8)))

    assert len(neighbors) == 8
    assert neighbors[(0, 1)] == 1.0
    assert neighbors[(0, 0)] == pytest.approx(math.sqrt(2))


def test_diagonal_corner_cutting_is_disabled_by_default() -> None:
    grid = GridMap(np.array([[0, 1], [0, 0]], dtype=bool))

    neighbors = dict(iter_neighbors(grid, (0, 0), MovementConfig(8)))

    assert (1, 1) not in neighbors


def test_diagonal_corner_cutting_can_be_enabled() -> None:
    grid = GridMap(np.array([[0, 1], [0, 0]], dtype=bool))

    neighbors = dict(
        iter_neighbors(
            grid,
            (0, 0),
            MovementConfig(8, allow_corner_cutting=True),
        )
    )

    assert neighbors[(1, 1)] == pytest.approx(math.sqrt(2))
    assert (0, 1) not in neighbors


@pytest.mark.parametrize(
    ("connectivity", "diagonal_cost"),
    [(5, math.sqrt(2)), (8, 0.0), (8, -1.0), (8, math.nan)],
)
def test_movement_config_rejects_invalid_values(
    connectivity: int,
    diagonal_cost: float,
) -> None:
    with pytest.raises(ValueError):
        MovementConfig(connectivity, diagonal_cost)  # type: ignore[arg-type]


def test_neighbor_expansion_rejects_blocked_origin() -> None:
    grid = GridMap(np.array([[1, 0], [0, 0]], dtype=bool))

    with pytest.raises(ValueError, match="blocked"):
        tuple(iter_neighbors(grid, (0, 0), MovementConfig(4)))


def test_neighbor_expansion_rejects_out_of_bounds_origin() -> None:
    grid = GridMap(np.zeros((2, 2), dtype=bool))

    with pytest.raises(ValueError, match="outside"):
        tuple(iter_neighbors(grid, (2, 0), MovementConfig(4)))
