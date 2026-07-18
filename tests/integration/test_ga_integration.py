from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from path_planning.algorithms import GAConfig, GeneticPlanner, genetic
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig
from path_planning.core.result import PlanningResult
from path_planning.core.types import Point
from path_planning.core.validation import validate_path
from path_planning.maps.io import load_scenario

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HANDCRAFTED = PROJECT_ROOT / "maps" / "handcrafted"


def _assert_zero_work_metadata(result: PlanningResult, stop_reason: str) -> None:
    assert set(result.metadata) == {
        "movement",
        "config",
        "operators",
        "budget",
        "best_fitness_history",
        "trajectory_digest",
    }
    assert result.metadata["operators"] == {
        "crossover": {
            "attempts": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
        },
        "mutation": {
            "attempts": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
        },
        "repair": {"successes": 0, "failures": 0},
    }
    assert result.metadata["budget"] == {
        "generation_limit": 2,
        "generations_executed": 0,
        "stagnation_limit": 3,
        "stop_reason": stop_reason,
        "budget_exhausted": False,
    }
    assert result.metadata["best_fitness_history"] == []
    assert len(result.metadata["trajectory_digest"]) == 64


def _config(**overrides: object) -> GAConfig:
    values = {
        "movement": MovementConfig(4),
        "population_size": 4,
        "generations": 2,
        "crossover_probability": 0.0,
        "mutation_probability": 0.0,
        "tournament_size": 2,
        "elite_size": 1,
        "max_initialization_steps": 50,
        "initialization_attempts": 2,
        "stagnation_generations": 3,
        "path_length_penalty": 1.0,
        "turn_penalty": 0.25,
        "repeat_penalty": 2.0,
        "unreachable_base_penalty": 1_000.0,
        "collision_penalty": 10.0,
        "remaining_distance_penalty": 3.0,
    }
    values.update(overrides)
    return GAConfig(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("cells", "start", "goal", "failure_reason"),
    [
        ([[0, 0], [0, 0]], (-1, 0), (1, 1), "start_out_of_bounds"),
        ([[0, 0], [0, 0]], (0, 0), (2, 1), "goal_out_of_bounds"),
        ([[1, 0], [0, 0]], (0, 0), (1, 1), "start_blocked"),
        ([[0, 0], [0, 1]], (0, 0), (1, 1), "goal_blocked"),
        ([[0, 1], [1, 0]], (0, 0), (1, 1), "no_path_precheck"),
    ],
)
def test_ga_precheck_preserves_failures_and_does_zero_work(
    cells: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
    failure_reason: str,
) -> None:
    result = GeneticPlanner().plan(
        GridMap(np.array(cells, dtype=bool)),
        start,
        goal,
        _config(),
        seed=11,
    )

    assert not result.success
    assert result.failure_reason == failure_reason
    assert result.path == ()
    assert result.path_length is None
    assert result.evaluations == 0
    assert result.iterations == 0
    assert result.convergence_history == ()
    _assert_zero_work_metadata(result, failure_reason)


@pytest.mark.parametrize(
    ("cells", "start", "goal"),
    [
        ([[0, 0], [0, 0]], (1, 1), (1, 1)),
        ([[0, 1], [1, 0]], (0, 0), (1, 1)),
        ([[0, 0], [0, 0]], (-1, 0), (1, 1)),
    ],
)
def test_ga_validates_grid_config_before_every_public_early_exit(
    cells: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> None:
    with pytest.raises(ValueError, match="unreachable_base_penalty"):
        GeneticPlanner().plan(
            GridMap(np.array(cells, dtype=bool)),
            start,
            goal,
            _config(unreachable_base_penalty=1.0),
            seed=12,
        )


def test_ga_start_equals_goal_is_an_immediate_zero_work_success() -> None:
    result = GeneticPlanner().plan(
        GridMap(np.zeros((2, 2), dtype=bool)),
        (1, 1),
        (1, 1),
        _config(),
        seed=13,
    )

    assert result.success
    assert result.path == ((1, 1),)
    assert result.path_length == 0.0
    assert result.evaluations == 0
    assert result.iterations == 0
    assert result.convergence_history == ()
    _assert_zero_work_metadata(result, "start_equals_goal")


def test_ga_reports_honest_bounded_initialization_failure() -> None:
    grid = GridMap(np.zeros((1, 3), dtype=bool))

    result = GeneticPlanner().plan(
        grid,
        (0, 0),
        (0, 2),
        _config(max_initialization_steps=1, initialization_attempts=1),
        seed=17,
    )

    assert not result.success
    assert result.failure_reason == "initialization_failed"
    assert result.path == ()
    assert result.path_length is None
    assert result.evaluations == 0
    assert result.iterations == 0
    assert result.convergence_history == ()
    _assert_zero_work_metadata(result, "initialization_failed")


def test_ga_does_not_hide_unrelated_toolbox_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenToolbox:
        @staticmethod
        def individual() -> list[tuple[int, int]]:
            raise RuntimeError("unrelated toolbox defect")

    monkeypatch.setattr(
        genetic,
        "build_toolbox",
        lambda *args, **kwargs: BrokenToolbox(),
    )

    with pytest.raises(RuntimeError, match="unrelated toolbox defect"):
        GeneticPlanner().plan(
            GridMap(np.zeros((3, 3), dtype=bool)),
            (0, 0),
            (2, 2),
            _config(),
            seed=18,
        )


def test_ga_initialization_attempts_control_public_retry_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fail_once_then_succeed(
        *args: object, **kwargs: object
    ) -> tuple[Point, ...] | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        return ((0, 0), (0, 1), (0, 2))

    monkeypatch.setattr(genetic, "_bounded_random_dfs", fail_once_then_succeed)
    grid = GridMap(np.zeros((1, 3), dtype=bool))
    planner = GeneticPlanner()

    one_attempt = planner.plan(
        grid,
        (0, 0),
        (0, 2),
        _config(initialization_attempts=1),
        seed=20,
    )
    assert not one_attempt.success
    assert one_attempt.failure_reason == "initialization_failed"
    assert calls == 1

    calls = 0
    two_attempts = planner.plan(
        grid,
        (0, 0),
        (0, 2),
        _config(initialization_attempts=2),
        seed=20,
    )
    assert two_attempts.success
    assert two_attempts.path == ((0, 0), (0, 1), (0, 2))
    assert calls == 5


@pytest.mark.parametrize("map_name", ["narrow_channel_20", "dead_ends_30"])
def test_ga_finds_valid_paths_on_complex_handcrafted_maps(map_name: str) -> None:
    scenario = load_scenario(HANDCRAFTED / f"{map_name}.json")
    config = _config(
        crossover_probability=0.8,
        mutation_probability=0.5,
        max_initialization_steps=scenario.grid.free_cell_count * 8,
        unreachable_base_penalty=1_000_000.0,
    )

    result = GeneticPlanner().plan(
        scenario.grid,
        scenario.start,
        scenario.goal,
        config,
        seed=17,
    )

    validation = validate_path(
        scenario.grid,
        result.path,
        scenario.start,
        scenario.goal,
        config.movement,
    )
    assert result.success
    assert validation.valid
    assert result.path_length == pytest.approx(validation.path_length)


@pytest.mark.parametrize("allow_corner_cutting", [False, True])
def test_ga_obeys_shared_corner_cutting_rule(allow_corner_cutting: bool) -> None:
    grid = GridMap(np.array([[0, 1], [1, 0]], dtype=bool))
    movement = MovementConfig(8, allow_corner_cutting=allow_corner_cutting)

    result = GeneticPlanner().plan(
        grid,
        (0, 0),
        (1, 1),
        _config(movement=movement),
        seed=19,
    )

    assert result.success is allow_corner_cutting
    if allow_corner_cutting:
        assert validate_path(grid, result.path, (0, 0), (1, 1), movement).valid
    else:
        assert result.failure_reason == "no_path_precheck"


def test_ga_result_contains_exact_config_operator_and_budget_metadata() -> None:
    grid = GridMap(np.zeros((4, 4), dtype=bool))
    config = _config(
        selection_method="roulette",
        crossover_method="splice_repair",
        mutation_method="shortcut",
    )

    result = GeneticPlanner().plan(grid, (0, 0), (3, 3), config, seed=23)

    assert result.evaluations == 12
    assert result.iterations == 2
    assert result.metadata["movement"] == {
        "connectivity": 4,
        "diagonal_cost": pytest.approx(2**0.5),
        "allow_corner_cutting": False,
    }
    assert result.metadata["config"] == {
        "population_size": 4,
        "generations": 2,
        "crossover_probability": 0.0,
        "mutation_probability": 0.0,
        "tournament_size": 2,
        "elite_size": 1,
        "max_initialization_steps": 50,
        "initialization_attempts": 2,
        "stagnation_generations": 3,
        "path_length_penalty": 1.0,
        "turn_penalty": 0.25,
        "repeat_penalty": 2.0,
        "unreachable_base_penalty": 1_000.0,
        "collision_penalty": 10.0,
        "remaining_distance_penalty": 3.0,
        "crossover_method": "splice_repair",
        "mutation_method": "shortcut",
        "selection_method": "roulette",
    }
    assert result.metadata["operators"] == {
        "crossover": {
            "attempts": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 4,
        },
        "mutation": {
            "attempts": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 6,
        },
        "repair": {"successes": 0, "failures": 0},
    }
    assert result.metadata["budget"] == {
        "generation_limit": 2,
        "generations_executed": 2,
        "stagnation_limit": 3,
        "stop_reason": "max_generations",
        "budget_exhausted": True,
    }
    assert result.convergence_history == (10.0, 10.0)
    assert result.metadata["best_fitness_history"] == [11.75, 11.75]
    assert len(result.metadata["trajectory_digest"]) == 64


def test_ga_marks_generation_budget_exhausted_when_stagnation_triggers_too() -> None:
    result = GeneticPlanner().plan(
        GridMap(np.zeros((3, 3), dtype=bool)),
        (0, 0),
        (2, 2),
        _config(generations=1, stagnation_generations=1),
        seed=27,
    )

    assert result.iterations == 1
    assert result.metadata["budget"] == {
        "generation_limit": 1,
        "generations_executed": 1,
        "stagnation_limit": 1,
        "stop_reason": "stagnation",
        "budget_exhausted": True,
    }


def test_ga_rejects_an_internally_selected_invalid_final_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = genetic.evolve_population

    def select_invalid_path(
        *args: object, **kwargs: object
    ) -> genetic.EvolutionOutcome:
        outcome = original(*args, **kwargs)  # type: ignore[arg-type]
        return replace(outcome, best_individual=((0, 0), (3, 3)))

    monkeypatch.setattr(genetic, "evolve_population", select_invalid_path)

    with pytest.raises(RuntimeError, match="invalid best path"):
        GeneticPlanner().plan(
            GridMap(np.zeros((4, 4), dtype=bool)),
            (0, 0),
            (3, 3),
            _config(),
            seed=29,
        )


def test_genetic_planner_uses_the_unified_public_result_contract() -> None:
    planner = GeneticPlanner()

    result = planner.plan(
        GridMap(np.zeros((3, 3), dtype=bool)),
        (0, 0),
        (2, 2),
        _config(),
        seed=7,
    )

    assert planner.name == "ga"
    assert isinstance(result, PlanningResult)
    assert result.algorithm == "ga"
    assert result.success
