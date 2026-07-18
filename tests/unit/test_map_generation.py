import numpy as np
import pytest

from path_planning.core.movement import MovementConfig
from path_planning.core.validation import is_reachable
from path_planning.maps.generation import (
    RandomMapConfig,
    generate_random_scenario,
    generated_scenario_name,
)


def config(seed: int = 17) -> RandomMapConfig:
    return RandomMapConfig(
        rows=10,
        columns=12,
        target_density=0.2,
        seed=seed,
        start=(0, 0),
        goal=(9, 11),
        guarantee_reachable=True,
    )


def test_same_seed_generates_identical_grid_and_metadata() -> None:
    first = generate_random_scenario(config())
    second = generate_random_scenario(config())

    assert np.array_equal(first.grid.cells, second.grid.cells)
    assert first.metadata == second.metadata


def test_different_seed_changes_obstacle_placement() -> None:
    first = generate_random_scenario(config(17))
    second = generate_random_scenario(config(18))

    assert not np.array_equal(first.grid.cells, second.grid.cells)


def test_generation_uses_exact_obstacle_target_and_protects_reachability() -> None:
    scenario = generate_random_scenario(config())
    blocked = int(np.count_nonzero(scenario.grid.cells))

    assert blocked == round(10 * 12 * 0.2)
    assert scenario.metadata["actual_density"] == pytest.approx(blocked / 120)
    assert not scenario.grid.is_blocked(scenario.start)
    assert not scenario.grid.is_blocked(scenario.goal)
    assert is_reachable(
        scenario.grid,
        scenario.start,
        scenario.goal,
        MovementConfig(4),
    )


def test_generated_name_is_stable() -> None:
    assert generated_scenario_name(config()) == "random_10x12_d20_seed17"


def test_generation_rejects_density_above_unprotected_capacity() -> None:
    impossible = RandomMapConfig(
        rows=2,
        columns=2,
        target_density=0.75,
        seed=1,
        start=(0, 0),
        goal=(1, 1),
        guarantee_reachable=True,
    )

    with pytest.raises(ValueError, match="capacity"):
        generate_random_scenario(impossible)


@pytest.mark.parametrize(
    "overrides",
    [
        {"rows": 0},
        {"columns": 0},
        {"target_density": -0.1},
        {"target_density": 1.0},
        {"seed": True},
        {"guarantee_reachable": 1},
        {"start": [0, 0]},
        {"start": (-1, 0)},
    ],
)
def test_random_map_config_rejects_invalid_values(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "rows": 10,
        "columns": 12,
        "target_density": 0.2,
        "seed": 17,
        "start": (0, 0),
        "goal": (9, 11),
        "guarantee_reachable": True,
    }
    values.update(overrides)

    with pytest.raises((TypeError, ValueError)):
        RandomMapConfig(**values)  # type: ignore[arg-type]


def test_generation_without_reachability_guarantee_supports_zero_density() -> None:
    scenario = generate_random_scenario(
        RandomMapConfig(
            rows=3,
            columns=3,
            target_density=0.0,
            seed=5,
            start=(2, 2),
            goal=(0, 0),
            guarantee_reachable=False,
        )
    )

    assert scenario.grid.free_cell_count == 9
    assert scenario.metadata["generation_strategy"] == "random_obstacles"
