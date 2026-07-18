import random
from dataclasses import replace

import numpy as np

from path_planning.algorithms import GAConfig, GeneticPlanner
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.result import PlanningResult
from path_planning.core.types import JsonValue


def _config() -> GAConfig:
    return GAConfig(
        movement=MovementConfig(4),
        population_size=4,
        generations=2,
        crossover_probability=0.5,
        mutation_probability=0.5,
        tournament_size=2,
        elite_size=1,
        max_initialization_steps=100,
        initialization_attempts=2,
        stagnation_generations=3,
        path_length_penalty=1.0,
        turn_penalty=0.25,
        repeat_penalty=2.0,
        unreachable_base_penalty=1_000.0,
        collision_penalty=10.0,
        remaining_distance_penalty=3.0,
    )


def _without_runtime(result: PlanningResult) -> dict[str, JsonValue]:
    payload = result.to_dict()
    payload.pop("runtime_ms")
    return payload


def test_same_seed_reproduces_all_non_time_ga_results() -> None:
    grid = GridMap(np.zeros((4, 4), dtype=bool))
    planner = GeneticPlanner()

    first = planner.plan(grid, (0, 0), (3, 3), _config(), seed=101)
    second = planner.plan(grid, (0, 0), (3, 3), _config(), seed=101)

    assert _without_runtime(first) == _without_runtime(second)


def test_different_seeds_change_actual_ga_trajectory_digest() -> None:
    grid = GridMap(np.zeros((6, 6), dtype=bool))
    planner = GeneticPlanner()

    first = planner.plan(grid, (0, 0), (5, 5), _config(), seed=1)
    second = planner.plan(grid, (0, 0), (5, 5), _config(), seed=2)

    assert first.metadata["trajectory_digest"] != second.metadata["trajectory_digest"]


def test_trajectory_digest_depends_on_executed_trajectory_not_only_seed() -> None:
    grid = GridMap(np.zeros((6, 6), dtype=bool))
    planner = GeneticPlanner()
    short = replace(_config(), generations=1)
    long = replace(_config(), generations=2)

    first = planner.plan(grid, (0, 0), (5, 5), short, seed=37)
    second = planner.plan(grid, (0, 0), (5, 5), long, seed=37)

    assert first.iterations == 1
    assert second.iterations == 2
    assert first.metadata["trajectory_digest"] != second.metadata["trajectory_digest"]


def test_ga_local_random_hierarchy_does_not_advance_global_random() -> None:
    grid = GridMap(np.zeros((4, 4), dtype=bool))
    random.seed(1234)
    expected = random.random()
    random.seed(1234)

    GeneticPlanner().plan(grid, (0, 0), (3, 3), _config(), seed=41)

    assert random.random() == expected
