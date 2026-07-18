import numpy as np

from path_planning.algorithms.aco import ACOConfig, AntColonyPlanner
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.result import PlanningResult
from path_planning.core.types import JsonValue


def _config() -> ACOConfig:
    return ACOConfig(
        movement=MovementConfig(4),
        ants=4,
        alpha=1.0,
        beta=2.0,
        evaporation_rate=0.2,
        pheromone_deposit=1.0,
        elite_weight=2.0,
        min_pheromone=0.01,
        max_pheromone=10.0,
        iterations=4,
        max_steps=100,
        max_restarts=1,
        max_backtracks=100,
        stagnation_iterations=5,
    )


def _without_runtime(result: PlanningResult) -> dict[str, JsonValue]:
    payload = result.to_dict()
    payload.pop("runtime_ms")
    return payload


def test_same_seed_reproduces_all_non_time_aco_results() -> None:
    grid = GridMap(np.zeros((6, 6), dtype=bool))
    planner = AntColonyPlanner()

    first = planner.plan(grid, (0, 0), (5, 5), _config(), seed=101)
    second = planner.plan(grid, (0, 0), (5, 5), _config(), seed=101)

    assert _without_runtime(first) == _without_runtime(second)


def test_different_seeds_change_sampling_trajectory_digest() -> None:
    grid = GridMap(np.zeros((6, 6), dtype=bool))
    planner = AntColonyPlanner()

    first = planner.plan(grid, (0, 0), (5, 5), _config(), seed=1)
    second = planner.plan(grid, (0, 0), (5, 5), _config(), seed=2)

    assert first.metadata["trajectory_digest"] != second.metadata["trajectory_digest"]


def test_aco_local_generator_does_not_advance_numpy_global_rng() -> None:
    grid = GridMap(np.zeros((4, 4), dtype=bool))
    np.random.seed(1234)
    expected = float(np.random.random())
    np.random.seed(1234)

    AntColonyPlanner().plan(grid, (0, 0), (3, 3), _config(), seed=9)

    assert float(np.random.random()) == expected
