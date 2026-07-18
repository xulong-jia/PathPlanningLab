from dataclasses import replace

import numpy as np
import pytest

from path_planning.algorithms.aco import (
    ACOConfig,
    _construct_ant_path,
    _initialize_pheromone,
    _precheck_failure,
    _transition_weights,
)
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.validation import validate_path


def _config(**overrides: object) -> ACOConfig:
    values = {
        "movement": MovementConfig(4),
        "ants": 4,
        "alpha": 1.0,
        "beta": 2.0,
        "evaporation_rate": 0.25,
        "pheromone_deposit": 1.0,
        "elite_weight": 2.0,
        "min_pheromone": 0.01,
        "max_pheromone": 10.0,
        "iterations": 5,
        "max_steps": 50,
        "max_restarts": 1,
        "max_backtracks": 20,
        "stagnation_iterations": 3,
    }
    values.update(overrides)
    return ACOConfig(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("movement", "movement_count"),
    [(MovementConfig(4), 4), (MovementConfig(8), 8)],
)
def test_pheromone_tensor_matches_grid_and_movement_count(
    movement: MovementConfig,
    movement_count: int,
) -> None:
    grid = GridMap(np.zeros((3, 5), dtype=bool))

    pheromone = _initialize_pheromone(grid, _config(movement=movement))

    assert pheromone.shape == (3, 5, movement_count)
    assert np.all(pheromone == 1.0)


def test_transition_weights_use_pheromone_and_goal_heuristic_exponents() -> None:
    config = _config(alpha=2.0, beta=1.0)

    weights = _transition_weights(
        np.array([2.0, 4.0]),
        np.array([2.0, 1.0]),
        config,
    )

    assert weights[1] / weights[0] == pytest.approx(8.0)


def test_ant_construction_returns_a_legal_simple_path() -> None:
    grid = GridMap(np.zeros((4, 4), dtype=bool))
    config = _config()

    construction = _construct_ant_path(
        grid,
        (0, 0),
        (3, 3),
        config,
        _initialize_pheromone(grid, config),
        np.random.default_rng(7),
    )

    assert construction.path is not None
    assert len(construction.path) == len(set(construction.path))
    assert validate_path(
        grid,
        construction.path,
        (0, 0),
        (3, 3),
        config.movement,
    ).valid


def test_ant_construction_backtracks_out_of_a_dead_end() -> None:
    grid = GridMap(
        np.array(
            [
                [0, 0, 1, 1],
                [0, 1, 1, 1],
                [0, 0, 0, 0],
            ],
            dtype=bool,
        )
    )
    config = _config(alpha=4.0, beta=0.0, max_pheromone=1e12)
    pheromone = _initialize_pheromone(grid, config)
    pheromone[2, 0, 0] = 1e12

    construction = _construct_ant_path(
        grid,
        (2, 0),
        (2, 3),
        config,
        pheromone,
        np.random.default_rng(0),
    )

    assert construction.path is not None
    assert construction.backtracks == 3
    assert (0, 0) not in construction.path
    assert (0, 1) not in construction.path


def test_ant_construction_respects_step_restart_and_backtrack_budgets() -> None:
    grid = GridMap(np.zeros((1, 4), dtype=bool))
    config = _config(max_steps=1, max_restarts=2, max_backtracks=0)

    construction = _construct_ant_path(
        grid,
        (0, 0),
        (0, 3),
        config,
        _initialize_pheromone(grid, config),
        np.random.default_rng(3),
    )

    assert construction.path is None
    assert construction.steps == 3
    assert construction.restarts == 2
    assert construction.backtracks == 0


def test_aco_precheck_uses_shared_endpoint_and_reachability_rules() -> None:
    grid = GridMap(
        np.array(
            [
                [0, 1, 0],
                [0, 1, 0],
                [0, 1, 0],
            ],
            dtype=bool,
        )
    )
    movement = MovementConfig(4)

    assert _precheck_failure(grid, (-1, 0), (0, 2), movement) == ("start_out_of_bounds")
    assert _precheck_failure(grid, (0, 0), (0, 2), movement) == ("no_path_precheck")
    assert _precheck_failure(grid, (0, 0), (2, 0), movement) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ants", 0),
        ("alpha", -0.1),
        ("beta", float("inf")),
        ("evaporation_rate", 1.0),
        ("pheromone_deposit", 0.0),
        ("elite_weight", -1.0),
        ("min_pheromone", 0.0),
        ("max_pheromone", 0.001),
        ("iterations", 0),
        ("max_steps", 0),
        ("max_restarts", -1),
        ("max_backtracks", -1),
        ("stagnation_iterations", 0),
    ],
)
def test_aco_config_rejects_invalid_parameters(field: str, value: object) -> None:
    config = _config()

    with pytest.raises(ValueError):
        replace(config, **{field: value})
