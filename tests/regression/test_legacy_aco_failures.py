from pathlib import Path

import numpy as np

from path_planning.algorithms.aco import (
    ACOConfig,
    _deposit_path,
    _initialize_pheromone,
)
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _config() -> ACOConfig:
    return ACOConfig(
        movement=MovementConfig(4),
        ants=2,
        alpha=1.0,
        beta=2.0,
        evaporation_rate=0.2,
        pheromone_deposit=1.0,
        elite_weight=1.0,
        min_pheromone=0.01,
        max_pheromone=10.0,
        iterations=2,
        max_steps=20,
        max_restarts=1,
        max_backtracks=5,
        stagnation_iterations=2,
    )


def test_path_deposit_changes_pheromone_and_covers_every_bidirectional_edge() -> None:
    grid = GridMap(np.zeros((3, 3), dtype=bool))
    config = _config()
    pheromone = _initialize_pheromone(grid, config)

    _deposit_path(
        pheromone,
        ((1, 0), (1, 1), (0, 1)),
        0.5,
        config.movement,
    )

    assert pheromone.sum() == 38.0
    assert pheromone[1, 0, 1] == 1.5
    assert pheromone[1, 1, 3] == 1.5
    assert pheromone[1, 1, 0] == 1.5
    assert pheromone[0, 1, 2] == 1.5
    assert np.unique(pheromone).tolist() == [1.0, 1.5]


def test_legacy_baseline_records_hashes_without_importing_old_code() -> None:
    text = (PROJECT_ROOT / "docs" / "legacy_baseline.md").read_text(encoding="utf-8")

    assert "02b8da882eb5b307592cc4e99b20f7f96320e414e7225f214da870857ccbbfa1" in text
    assert "f534b2543beb31e8f0253001b96494b0086b4b085a340d8d4ae4d33e10c91e8e" in text
    assert "未执行、导入或复制" in text
    assert "只挥发不学习" in text
    assert "闭环边更新不完整" in text
