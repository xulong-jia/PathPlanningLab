import importlib
import math
import random
from dataclasses import replace

import numpy as np
import pytest
from deap import base

from path_planning.algorithms import genetic
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.validation import validate_path


def _config(**overrides: object) -> genetic.GAConfig:
    values = {
        "movement": MovementConfig(4),
        "population_size": 20,
        "generations": 30,
        "crossover_probability": 0.8,
        "mutation_probability": 0.2,
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


def test_deap_creator_types_survive_repeated_import() -> None:
    fitness_type = genetic.GAFitness
    individual_type = genetic.GAIndividual

    reloaded = importlib.reload(genetic)

    assert reloaded.GAFitness is fitness_type
    assert reloaded.GAIndividual is individual_type
    assert reloaded.GAFitness.weights == (-1.0,)


def test_individual_decodes_to_coordinate_path() -> None:
    individual = genetic.GAIndividual([(0, 0), (0, 1), (1, 1)])

    assert genetic.decode_individual(individual) == (
        (0, 0),
        (0, 1),
        (1, 1),
    )


def test_toolbox_initializes_a_legal_simple_path_without_global_random() -> None:
    grid = GridMap(
        np.array(
            [
                [0, 0, 0, 0],
                [1, 1, 0, 1],
                [0, 0, 0, 0],
                [0, 1, 1, 0],
            ],
            dtype=bool,
        )
    )
    config = _config()
    random.seed(991)
    global_state = random.getstate()

    toolbox = genetic.build_toolbox(grid, (0, 0), (3, 3), config, seed=7)
    individual = toolbox.individual()
    path = genetic.decode_individual(individual)

    assert isinstance(toolbox, base.Toolbox)
    assert isinstance(individual, genetic.GAIndividual)
    assert isinstance(individual.fitness, genetic.GAFitness)
    assert path[0] == (0, 0)
    assert path[-1] == (3, 3)
    assert len(path) == len(set(path))
    assert validate_path(grid, path, (0, 0), (3, 3), config.movement).valid
    assert random.getstate() == global_state


def test_shorter_legal_path_has_better_fitness_than_longer_path() -> None:
    grid = GridMap(np.zeros((3, 3), dtype=bool))
    config = _config()
    config.validate_for_grid(grid)
    short = genetic.GAIndividual([(0, 0), (0, 1), (0, 2)])
    long = genetic.GAIndividual([(0, 0), (1, 0), (1, 1), (0, 1), (0, 2)])

    short_fitness = genetic.evaluate_individual(short, grid, (0, 0), (0, 2), config)
    long_fitness = genetic.evaluate_individual(long, grid, (0, 0), (0, 2), config)

    assert short_fitness < long_fitness


def test_repeat_penalty_changes_only_repeated_node_cost() -> None:
    grid = GridMap(np.zeros((2, 3), dtype=bool))
    repeated = genetic.GAIndividual([(0, 0), (0, 1), (0, 0), (0, 1), (0, 2)])
    without_penalty = genetic.evaluate_individual(
        repeated,
        grid,
        (0, 0),
        (0, 2),
        _config(repeat_penalty=0.0),
    )
    with_penalty = genetic.evaluate_individual(
        repeated,
        grid,
        (0, 0),
        (0, 2),
        _config(repeat_penalty=5.0),
    )

    assert with_penalty[0] - without_penalty[0] == 10.0


def test_collision_penalty_changes_only_collision_cost() -> None:
    grid = GridMap(np.zeros((1, 3), dtype=bool))
    illegal_jump = genetic.GAIndividual([(0, 0), (0, 2)])
    without_penalty = genetic.evaluate_individual(
        illegal_jump,
        grid,
        (0, 0),
        (0, 2),
        _config(collision_penalty=0.0),
    )
    with_penalty = genetic.evaluate_individual(
        illegal_jump,
        grid,
        (0, 0),
        (0, 2),
        _config(collision_penalty=7.0),
    )

    assert with_penalty[0] - without_penalty[0] == 7.0


def test_remaining_distance_penalty_changes_only_goal_distance_cost() -> None:
    grid = GridMap(np.zeros((1, 4), dtype=bool))
    unfinished = genetic.GAIndividual([(0, 0), (0, 1)])
    without_penalty = genetic.evaluate_individual(
        unfinished,
        grid,
        (0, 0),
        (0, 3),
        _config(remaining_distance_penalty=0.0),
    )
    with_penalty = genetic.evaluate_individual(
        unfinished,
        grid,
        (0, 0),
        (0, 3),
        _config(remaining_distance_penalty=4.0),
    )

    assert with_penalty[0] - without_penalty[0] == 8.0


@pytest.mark.parametrize(
    ("path_length_penalty", "turn_penalty", "unreachable_base_penalty"),
    [(0.0, 0.0, 1.0), (1.0, 0.25, 100.0), (20.0, 30.0, 1000.0)],
)
def test_invalid_individual_is_always_worse_than_a_legal_individual(
    path_length_penalty: float,
    turn_penalty: float,
    unreachable_base_penalty: float,
) -> None:
    grid = GridMap(np.zeros((3, 3), dtype=bool))
    config = _config(
        path_length_penalty=path_length_penalty,
        turn_penalty=turn_penalty,
        unreachable_base_penalty=unreachable_base_penalty,
    )
    config.validate_for_grid(grid)
    legal = genetic.GAIndividual([(0, 0), (0, 1), (0, 2)])
    invalid = genetic.GAIndividual([(0, 0), (1, 1), (0, 2)])

    legal_fitness = genetic.evaluate_individual(legal, grid, (0, 0), (0, 2), config)
    invalid_fitness = genetic.evaluate_individual(invalid, grid, (0, 0), (0, 2), config)

    assert invalid_fitness > legal_fitness


def test_diagonal_rounding_keeps_invalid_fitness_strictly_worse() -> None:
    cells = np.ones((8, 8), dtype=bool)
    np.fill_diagonal(cells, False)
    grid = GridMap(cells)
    movement = MovementConfig(8, allow_corner_cutting=True)
    provisional = _config(
        movement=movement,
        turn_penalty=0.0,
        repeat_penalty=0.0,
        collision_penalty=0.0,
        remaining_distance_penalty=0.0,
    )
    upper_bound = genetic.legal_fitness_upper_bound(grid, provisional)
    config = replace(
        provisional,
        unreachable_base_penalty=math.nextafter(upper_bound, math.inf),
    )
    config.validate_for_grid(grid)
    legal = genetic.GAIndividual([(index, index) for index in range(8)])
    invalid = genetic.GAIndividual([])

    legal_fitness = genetic.evaluate_individual(legal, grid, (0, 0), (7, 7), config)
    invalid_fitness = genetic.evaluate_individual(invalid, grid, (0, 0), (7, 7), config)

    assert legal_fitness < invalid_fitness


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("population_size", 0),
        ("generations", 0),
        ("crossover_probability", 1.1),
        ("mutation_probability", -0.1),
        ("tournament_size", 1),
        ("elite_size", -1),
        ("max_initialization_steps", 0),
        ("initialization_attempts", 0),
        ("stagnation_generations", 0),
        ("path_length_penalty", -1.0),
        ("turn_penalty", float("inf")),
        ("repeat_penalty", -1.0),
        ("unreachable_base_penalty", 0.0),
        ("collision_penalty", -1.0),
        ("remaining_distance_penalty", -1.0),
    ],
)
def test_ga_config_rejects_unsafe_values(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        replace(_config(), **{field: value})


def test_grid_validation_rejects_non_dominating_invalid_base_penalty() -> None:
    grid = GridMap(np.zeros((3, 3), dtype=bool))
    upper_bound = genetic.legal_fitness_upper_bound(grid, _config())

    with pytest.raises(ValueError, match="unreachable_base_penalty"):
        replace(
            _config(),
            unreachable_base_penalty=upper_bound,
        ).validate_for_grid(grid)
