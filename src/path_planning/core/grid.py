from numbers import Integral

import numpy as np
from numpy.typing import ArrayLike, NDArray

from path_planning.core.types import Point


class GridMap:
    """A copied, read-only two-dimensional obstacle grid."""

    __slots__ = ("_cells",)

    def __init__(self, cells: ArrayLike) -> None:
        array = np.asarray(cells)
        if array.ndim != 2 or 0 in array.shape:
            raise ValueError("grid cells must be a non-empty two-dimensional array")
        if array.dtype.kind not in "biuf":
            raise TypeError("grid cells must have a boolean or real numeric dtype")
        if array.dtype.kind == "f" and not np.isfinite(array).all():
            raise ValueError("grid cells must contain only finite values")

        normalized = np.array(array, dtype=np.bool_, copy=True)
        normalized.setflags(write=False)
        self._cells: NDArray[np.bool_] = normalized

    @property
    def cells(self) -> NDArray[np.bool_]:
        view = self._cells.view()
        view.setflags(write=False)
        return view

    @property
    def shape(self) -> tuple[int, int]:
        rows, columns = self._cells.shape
        return int(rows), int(columns)

    @property
    def free_cell_count(self) -> int:
        return int(np.count_nonzero(~self._cells))

    def is_within(self, point: Point) -> bool:
        row, column = self._validated_point(point)
        rows, columns = self.shape
        return 0 <= row < rows and 0 <= column < columns

    def is_blocked(self, point: Point) -> bool:
        row, column = self._validated_point(point)
        if not self.is_within((row, column)):
            raise ValueError(f"point is outside grid bounds: {(row, column)}")
        return bool(self._cells[row, column])

    @staticmethod
    def _validated_point(point: Point) -> Point:
        if not isinstance(point, tuple) or len(point) != 2:
            raise TypeError("point must be a two-item tuple")
        if any(
            isinstance(value, bool) or not isinstance(value, Integral)
            for value in point
        ):
            raise TypeError("point coordinates must be integers")
        return int(point[0]), int(point[1])
