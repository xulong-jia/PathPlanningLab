import random
from dataclasses import replace

import numpy as np
import pytest

from path_planning.algorithms import genetic
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig

MOVEMENT = MovementConfig(4)


def _config(**overrides: object) -> genetic.GAConfig:
    values = {
        "movement": MOVEMENT,
        "population_size": 4,
        "generations": 4,
        "crossover_probability": 0.0,
        "mutation_probability": 0.0,
        "tournament_size": 4,
        "elite_size": 1,
        "max_initialization_steps": 50,
        "initialization_attempts": 2,
        "stagnation_generations": 5,
        "path_length_penalty": 1.0,
        "turn_penalty": 0.0,
        "repeat_penalty": 2.0,
        "unreachable_base_penalty": 100.0,
        "collision_penalty": 10.0,
        "remaining_distance_penalty": 3.0,
    }
    values.update(overrides)
    return genetic.GAConfig(**values)  # type: ignore[arg-type]


def _individual(path: list[tuple[int, int]], fitness: float) -> list[tuple[int, int]]:
    individual = genetic.GAIndividual(path)
    individual.fitness.values = (fitness,)
    return individual


def _population() -> list[list[tuple[int, int]]]:
    return [
        genetic.GAIndividual([(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)]),
        genetic.GAIndividual([(0, 0), (1, 0), (1, 1), (0, 1), (0, 2), (1, 2), (2, 2)]),
        genetic.GAIndividual([(0, 0), (0, 1), (1, 1), (1, 0), (2, 0), (2, 1), (2, 2)]),
        genetic.GAIndividual([(0, 0), (1, 0), (2, 0), (2, 1), (1, 1), (1, 2), (2, 2)]),
    ]


@pytest.mark.parametrize("selection_method", ["tournament", "roulette"])
def test_selection_methods_use_configured_local_rng(selection_method: str) -> None:
    population = [_individual([(0, index)], float(index + 1)) for index in range(4)]
    random.seed(991)
    global_state = random.getstate()

    selected = genetic.select_population(
        population,
        8,
        _config(selection_method=selection_method),
        random.Random(7),
    )

    assert len(selected) == 8
    assert all(
        tuple(choice) in {tuple(member) for member in population} for choice in selected
    )
    assert all(choice is not member for choice in selected for member in population)
    if selection_method == "tournament":
        assert all(tuple(choice) == tuple(population[0]) for choice in selected)
    assert random.getstate() == global_state


def test_roulette_is_stable_for_extreme_finite_fitness() -> None:
    population = [
        _individual([(0, index)], fitness)
        for index, fitness in enumerate((-1e308, 0.0, 1e308))
    ]

    selected = genetic.select_population(
        population,
        100,
        _config(
            population_size=3,
            tournament_size=3,
            selection_method="roulette",
        ),
        random.Random(11),
    )

    assert any(tuple(choice) == tuple(population[0]) for choice in selected)
    assert all(tuple(choice) != tuple(population[2]) for choice in selected)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("selection_method", "rank"),
        ("tournament_size", 5),
    ],
)
def test_selection_config_rejects_invalid_contract(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        replace(_config(), **{field: value})


def test_evolution_preserves_elite_best_fitness() -> None:
    grid = GridMap(np.zeros((3, 3), dtype=bool))
    population = _population()
    snapshots = [tuple(individual) for individual in population]

    result = genetic.evolve_population(
        population,
        grid,
        (0, 0),
        (2, 2),
        _config(selection_method="tournament", elite_size=2, generations=1),
        random.Random(13),
    )

    assert result.best_fitness_history == tuple(
        sorted(result.best_fitness_history, reverse=True)
    )
    assert tuple(result.best_individual) == snapshots[0]
    assert result.population[:2] == tuple(snapshots[:2])
    assert [tuple(individual) for individual in population] == snapshots


def test_evolution_routes_all_operations_through_real_toolbox_aliases() -> None:
    grid = GridMap(np.zeros((3, 3), dtype=bool))
    config = _config(
        generations=1,
        stagnation_generations=2,
        crossover_probability=1.0,
        mutation_probability=1.0,
    )
    operator_rng = random.Random(43)
    toolbox = genetic.build_toolbox(
        grid,
        (0, 0),
        (2, 2),
        config,
        seed=41,
        operator_rng=operator_rng,
    )
    calls = {name: 0 for name in ("select", "mate", "mutate", "elite")}

    for name in calls:
        original = getattr(toolbox, name)

        def traced(
            *args: object,
            _name: str = name,
            _original: object = original,
            **kwargs: object,
        ) -> object:
            calls[_name] += 1
            return _original(*args, **kwargs)  # type: ignore[operator]

        toolbox.unregister(name)
        toolbox.register(name, traced)

    result = genetic.evolve_population(
        _population(),
        grid,
        (0, 0),
        (2, 2),
        config,
        operator_rng,
        toolbox=toolbox,
    )

    assert result.generations_executed == 1
    assert calls["elite"] == 1
    assert calls["select"] == 2
    assert calls["mate"] == 2
    assert calls["mutate"] == 3


def test_rate_zero_records_skips_without_attempts() -> None:
    result = genetic.evolve_population(
        _population(),
        GridMap(np.zeros((3, 3), dtype=bool)),
        (0, 0),
        (2, 2),
        _config(generations=2, stagnation_generations=3),
        random.Random(17),
    )

    counts = result.operator_counts
    assert counts.crossover_attempts == 0
    assert counts.crossover_succeeded == 0
    assert counts.crossover_failed == 0
    assert counts.crossover_skipped == 4
    assert counts.mutation_attempts == 0
    assert counts.mutation_succeeded == 0
    assert counts.mutation_failed == 0
    assert counts.mutation_skipped == 6
    assert (counts.repair_successes, counts.repair_failures) == (0, 0)


def test_rate_one_records_attempts_and_propagates_repair_counts() -> None:
    result = genetic.evolve_population(
        _population(),
        GridMap(np.zeros((3, 3), dtype=bool)),
        (0, 0),
        (2, 2),
        _config(
            generations=1,
            stagnation_generations=2,
            crossover_probability=1.0,
            mutation_probability=1.0,
            crossover_method="splice_repair",
            mutation_method="shortcut",
        ),
        random.Random(19),
    )

    counts = result.operator_counts
    assert counts.crossover_attempts == 2
    assert (counts.crossover_succeeded, counts.crossover_failed) == (1, 1)
    assert counts.crossover_skipped == 0
    assert counts.mutation_attempts == 3
    assert (counts.mutation_succeeded, counts.mutation_failed) == (1, 2)
    assert counts.mutation_skipped == 0
    assert (counts.repair_successes, counts.repair_failures) == (4, 0)

    failed_repairs = genetic.evolve_population(
        [genetic.GAIndividual([(0, 0), (0, 2)]) for _ in range(4)],
        GridMap(np.array([[0, 1, 0]], dtype=bool)),
        (0, 0),
        (0, 2),
        _config(
            generations=1,
            stagnation_generations=2,
            crossover_probability=1.0,
            mutation_probability=1.0,
            crossover_method="splice_repair",
            mutation_method="shortcut",
            max_initialization_steps=1,
        ),
        random.Random(31),
    )

    assert (
        failed_repairs.operator_counts.repair_successes,
        failed_repairs.operator_counts.repair_failures,
    ) == (0, 4)


def test_evolution_stops_at_maximum_generations_and_records_histories() -> None:
    random.seed(991)
    global_state = random.getstate()

    result = genetic.evolve_population(
        _population(),
        GridMap(np.zeros((3, 3), dtype=bool)),
        (0, 0),
        (2, 2),
        _config(generations=4, stagnation_generations=5),
        random.Random(23),
    )

    assert result.stop_reason == "max_generations"
    assert result.generations_executed == 4
    assert len(result.best_fitness_history) == result.generations_executed
    assert len(result.best_path_cost_history) == result.generations_executed
    assert result.best_fitness_history == (4.0, 4.0, 4.0, 4.0)
    assert result.best_path_cost_history == (4.0, 4.0, 4.0, 4.0)
    assert result.evaluations == 4 + 4 * 4
    assert random.getstate() == global_state


def test_evolution_stops_early_after_configured_stagnation() -> None:
    result = genetic.evolve_population(
        _population(),
        GridMap(np.zeros((3, 3), dtype=bool)),
        (0, 0),
        (2, 2),
        _config(generations=10, stagnation_generations=2),
        random.Random(29),
    )

    assert result.stop_reason == "stagnation"
    assert result.generations_executed == 2
    assert len(result.best_fitness_history) == 2
    assert len(result.best_path_cost_history) == 2
    assert result.evaluations == 4 + 2 * 4
