import numpy as np
import pytest

from path_planning.core.grid import GridMap


@pytest.mark.parametrize(
    "cells",
    [np.array([0, 1]), np.zeros((2, 2, 2)), np.zeros((0, 2))],
)
def test_grid_rejects_non_two_dimensional_or_empty_input(
    cells: np.ndarray,
) -> None:
    with pytest.raises(ValueError):
        GridMap(cells)


def test_grid_rejects_non_numeric_input() -> None:
    with pytest.raises(TypeError):
        GridMap(np.array([["free", "blocked"]]))


def test_grid_rejects_non_finite_input() -> None:
    with pytest.raises(ValueError, match="finite"):
        GridMap(np.array([[np.nan]]))


def test_grid_copies_and_normalizes_input() -> None:
    cells = np.array([[0, 2], [0, 0]], dtype=np.int64)

    grid = GridMap(cells)
    cells[0, 1] = 0

    assert grid.shape == (2, 2)
    assert grid.free_cell_count == 3
    assert grid.is_blocked((0, 1))
    assert grid.cells.dtype == np.bool_
    with pytest.raises(ValueError):
        grid.cells[0, 0] = True


@pytest.mark.parametrize("point", [(-1, 0), (2, 0), (0, 2)])
def test_grid_reports_points_outside_bounds(point: tuple[int, int]) -> None:
    grid = GridMap(np.zeros((2, 2), dtype=bool))

    assert not grid.is_within(point)
    with pytest.raises(ValueError):
        grid.is_blocked(point)


@pytest.mark.parametrize("point", [(0,), (0, 1, 2), ("0", 1), (True, 1)])
def test_grid_rejects_malformed_points(point: object) -> None:
    grid = GridMap(np.zeros((2, 2), dtype=bool))

    with pytest.raises((TypeError, ValueError)):
        grid.is_within(point)  # type: ignore[arg-type]
