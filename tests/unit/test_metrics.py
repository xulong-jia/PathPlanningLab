import math

import pytest

from path_planning.core.metrics import (
    normalized_path_cost,
    path_length,
    turning_count,
)
from path_planning.core.movement import MovementConfig


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ((), 0),
        (((0, 0),), 0),
        (((0, 0), (0, 1)), 0),
        (((0, 0), (0, 1), (0, 2)), 0),
        (((0, 0), (0, 1), (1, 1)), 1),
        (((0, 0), (0, 1), (1, 1), (1, 0)), 2),
    ],
)
def test_turning_count_has_explicit_short_path_behavior(
    path: tuple[tuple[int, int], ...],
    expected: int,
) -> None:
    assert turning_count(path) == expected


def test_path_length_uses_movement_costs() -> None:
    path = ((0, 0), (1, 1), (1, 2))

    assert path_length(path, MovementConfig(8)) == pytest.approx(math.sqrt(2) + 1)


def test_path_length_rejects_invalid_steps() -> None:
    with pytest.raises(ValueError, match="invalid step"):
        path_length(((0, 0), (0, 2)), MovementConfig(4))


@pytest.mark.parametrize(
    ("candidate", "optimal", "expected"),
    [(None, 1.0, None), (1.0, None, None), (0.0, 0.0, 1.0), (6.0, 4.0, 1.5)],
)
def test_normalized_path_cost_handles_null_and_zero_costs(
    candidate: float | None,
    optimal: float | None,
    expected: float | None,
) -> None:
    assert normalized_path_cost(candidate, optimal) == expected


@pytest.mark.parametrize(
    ("candidate", "optimal"),
    [(-1.0, 1.0), (1.0, -1.0), (1.0, 0.0)],
)
def test_normalized_path_cost_rejects_invalid_values(
    candidate: float,
    optimal: float,
) -> None:
    with pytest.raises(ValueError):
        normalized_path_cost(candidate, optimal)
