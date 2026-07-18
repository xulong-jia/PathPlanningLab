import random
from dataclasses import replace

import numpy as np
import pytest

from path_planning.algorithms import genetic
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.types import Point
from path_planning.core.validation import validate_path

MOVEMENT = MovementConfig(4)


def _config(**overrides: object) -> genetic.GAConfig:
    values = {
        "movement": MOVEMENT,
        "population_size": 20,
        "generations": 30,
        "crossover_probability": 1.0,
        "mutation_probability": 1.0,
        "tournament_size": 3,
        "elite_size": 2,
        "max_initialization_steps": 200,
        "initialization_attempts": 4,
        "stagnation_generations": 10,
        "path_length_penalty": 1.0,
        "turn_penalty": 0.25,
        "repeat_penalty": 2.0,
        "unreachable_base_penalty": 100.0,
        "collision_penalty": 10.0,
        "remaining_distance_penalty": 3.0,
    }
    values.update(overrides)
    return genetic.GAConfig(**values)  # type: ignore[arg-type]


def _assert_legal(
    grid: GridMap,
    path: tuple[Point, ...],
    start: Point,
    goal: Point,
) -> None:
    assert path[0] == start
    assert path[-1] == goal
    assert len(path) == len(set(path))
    assert validate_path(grid, path, start, goal, MOVEMENT).valid


def test_repair_erases_loops_and_reconnects_first_invalid_segment() -> None:
    grid = GridMap(np.zeros((3, 4), dtype=bool))
    original = [
        (0, 0),
        (0, 1),
        (0, 0),
        (0, 1),
        (2, 1),
        (2, 2),
        (2, 3),
    ]
    snapshot = original.copy()

    repaired = genetic.repair_path(
        original,
        grid,
        (0, 0),
        (2, 3),
        MOVEMENT,
        max_steps=50,
        rng=random.Random(11),
    )

    assert repaired is not None
    assert repaired != tuple(original)
    _assert_legal(grid, repaired, (0, 0), (2, 3))
    assert original == snapshot


def test_repair_failure_is_bounded_and_does_not_modify_input() -> None:
    grid = GridMap(np.array([[0, 1, 0]], dtype=bool))
    original = [(0, 0), (0, 2)]
    snapshot = original.copy()

    repaired = genetic.repair_path(
        original,
        grid,
        (0, 0),
        (0, 2),
        MOVEMENT,
        max_steps=1,
        rng=random.Random(5),
    )

    assert repaired is None
    assert original == snapshot


def test_common_node_changes_legal_children_without_parent_pollution() -> None:
    grid = GridMap(np.zeros((4, 4), dtype=bool))
    parent_a = [(0, 0), (0, 1), (1, 1), (1, 2), (1, 3), (2, 3), (3, 3)]
    parent_b = [(0, 0), (1, 0), (1, 1), (2, 1), (2, 2), (2, 3), (3, 3)]
    snapshots = parent_a.copy(), parent_b.copy()

    outcome = genetic.apply_crossover(
        parent_a,
        parent_b,
        grid,
        (0, 0),
        (3, 3),
        _config(crossover_method="common_node"),
        random.Random(3),
    )

    child_a, child_b = outcome.child_a, outcome.child_b
    assert outcome.status == "succeeded"
    assert (tuple(child_a), tuple(child_b)) != (tuple(parent_a), tuple(parent_b))
    _assert_legal(grid, tuple(child_a), (0, 0), (3, 3))
    _assert_legal(grid, tuple(child_b), (0, 0), (3, 3))
    assert (parent_a, parent_b) == snapshots


def test_splice_repair_crossover_changes_and_repairs_children() -> None:
    grid = GridMap(np.zeros((5, 5), dtype=bool))
    parent_a = [(0, index) for index in range(5)] + [
        (index, 4) for index in range(1, 5)
    ]
    parent_b = [(index, 0) for index in range(5)] + [
        (4, index) for index in range(1, 5)
    ]
    snapshots = parent_a.copy(), parent_b.copy()

    outcome = genetic.apply_crossover(
        parent_a,
        parent_b,
        grid,
        (0, 0),
        (4, 4),
        _config(crossover_method="splice_repair"),
        random.Random(9),
    )

    child_a, child_b = outcome.child_a, outcome.child_b
    assert outcome.status == "succeeded"
    assert (tuple(child_a), tuple(child_b)) != (tuple(parent_a), tuple(parent_b))
    _assert_legal(grid, tuple(child_a), (0, 0), (4, 4))
    _assert_legal(grid, tuple(child_b), (0, 0), (4, 4))
    assert (parent_a, parent_b) == snapshots


def test_failed_splice_repair_returns_copies_of_both_parents() -> None:
    grid = GridMap(
        np.array(
            [
                [0, 0, 0],
                [1, 1, 1],
                [0, 0, 0],
            ],
            dtype=bool,
        )
    )
    parent_a = [(0, 0), (0, 1), (0, 2), (2, 2)]
    parent_b = [(0, 0), (2, 0), (2, 1), (2, 2)]

    outcome = genetic.apply_crossover(
        parent_a,
        parent_b,
        grid,
        (0, 0),
        (2, 2),
        _config(crossover_method="splice_repair", max_initialization_steps=1),
        random.Random(2),
    )

    child_a, child_b = outcome.child_a, outcome.child_b
    assert outcome.status == "failed"
    assert tuple(child_a) == tuple(parent_a)
    assert tuple(child_b) == tuple(parent_b)
    assert child_a is not parent_a
    assert child_b is not parent_b


def test_reroute_segment_mutation_rate_one_changes_a_legal_path() -> None:
    grid = GridMap(np.zeros((4, 4), dtype=bool))
    parent = [(0, index) for index in range(4)] + [(index, 3) for index in range(1, 4)]
    snapshot = parent.copy()

    outcome = genetic.apply_mutation(
        parent,
        grid,
        (0, 0),
        (3, 3),
        _config(mutation_method="reroute_segment"),
        random.Random(17),
    )

    child = outcome.child
    assert outcome.status == "succeeded"
    assert tuple(child) != tuple(parent)
    _assert_legal(grid, tuple(child), (0, 0), (3, 3))
    assert parent == snapshot


def test_shortcut_mutation_rate_one_removes_a_legal_detour() -> None:
    grid = GridMap(np.zeros((3, 2), dtype=bool))
    parent = [(0, 0), (0, 1), (1, 1), (1, 0), (2, 0)]
    snapshot = parent.copy()

    outcome = genetic.apply_mutation(
        parent,
        grid,
        (0, 0),
        (2, 0),
        _config(mutation_method="shortcut"),
        random.Random(23),
    )

    child = outcome.child
    assert outcome.status == "succeeded"
    assert len(child) < len(parent)
    _assert_legal(grid, tuple(child), (0, 0), (2, 0))
    assert parent == snapshot


def test_failed_mutation_returns_a_parent_copy() -> None:
    grid = GridMap(np.zeros((1, 2), dtype=bool))
    parent = [(0, 0), (0, 1)]

    outcome = genetic.apply_mutation(
        parent,
        grid,
        (0, 0),
        (0, 1),
        _config(mutation_method="shortcut"),
        random.Random(29),
    )

    child = outcome.child
    assert outcome.status == "failed"
    assert tuple(child) == tuple(parent)
    assert child is not parent


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("crossover_method", "single_point"),
        ("mutation_method", "swap"),
    ],
)
def test_ga_config_rejects_unknown_operator_methods(field: str, value: str) -> None:
    with pytest.raises(ValueError, match=field):
        replace(_config(), **{field: value})


def test_operators_do_not_advance_global_random_state() -> None:
    grid = GridMap(np.zeros((3, 2), dtype=bool))
    parent = [(0, 0), (0, 1), (1, 1), (1, 0), (2, 0)]
    random.seed(991)
    global_state = random.getstate()

    genetic.apply_mutation(
        parent,
        grid,
        (0, 0),
        (2, 0),
        _config(mutation_method="shortcut"),
        random.Random(31),
    )

    assert random.getstate() == global_state


def test_crossover_outcomes_distinguish_skip_failure_and_success() -> None:
    grid = GridMap(np.zeros((5, 5), dtype=bool))
    parent_a = [(0, index) for index in range(5)] + [
        (index, 4) for index in range(1, 5)
    ]
    parent_b = [(index, 0) for index in range(5)] + [
        (4, index) for index in range(1, 5)
    ]

    skipped = genetic.apply_crossover(
        parent_a,
        parent_b,
        grid,
        (0, 0),
        (4, 4),
        _config(crossover_probability=0.0, crossover_method="splice_repair"),
        random.Random(41),
    )
    succeeded = genetic.apply_crossover(
        parent_a,
        parent_b,
        grid,
        (0, 0),
        (4, 4),
        _config(crossover_method="splice_repair"),
        random.Random(9),
    )

    blocked_grid = GridMap(np.array([[0, 1, 0]], dtype=bool))
    failed = genetic.apply_crossover(
        [(0, 0), (0, 2)],
        [(0, 0), (0, 2)],
        blocked_grid,
        (0, 0),
        (0, 2),
        _config(crossover_method="splice_repair", max_initialization_steps=1),
        random.Random(43),
    )
    assert skipped.status == "skipped"
    assert (skipped.repair_successes, skipped.repair_failures) == (0, 0)
    assert tuple(skipped.child_a) == tuple(parent_a)
    assert tuple(skipped.child_b) == tuple(parent_b)
    assert skipped.child_a is not parent_a
    assert skipped.child_b is not parent_b
    assert succeeded.status == "succeeded"
    assert (succeeded.repair_successes, succeeded.repair_failures) == (2, 0)
    assert failed.status == "failed"
    assert (failed.repair_successes, failed.repair_failures) == (0, 2)


def test_splice_repair_outcome_reports_both_repair_attempts() -> None:
    grid = GridMap(np.zeros((5, 5), dtype=bool))
    parent_a = [(0, index) for index in range(5)] + [
        (index, 4) for index in range(1, 5)
    ]
    parent_b = [(index, 0) for index in range(5)] + [
        (4, index) for index in range(1, 5)
    ]
    direct_success = genetic.splice_repair(
        parent_a,
        parent_b,
        grid,
        (0, 0),
        (4, 4),
        MOVEMENT,
        200,
        random.Random(9),
    )
    blocked_grid = GridMap(np.array([[0, 1, 0]], dtype=bool))
    direct_failure = genetic.splice_repair(
        [(0, 0), (0, 2)],
        [(0, 0), (0, 2)],
        blocked_grid,
        (0, 0),
        (0, 2),
        MOVEMENT,
        1,
        random.Random(43),
    )

    assert direct_success.children is not None
    assert (direct_success.repair_successes, direct_success.repair_failures) == (2, 0)
    assert direct_failure.children is None
    assert (direct_failure.repair_successes, direct_failure.repair_failures) == (0, 2)


def test_mutation_outcomes_distinguish_skip_failure_and_success() -> None:
    grid = GridMap(np.zeros((3, 2), dtype=bool))
    detour = [(0, 0), (0, 1), (1, 1), (1, 0), (2, 0)]

    skipped = genetic.apply_mutation(
        detour,
        grid,
        (0, 0),
        (2, 0),
        _config(mutation_probability=0.0, mutation_method="shortcut"),
        random.Random(47),
    )
    failed = genetic.apply_mutation(
        [(0, 0), (0, 1)],
        GridMap(np.zeros((1, 2), dtype=bool)),
        (0, 0),
        (0, 1),
        _config(mutation_method="shortcut"),
        random.Random(53),
    )
    succeeded = genetic.apply_mutation(
        detour,
        grid,
        (0, 0),
        (2, 0),
        _config(mutation_method="shortcut"),
        random.Random(59),
    )

    assert skipped.status == "skipped"
    assert tuple(skipped.child) == tuple(detour)
    assert skipped.child is not detour
    assert failed.status == "failed"
    assert succeeded.status == "succeeded"
