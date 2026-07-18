import hashlib

import numpy as np
import pytest

from path_planning.algorithms.aco import ACOConfig, AntColonyPlanner
from path_planning.algorithms.base import Planner
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.validation import validate_path


def _config(**overrides: object) -> ACOConfig:
    values = {
        "movement": MovementConfig(4),
        "ants": 3,
        "alpha": 1.0,
        "beta": 3.0,
        "evaporation_rate": 0.2,
        "pheromone_deposit": 1.0,
        "elite_weight": 2.0,
        "min_pheromone": 0.01,
        "max_pheromone": 10.0,
        "iterations": 4,
        "max_steps": 100,
        "max_restarts": 1,
        "max_backtracks": 100,
        "stagnation_iterations": 10,
    }
    values.update(overrides)
    return ACOConfig(**values)  # type: ignore[arg-type]


def test_aco_planner_returns_a_valid_unified_result_and_budget_metadata() -> None:
    grid = GridMap(np.zeros((5, 5), dtype=bool))
    config = _config()
    planner = AntColonyPlanner()

    result = planner.plan(grid, (0, 0), (4, 4), config, seed=42)

    assert isinstance(planner, Planner)
    assert result.algorithm == "aco"
    assert result.success
    assert validate_path(grid, result.path, (0, 0), (4, 4), config.movement).valid
    assert result.path_length is not None
    assert result.expanded_nodes is None
    assert result.evaluations == config.ants * config.iterations
    assert result.iterations == config.iterations
    assert len(result.convergence_history) == config.iterations
    assert all(value is not None for value in result.convergence_history)
    assert result.seed == 42
    assert result.metadata["constructed_paths"] == result.evaluations
    assert result.metadata["successful_paths"] == result.evaluations
    assert result.metadata["construction_steps"] > 0
    assert result.metadata["config"] == {
        "alpha": 1.0,
        "ants": 3,
        "beta": 3.0,
        "elite_weight": 2.0,
        "evaporation_rate": 0.2,
        "iterations": 4,
        "max_backtracks": 100,
        "max_pheromone": 10.0,
        "max_restarts": 1,
        "max_steps": 100,
        "min_pheromone": 0.01,
        "pheromone_deposit": 1.0,
        "stagnation_iterations": 10,
    }
    digest = result.metadata["trajectory_digest"]
    assert isinstance(digest, str)
    assert len(digest) == hashlib.sha256().digest_size * 2


@pytest.mark.parametrize(
    ("ants", "iterations"),
    [(1, 2), (4, 3)],
)
def test_aco_ants_and_iterations_control_constructed_path_budget(
    ants: int,
    iterations: int,
) -> None:
    grid = GridMap(np.zeros((3, 3), dtype=bool))
    config = _config(
        ants=ants,
        iterations=iterations,
        stagnation_iterations=iterations + 1,
    )

    result = AntColonyPlanner().plan(grid, (0, 0), (2, 2), config, seed=7)

    assert result.evaluations == ants * iterations
    assert result.metadata["constructed_paths"] == ants * iterations
    assert result.iterations == iterations


def test_aco_step_budget_failure_stops_at_stagnation_limit() -> None:
    grid = GridMap(np.zeros((1, 4), dtype=bool))
    config = _config(
        ants=2,
        iterations=10,
        max_steps=1,
        max_restarts=0,
        max_backtracks=0,
        stagnation_iterations=2,
    )

    result = AntColonyPlanner().plan(grid, (0, 0), (0, 3), config, seed=5)

    assert not result.success
    assert result.failure_reason == "construction_failed"
    assert result.iterations == 2
    assert result.evaluations == 4
    assert result.convergence_history == (None, None)
    assert result.metadata["construction_steps"] == 4
    assert result.metadata["restarts"] == 0
    assert result.metadata["backtracks"] == 0


def test_aco_handles_start_equal_to_goal_without_running_iterations() -> None:
    grid = GridMap(np.zeros((1, 1), dtype=bool))

    result = AntColonyPlanner().plan(
        grid,
        (0, 0),
        (0, 0),
        _config(),
        seed=11,
    )

    assert result.success
    assert result.path == ((0, 0),)
    assert result.path_length == 0.0
    assert result.evaluations == 0
    assert result.iterations == 0
    assert result.convergence_history == ()
    assert result.seed == 11


def test_aco_returns_shared_endpoint_failure_without_constructing_paths() -> None:
    grid = GridMap(np.zeros((2, 2), dtype=bool))

    result = AntColonyPlanner().plan(
        grid,
        (-1, 0),
        (1, 1),
        _config(),
        seed=3,
    )

    assert not result.success
    assert result.failure_reason == "start_out_of_bounds"
    assert result.evaluations == 0
    assert result.metadata["constructed_paths"] == 0
