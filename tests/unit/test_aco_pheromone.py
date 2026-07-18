from dataclasses import replace

import numpy as np
import pytest

from path_planning.algorithms.aco import (
    ACOConfig,
    _initialize_pheromone,
    _update_convergence,
    _update_pheromone,
)
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig

PATH = ((1, 0), (1, 1), (1, 2))


def _config(**overrides: object) -> ACOConfig:
    values = {
        "movement": MovementConfig(4),
        "ants": 4,
        "alpha": 1.0,
        "beta": 2.0,
        "evaporation_rate": 0.2,
        "pheromone_deposit": 1.0,
        "elite_weight": 0.0,
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


def _pheromone(config: ACOConfig) -> np.ndarray[tuple[int, ...], np.dtype[np.float64]]:
    return _initialize_pheromone(GridMap(np.zeros((3, 4), dtype=bool)), config)


def test_round_update_evaporates_globally_and_reinforces_non_uniformly() -> None:
    config = _config()
    pheromone = _pheromone(config)

    _update_pheromone(pheromone, ((PATH, 2.0),), None, config)

    assert np.min(pheromone) == pytest.approx(0.8)
    assert np.max(pheromone) == pytest.approx(1.3)
    assert np.unique(pheromone).size == 2


def test_shorter_path_receives_more_pheromone_than_longer_path() -> None:
    config = _config(evaporation_rate=0.0)
    short = _pheromone(config)
    long = _pheromone(config)

    _update_pheromone(short, ((PATH, 2.0),), None, config)
    _update_pheromone(long, ((PATH, 4.0),), None, config)

    assert short[1, 0, 1] == pytest.approx(1.5)
    assert long[1, 0, 1] == pytest.approx(1.25)


def test_evaporation_rate_changes_the_whole_tensor() -> None:
    low_rate = _pheromone(_config(evaporation_rate=0.1))
    high_rate = _pheromone(_config(evaporation_rate=0.6))

    _update_pheromone(low_rate, (), None, _config(evaporation_rate=0.1))
    _update_pheromone(high_rate, (), None, _config(evaporation_rate=0.6))

    assert np.all(low_rate == pytest.approx(0.9))
    assert np.all(high_rate == pytest.approx(0.4))


def test_round_update_clips_to_configured_minimum_and_maximum() -> None:
    config = _config(
        evaporation_rate=0.8,
        pheromone_deposit=100.0,
        min_pheromone=0.5,
        max_pheromone=1.2,
    )
    pheromone = _pheromone(config)

    _update_pheromone(pheromone, ((PATH, 2.0),), None, config)

    assert np.min(pheromone) == pytest.approx(0.5)
    assert np.max(pheromone) == pytest.approx(1.2)


def test_elite_weight_adds_global_best_reinforcement() -> None:
    ordinary_config = _config(evaporation_rate=0.0, elite_weight=0.0)
    elite_config = replace(ordinary_config, elite_weight=2.0)
    ordinary = _pheromone(ordinary_config)
    elite = _pheromone(elite_config)

    _update_pheromone(ordinary, ((PATH, 2.0),), (PATH, 2.0), ordinary_config)
    _update_pheromone(elite, ((PATH, 2.0),), (PATH, 2.0), elite_config)

    assert ordinary[1, 0, 1] == pytest.approx(1.5)
    assert elite[1, 0, 1] == pytest.approx(2.5)


def test_round_update_evaporates_before_depositing() -> None:
    config = _config(evaporation_rate=0.5)
    pheromone = _pheromone(config)
    pheromone.fill(2.0)

    _update_pheromone(pheromone, ((PATH, 2.0),), None, config)

    assert pheromone[1, 0, 1] == pytest.approx(1.5)


def test_convergence_carries_best_forward_and_tracks_stagnation() -> None:
    best, stagnant = _update_convergence(None, None, 0)
    assert best is None
    assert stagnant == 1

    best, stagnant = _update_convergence(best, 5.0, stagnant)
    assert best == 5.0
    assert stagnant == 0

    best, stagnant = _update_convergence(best, 6.0, stagnant)
    assert best == 5.0
    assert stagnant == 1

    best, stagnant = _update_convergence(best, 4.0, stagnant)
    assert best == 4.0
    assert stagnant == 0
