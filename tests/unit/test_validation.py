import math

import numpy as np
import pytest

from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.validation import (
    is_reachable,
    validate_endpoints,
    validate_path,
)


@pytest.mark.parametrize(
    ("start", "goal", "expected"),
    [
        ((-1, 0), (1, 1), "start_out_of_bounds"),
        ((0, 0), (2, 1), "goal_out_of_bounds"),
        ((0, 0), (1, 1), "start_blocked"),
        ((1, 1), (0, 0), "goal_blocked"),
    ],
)
def test_validate_endpoints_distinguishes_invalid_cases(
    start: tuple[int, int],
    goal: tuple[int, int],
    expected: str,
) -> None:
    grid = GridMap(np.array([[1, 0], [0, 0]], dtype=bool))

    assert validate_endpoints(grid, start, goal) == expected


def test_validate_endpoints_returns_none_for_valid_points() -> None:
    grid = GridMap(np.zeros((2, 2), dtype=bool))

    assert validate_endpoints(grid, (0, 0), (1, 1)) is None


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ((), "empty_path"),
        (((0, 1), (1, 1)), "wrong_start"),
        (((0, 0), (1, 0)), "wrong_goal"),
        (((0, 0), (0, 2), (1, 1)), "invalid_step"),
    ],
)
def test_validate_path_reports_stable_structural_failures(
    path: tuple[tuple[int, int], ...],
    expected: str,
) -> None:
    grid = GridMap(np.zeros((3, 3), dtype=bool))

    validation = validate_path(
        grid,
        path,
        (0, 0),
        (1, 1),
        MovementConfig(4),
    )

    assert not validation.valid
    assert validation.path_length is None
    assert validation.failure_reason == expected


def test_validate_path_rejects_obstacle_collision() -> None:
    grid = GridMap(np.array([[0, 1], [0, 0]], dtype=bool))

    validation = validate_path(
        grid,
        ((0, 0), (0, 1), (1, 1)),
        (0, 0),
        (1, 1),
        MovementConfig(4),
    )

    assert validation.failure_reason == "path_hits_obstacle"


def test_validate_path_applies_corner_rule() -> None:
    grid = GridMap(np.array([[0, 1], [0, 0]], dtype=bool))
    path = ((0, 0), (1, 1))

    forbidden = validate_path(grid, path, path[0], path[-1], MovementConfig(8))
    allowed = validate_path(
        grid,
        path,
        path[0],
        path[-1],
        MovementConfig(8, allow_corner_cutting=True),
    )

    assert forbidden.failure_reason == "invalid_step"
    assert allowed.valid
    assert allowed.path_length == pytest.approx(math.sqrt(2))


def test_validate_path_computes_four_way_length() -> None:
    grid = GridMap(np.zeros((2, 2), dtype=bool))

    validation = validate_path(
        grid,
        ((0, 0), (0, 1), (1, 1)),
        (0, 0),
        (1, 1),
        MovementConfig(4),
    )

    assert validation.valid
    assert validation.path_length == 2.0
    assert validation.failure_reason is None


def test_reachability_uses_movement_rules_and_terminates_without_path() -> None:
    grid = GridMap(np.array([[0, 1, 0], [0, 1, 0], [0, 1, 0]], dtype=bool))

    assert is_reachable(grid, (0, 0), (2, 0), MovementConfig(4))
    assert not is_reachable(grid, (0, 0), (0, 2), MovementConfig(4))


def test_reachability_handles_start_equal_to_goal() -> None:
    grid = GridMap(np.zeros((1, 1), dtype=bool))

    assert is_reachable(grid, (0, 0), (0, 0), MovementConfig(4))


def test_validate_path_reports_invalid_endpoints_before_path_checks() -> None:
    grid = GridMap(np.zeros((2, 2), dtype=bool))

    validation = validate_path(
        grid,
        ((-1, 0), (1, 1)),
        (-1, 0),
        (1, 1),
        MovementConfig(4),
    )

    assert validation.failure_reason == "start_out_of_bounds"


def test_validate_path_reports_out_of_bounds_internal_point() -> None:
    grid = GridMap(np.zeros((2, 2), dtype=bool))

    validation = validate_path(
        grid,
        ((0, 0), (2, 0), (1, 1)),
        (0, 0),
        (1, 1),
        MovementConfig(4),
    )

    assert validation.failure_reason == "path_out_of_bounds"


def test_reachability_rejects_invalid_endpoints() -> None:
    grid = GridMap(np.zeros((2, 2), dtype=bool))

    assert not is_reachable(grid, (-1, 0), (1, 1), MovementConfig(4))
