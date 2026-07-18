import math

from path_planning.core.movement import MovementConfig
from path_planning.core.types import Point


def path_length(path: tuple[Point, ...], movement: MovementConfig) -> float:
    total = 0.0
    for current, following in zip(path, path[1:], strict=False):
        row_delta = abs(following[0] - current[0])
        column_delta = abs(following[1] - current[1])
        if row_delta + column_delta == 1:
            total += 1.0
        elif movement.connectivity == 8 and row_delta == column_delta == 1:
            total += movement.diagonal_cost
        else:
            raise ValueError(f"invalid step: {current} -> {following}")
    return total


def turning_count(path: tuple[Point, ...]) -> int:
    if len(path) < 3:
        return 0
    directions = [
        (following[0] - current[0], following[1] - current[1])
        for current, following in zip(path, path[1:], strict=False)
    ]
    return sum(
        first != second
        for first, second in zip(directions, directions[1:], strict=False)
    )


def normalized_path_cost(
    candidate_cost: float | None,
    optimal_cost: float | None,
) -> float | None:
    if candidate_cost is None or optimal_cost is None:
        return None
    if not math.isfinite(candidate_cost) or candidate_cost < 0:
        raise ValueError("candidate_cost must be finite and non-negative")
    if not math.isfinite(optimal_cost) or optimal_cost < 0:
        raise ValueError("optimal_cost must be finite and non-negative")
    if optimal_cost == 0:
        if candidate_cost == 0:
            return 1.0
        raise ValueError("a positive cost cannot be normalized by zero")
    return candidate_cost / optimal_cost
