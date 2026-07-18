import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from path_planning.core.grid import GridMap
from path_planning.core.types import Point

Connectivity = Literal[4, 8]

_CARDINAL_OFFSETS = ((-1, 0), (0, 1), (1, 0), (0, -1))
_DIAGONAL_OFFSETS = ((-1, -1), (-1, 1), (1, 1), (1, -1))


@dataclass(frozen=True, slots=True)
class MovementConfig:
    connectivity: Connectivity
    diagonal_cost: float = math.sqrt(2)
    allow_corner_cutting: bool = False

    def __post_init__(self) -> None:
        if self.connectivity not in (4, 8):
            raise ValueError("connectivity must be 4 or 8")
        if not math.isfinite(self.diagonal_cost) or self.diagonal_cost <= 0:
            raise ValueError("diagonal_cost must be finite and positive")


def iter_neighbors(
    grid: GridMap,
    point: Point,
    config: MovementConfig,
) -> Iterator[tuple[Point, float]]:
    if not grid.is_within(point):
        raise ValueError(f"point is outside grid bounds: {point}")
    if grid.is_blocked(point):
        raise ValueError(f"cannot expand blocked point: {point}")

    row, column = point
    offsets: tuple[tuple[int, int], ...] = _CARDINAL_OFFSETS
    if config.connectivity == 8:
        offsets += _DIAGONAL_OFFSETS

    for row_delta, column_delta in offsets:
        neighbor = row + row_delta, column + column_delta
        if not grid.is_within(neighbor) or grid.is_blocked(neighbor):
            continue

        is_diagonal = row_delta != 0 and column_delta != 0
        if is_diagonal and not config.allow_corner_cutting:
            side_a = row + row_delta, column
            side_b = row, column + column_delta
            if grid.is_blocked(side_a) or grid.is_blocked(side_b):
                continue

        yield neighbor, config.diagonal_cost if is_diagonal else 1.0
