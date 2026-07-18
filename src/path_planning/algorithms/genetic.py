import hashlib
import json
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from deap import base, creator

from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig, iter_neighbors
from path_planning.core.result import PlanningResult
from path_planning.core.types import JsonValue, Point
from path_planning.core.validation import (
    is_reachable,
    validate_endpoints,
    validate_path,
)

_FITNESS_TYPE_NAME = "PathPlanningLabGAFitnessMin"
_INDIVIDUAL_TYPE_NAME = "PathPlanningLabGAIndividual"

if not hasattr(creator, _FITNESS_TYPE_NAME):
    creator.create(_FITNESS_TYPE_NAME, base.Fitness, weights=(-1.0,))
if not hasattr(creator, _INDIVIDUAL_TYPE_NAME):
    creator.create(
        _INDIVIDUAL_TYPE_NAME,
        list,
        fitness=getattr(creator, _FITNESS_TYPE_NAME),
    )

GAFitness: type[base.Fitness] = getattr(creator, _FITNESS_TYPE_NAME)
GAIndividual: type[list[Point]] = getattr(creator, _INDIVIDUAL_TYPE_NAME)

CrossoverMethod = Literal["common_node", "splice_repair"]
MutationMethod = Literal["reroute_segment", "shortcut"]
OperatorStatus = Literal["skipped", "succeeded", "failed"]
SelectionMethod = Literal["tournament", "roulette"]
EvolutionStopReason = Literal["max_generations", "stagnation"]


class GAInitializationError(RuntimeError):
    """Raised when bounded random initialization exhausts its configured budget."""


@dataclass(frozen=True, slots=True)
class SpliceRepairOutcome:
    children: tuple[tuple[Point, ...], tuple[Point, ...]] | None
    repair_successes: int
    repair_failures: int


@dataclass(frozen=True, slots=True)
class CrossoverOutcome:
    child_a: list[Point]
    child_b: list[Point]
    status: OperatorStatus
    repair_successes: int
    repair_failures: int


@dataclass(frozen=True, slots=True)
class MutationOutcome:
    child: list[Point]
    status: OperatorStatus


@dataclass(slots=True)
class OperatorCounts:
    crossover_attempts: int = 0
    crossover_succeeded: int = 0
    crossover_failed: int = 0
    crossover_skipped: int = 0
    mutation_attempts: int = 0
    mutation_succeeded: int = 0
    mutation_failed: int = 0
    mutation_skipped: int = 0
    repair_successes: int = 0
    repair_failures: int = 0


@dataclass(frozen=True, slots=True)
class EvolutionSnapshot:
    population: tuple[tuple[Point, ...], ...]
    fitness_values: tuple[float, ...]
    operator_counts: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class EvolutionOutcome:
    population: tuple[tuple[Point, ...], ...]
    best_individual: tuple[Point, ...]
    generations_executed: int
    best_fitness_history: tuple[float, ...]
    best_path_cost_history: tuple[float, ...]
    evaluations: int
    operator_counts: OperatorCounts
    stop_reason: EvolutionStopReason
    trajectory: tuple[EvolutionSnapshot, ...]


@dataclass(frozen=True, slots=True)
class GAConfig:
    movement: MovementConfig
    population_size: int
    generations: int
    crossover_probability: float
    mutation_probability: float
    tournament_size: int
    elite_size: int
    max_initialization_steps: int
    initialization_attempts: int
    stagnation_generations: int
    path_length_penalty: float
    turn_penalty: float
    repeat_penalty: float
    unreachable_base_penalty: float
    collision_penalty: float
    remaining_distance_penalty: float
    crossover_method: CrossoverMethod = "common_node"
    mutation_method: MutationMethod = "reroute_segment"
    selection_method: SelectionMethod = "tournament"

    def __post_init__(self) -> None:
        for name in (
            "population_size",
            "generations",
            "max_initialization_steps",
            "initialization_attempts",
            "stagnation_generations",
        ):
            _require_positive_integer(name, getattr(self, name))
        _require_positive_integer("tournament_size", self.tournament_size)
        if self.tournament_size < 2:
            raise ValueError("tournament_size must be at least 2")
        _require_non_negative_integer("elite_size", self.elite_size)
        if self.elite_size >= self.population_size:
            raise ValueError("elite_size must be less than population_size")
        for name in ("crossover_probability", "mutation_probability"):
            _require_probability(name, getattr(self, name))
        for name in (
            "path_length_penalty",
            "turn_penalty",
            "repeat_penalty",
            "collision_penalty",
            "remaining_distance_penalty",
        ):
            _require_non_negative_number(name, getattr(self, name))
        _require_positive_number(
            "unreachable_base_penalty",
            self.unreachable_base_penalty,
        )
        if self.crossover_method not in ("common_node", "splice_repair"):
            raise ValueError("crossover_method must be common_node or splice_repair")
        if self.mutation_method not in ("reroute_segment", "shortcut"):
            raise ValueError("mutation_method must be reroute_segment or shortcut")
        if self.selection_method not in ("tournament", "roulette"):
            raise ValueError("selection_method must be tournament or roulette")
        if self.tournament_size > self.population_size:
            raise ValueError("tournament_size must not exceed population_size")

    def validate_for_grid(self, grid: GridMap) -> None:
        upper_bound = legal_fitness_upper_bound(grid, self)
        if self.unreachable_base_penalty <= upper_bound:
            raise ValueError(
                "unreachable_base_penalty must exceed the legal fitness upper bound "
                f"for this grid ({upper_bound})"
            )


class GeneticPlanner:
    name = "ga"

    def plan(
        self,
        grid: GridMap,
        start: Point,
        goal: Point,
        config: GAConfig,
        seed: int | None = None,
    ) -> PlanningResult:
        started_at = perf_counter()
        config.validate_for_grid(grid)
        precheck_failure = validate_endpoints(grid, start, goal)
        if precheck_failure is None and not is_reachable(
            grid, start, goal, config.movement
        ):
            precheck_failure = "no_path_precheck"
        if precheck_failure is not None:
            return self._result(
                started_at=started_at,
                config=config,
                seed=seed,
                failure_reason=precheck_failure,
                stop_reason=precheck_failure,
                trajectory_digest=_trajectory_digest((), ()),
            )
        if start == goal:
            return self._result(
                started_at=started_at,
                config=config,
                seed=seed,
                path=(start,),
                path_length=0.0,
                stop_reason="start_equals_goal",
                trajectory_digest=_trajectory_digest((), ()),
            )
        master_rng = random.Random(seed)
        initialization_seed = master_rng.getrandbits(64)
        evolution_rng = random.Random(master_rng.getrandbits(64))
        toolbox = build_toolbox(
            grid,
            start,
            goal,
            config,
            seed=initialization_seed,
            operator_rng=evolution_rng,
        )
        population: list[list[Point]] = []
        try:
            for _ in range(config.population_size):
                population.append(toolbox.individual())
        except GAInitializationError:
            partial_population = tuple(tuple(individual) for individual in population)
            return self._result(
                started_at=started_at,
                config=config,
                seed=seed,
                failure_reason="initialization_failed",
                stop_reason="initialization_failed",
                trajectory_digest=_trajectory_digest(partial_population, ()),
            )
        initial_population = tuple(tuple(individual) for individual in population)
        evolution = evolve_population(
            population,
            grid,
            start,
            goal,
            config,
            evolution_rng,
            toolbox=toolbox,
        )
        validation = validate_path(
            grid,
            evolution.best_individual,
            start,
            goal,
            config.movement,
        )
        if not validation.valid or validation.path_length is None:
            raise RuntimeError("GA selected an invalid best path")
        return self._result(
            started_at=started_at,
            config=config,
            seed=seed,
            path=evolution.best_individual,
            path_length=validation.path_length,
            evolution=evolution,
            stop_reason=evolution.stop_reason,
            trajectory_digest=_trajectory_digest(
                initial_population,
                evolution.trajectory,
            ),
        )

    def _result(
        self,
        *,
        started_at: float,
        config: GAConfig,
        seed: int | None,
        stop_reason: str,
        trajectory_digest: str,
        path: tuple[Point, ...] = (),
        path_length: float | None = None,
        failure_reason: str | None = None,
        evolution: EvolutionOutcome | None = None,
    ) -> PlanningResult:
        evaluations = evolution.evaluations if evolution is not None else 0
        iterations = evolution.generations_executed if evolution is not None else 0
        convergence = evolution.best_path_cost_history if evolution is not None else ()
        return PlanningResult(
            algorithm=self.name,
            success=failure_reason is None,
            path=path,
            path_length=path_length,
            runtime_ms=(perf_counter() - started_at) * 1000,
            expanded_nodes=None,
            evaluations=evaluations,
            iterations=iterations,
            convergence_history=convergence,
            seed=seed,
            failure_reason=failure_reason,
            metadata=self._metadata(
                config,
                evolution,
                stop_reason,
                trajectory_digest,
            ),
        )

    @staticmethod
    def _metadata(
        config: GAConfig,
        evolution: EvolutionOutcome | None,
        stop_reason: str,
        trajectory_digest: str,
    ) -> dict[str, JsonValue]:
        counts = (
            evolution.operator_counts if evolution is not None else OperatorCounts()
        )
        generations_executed = (
            evolution.generations_executed if evolution is not None else 0
        )
        best_fitness_history: list[JsonValue] = (
            list(evolution.best_fitness_history) if evolution is not None else []
        )
        movement: dict[str, JsonValue] = {
            "connectivity": config.movement.connectivity,
            "diagonal_cost": config.movement.diagonal_cost,
            "allow_corner_cutting": config.movement.allow_corner_cutting,
        }
        config_values: dict[str, JsonValue] = {
            "population_size": config.population_size,
            "generations": config.generations,
            "crossover_probability": config.crossover_probability,
            "mutation_probability": config.mutation_probability,
            "tournament_size": config.tournament_size,
            "elite_size": config.elite_size,
            "max_initialization_steps": config.max_initialization_steps,
            "initialization_attempts": config.initialization_attempts,
            "stagnation_generations": config.stagnation_generations,
            "path_length_penalty": config.path_length_penalty,
            "turn_penalty": config.turn_penalty,
            "repeat_penalty": config.repeat_penalty,
            "unreachable_base_penalty": config.unreachable_base_penalty,
            "collision_penalty": config.collision_penalty,
            "remaining_distance_penalty": config.remaining_distance_penalty,
            "crossover_method": config.crossover_method,
            "mutation_method": config.mutation_method,
            "selection_method": config.selection_method,
        }
        return {
            "movement": movement,
            "config": config_values,
            "operators": _operator_metadata(counts),
            "budget": {
                "generation_limit": config.generations,
                "generations_executed": generations_executed,
                "stagnation_limit": config.stagnation_generations,
                "stop_reason": stop_reason,
                "budget_exhausted": generations_executed >= config.generations,
            },
            "best_fitness_history": best_fitness_history,
            "trajectory_digest": trajectory_digest,
        }


def legal_fitness_upper_bound(grid: GridMap, config: GAConfig) -> float:
    edge_count = max(grid.free_cell_count - 1, 0)
    max_step_cost = 1.0
    if config.movement.connectivity == 8:
        max_step_cost = max(max_step_cost, config.movement.diagonal_cost)
    max_path_length = 0.0
    for _ in range(edge_count):
        max_path_length += max_step_cost
    return config.path_length_penalty * max_path_length + config.turn_penalty * max(
        edge_count - 1, 0
    )


def decode_individual(individual: Sequence[Point]) -> tuple[Point, ...]:
    return tuple(individual)


def build_toolbox(
    grid: GridMap,
    start: Point,
    goal: Point,
    config: GAConfig,
    seed: int | None = None,
    operator_rng: random.Random | None = None,
) -> base.Toolbox:
    endpoint_failure = validate_endpoints(grid, start, goal)
    if endpoint_failure is not None:
        raise ValueError(endpoint_failure)
    if not is_reachable(grid, start, goal, config.movement):
        raise ValueError("no_path_precheck")
    config.validate_for_grid(grid)

    master_rng = random.Random(seed)
    toolbox = base.Toolbox()

    def create_individual() -> list[Point]:
        individual_rng = random.Random(master_rng.getrandbits(64))
        path = _initialize_path(grid, start, goal, config, individual_rng)
        return GAIndividual(path)

    toolbox.register("individual", create_individual)
    toolbox.register(
        "evaluate",
        evaluate_individual,
        grid=grid,
        start=start,
        goal=goal,
        config=config,
    )
    _register_evolution_aliases(
        toolbox,
        grid,
        start,
        goal,
        config,
        operator_rng if operator_rng is not None else random.Random(seed),
    )
    return toolbox


def evaluate_individual(
    individual: Sequence[Point],
    grid: GridMap,
    start: Point,
    goal: Point,
    config: GAConfig,
) -> tuple[float]:
    path = decode_individual(individual)
    repeats = len(path) - len(set(path))
    validation = validate_path(grid, path, start, goal, config.movement)
    path_length = _coordinate_path_length(path, config.movement)
    score = (
        config.path_length_penalty * path_length
        + config.turn_penalty * _turn_count(path)
        + config.repeat_penalty * repeats
    )
    if validation.valid and repeats == 0:
        return (score,)

    return (
        config.unreachable_base_penalty
        + score
        + config.collision_penalty
        * _collision_count(grid, path, start, goal, config.movement)
        + config.remaining_distance_penalty * _distance_to_goal(path, goal),
    )


def select_population(
    population: Sequence[Sequence[Point]],
    count: int,
    config: GAConfig,
    rng: random.Random,
) -> list[list[Point]]:
    if count < 0:
        raise ValueError("count must be non-negative")
    if not population:
        raise ValueError("population must not be empty")
    fitness_values = [_fitness_value(individual) for individual in population]
    selected: list[Sequence[Point]]
    if config.selection_method == "tournament":
        if config.tournament_size > len(population):
            raise ValueError("tournament_size must not exceed the population length")
        selected = [
            min(
                rng.sample(list(population), config.tournament_size),
                key=_fitness_value,
            )
            for _ in range(count)
        ]
    else:
        scale = max(abs(value) for value in fitness_values)
        if scale == 0.0:
            selected = rng.choices(list(population), k=count)
        else:
            normalized = [value / scale for value in fitness_values]
            worst = max(normalized)
            weights = [worst - value for value in normalized]
            if sum(weights) == 0.0:
                selected = rng.choices(list(population), k=count)
            else:
                selected = rng.choices(list(population), weights=weights, k=count)
    return [GAIndividual(individual) for individual in selected]


def evolve_population(
    population: Sequence[Sequence[Point]],
    grid: GridMap,
    start: Point,
    goal: Point,
    config: GAConfig,
    rng: random.Random,
    *,
    toolbox: base.Toolbox | None = None,
) -> EvolutionOutcome:
    if len(population) != config.population_size:
        raise ValueError("population length must equal population_size")
    config.validate_for_grid(grid)
    if toolbox is None:
        toolbox = base.Toolbox()
        _register_evolution_aliases(toolbox, grid, start, goal, config, rng)
    current = [GAIndividual(individual) for individual in population]
    evaluations = _evaluate_population(current, grid, start, goal, config)
    best_source = min(current, key=lambda individual: _fitness_value(individual))
    best = GAIndividual(best_source)
    best_fitness = _fitness_value(best_source)
    best_fitness_history: list[float] = []
    best_path_cost_history: list[float] = []
    operator_counts = OperatorCounts()
    trajectory = [_evolution_snapshot(current, operator_counts)]
    stagnation = 0
    stop_reason: EvolutionStopReason = "max_generations"

    for _ in range(config.generations):
        following = toolbox.elite(current, config.elite_size)
        while len(following) < config.population_size:
            parent_a, parent_b = toolbox.select(current, 2)
            crossover = toolbox.mate(parent_a, parent_b)
            operator_counts.repair_successes += crossover.repair_successes
            operator_counts.repair_failures += crossover.repair_failures
            if crossover.status == "skipped":
                operator_counts.crossover_skipped += 1
            else:
                operator_counts.crossover_attempts += 1
                if crossover.status == "succeeded":
                    operator_counts.crossover_succeeded += 1
                else:
                    operator_counts.crossover_failed += 1

            for child in (crossover.child_a, crossover.child_b):
                if len(following) >= config.population_size:
                    break
                mutation = toolbox.mutate(child)
                if mutation.status == "skipped":
                    operator_counts.mutation_skipped += 1
                else:
                    operator_counts.mutation_attempts += 1
                    if mutation.status == "succeeded":
                        operator_counts.mutation_succeeded += 1
                    else:
                        operator_counts.mutation_failed += 1
                following.append(mutation.child)

        evaluations += _evaluate_population(following, grid, start, goal, config)
        generation_best = min(following, key=_fitness_value)
        generation_best_fitness = _fitness_value(generation_best)
        if generation_best_fitness < best_fitness:
            best = GAIndividual(generation_best)
            best_fitness = generation_best_fitness
            stagnation = 0
        else:
            stagnation += 1
        best_fitness_history.append(best_fitness)
        best_path_cost_history.append(_coordinate_path_length(best, config.movement))
        current = following
        trajectory.append(_evolution_snapshot(current, operator_counts))
        if stagnation >= config.stagnation_generations:
            stop_reason = "stagnation"
            break

    return EvolutionOutcome(
        population=tuple(tuple(individual) for individual in current),
        best_individual=tuple(best),
        generations_executed=len(best_fitness_history),
        best_fitness_history=tuple(best_fitness_history),
        best_path_cost_history=tuple(best_path_cost_history),
        evaluations=evaluations,
        operator_counts=operator_counts,
        stop_reason=stop_reason,
        trajectory=tuple(trajectory),
    )


def _register_evolution_aliases(
    toolbox: base.Toolbox,
    grid: GridMap,
    start: Point,
    goal: Point,
    config: GAConfig,
    rng: random.Random,
) -> None:
    toolbox.register("select", select_population, config=config, rng=rng)
    toolbox.register(
        "mate",
        apply_crossover,
        grid=grid,
        start=start,
        goal=goal,
        config=config,
        rng=rng,
    )
    toolbox.register(
        "mutate",
        apply_mutation,
        grid=grid,
        start=start,
        goal=goal,
        config=config,
        rng=rng,
    )
    toolbox.register("elite", _select_elite)


def _select_elite(
    population: Sequence[Sequence[Point]],
    count: int,
) -> list[list[Point]]:
    return [
        GAIndividual(individual)
        for individual in sorted(population, key=_fitness_value)[:count]
    ]


def repair_path(
    path: Sequence[Point],
    grid: GridMap,
    start: Point,
    goal: Point,
    movement: MovementConfig,
    max_steps: int,
    rng: random.Random,
) -> tuple[Point, ...] | None:
    simple = _erase_loops(path)
    if not simple or simple[0] != start or simple[-1] != goal:
        return None
    if validate_path(grid, simple, start, goal, movement).valid:
        return simple

    for index, (current, following) in enumerate(zip(simple, simple[1:], strict=False)):
        if _is_legal_step(grid, current, following, movement):
            continue
        if max_steps <= 0 or not _is_traversable(grid, current):
            return None
        if not _is_traversable(grid, following):
            return None
        connection = _bounded_random_dfs(
            grid,
            current,
            following,
            movement,
            max_steps,
            rng,
        )
        if connection is None:
            return None
        repaired = _erase_loops(simple[:index] + connection + simple[index + 2 :])
        if validate_path(grid, repaired, start, goal, movement).valid:
            return repaired
        return None
    return None


def common_node(
    parent_a: Sequence[Point],
    parent_b: Sequence[Point],
    rng: random.Random,
) -> tuple[tuple[Point, ...], tuple[Point, ...]] | None:
    positions_b = {point: index for index, point in enumerate(parent_b[1:-1], 1)}
    common = [
        (index, positions_b[point])
        for index, point in enumerate(parent_a[1:-1], 1)
        if point in positions_b
    ]
    rng.shuffle(common)
    originals = tuple(parent_a), tuple(parent_b)
    for index_a, index_b in common:
        child_a = _erase_loops(
            tuple(parent_a[: index_a + 1]) + tuple(parent_b[index_b + 1 :])
        )
        child_b = _erase_loops(
            tuple(parent_b[: index_b + 1]) + tuple(parent_a[index_a + 1 :])
        )
        if (child_a, child_b) != originals:
            return child_a, child_b
    return None


def splice_repair(
    parent_a: Sequence[Point],
    parent_b: Sequence[Point],
    grid: GridMap,
    start: Point,
    goal: Point,
    movement: MovementConfig,
    max_steps: int,
    rng: random.Random,
) -> SpliceRepairOutcome:
    if len(parent_a) < 2 or len(parent_b) < 2:
        return SpliceRepairOutcome(None, 0, 0)
    cut_a = rng.randrange(1, len(parent_a))
    cut_b = rng.randrange(1, len(parent_b))
    child_a = repair_path(
        tuple(parent_a[:cut_a]) + tuple(parent_b[cut_b:]),
        grid,
        start,
        goal,
        movement,
        max_steps,
        rng,
    )
    child_b = repair_path(
        tuple(parent_b[:cut_b]) + tuple(parent_a[cut_a:]),
        grid,
        start,
        goal,
        movement,
        max_steps,
        rng,
    )
    repair_successes = int(child_a is not None) + int(child_b is not None)
    repair_failures = 2 - repair_successes
    if child_a is None or child_b is None:
        return SpliceRepairOutcome(None, repair_successes, repair_failures)
    if (child_a, child_b) == (tuple(parent_a), tuple(parent_b)):
        return SpliceRepairOutcome(None, repair_successes, repair_failures)
    return SpliceRepairOutcome(
        (child_a, child_b),
        repair_successes,
        repair_failures,
    )


def reroute_segment(
    path: Sequence[Point],
    grid: GridMap,
    start: Point,
    goal: Point,
    movement: MovementConfig,
    max_steps: int,
    rng: random.Random,
) -> tuple[Point, ...] | None:
    pairs = [
        (left, right)
        for left in range(len(path))
        for right in range(left + 2, len(path))
    ]
    rng.shuffle(pairs)
    original = tuple(path)
    for left, right in pairs:
        replacement = _bounded_random_dfs(
            grid,
            path[left],
            path[right],
            movement,
            max_steps,
            rng,
        )
        if replacement is None:
            continue
        candidate = _erase_loops(
            tuple(path[:left]) + replacement + tuple(path[right + 1 :])
        )
        if candidate != original and _is_valid_simple(
            candidate, grid, start, goal, movement
        ):
            return candidate
    return None


def shortcut(
    path: Sequence[Point],
    grid: GridMap,
    start: Point,
    goal: Point,
    movement: MovementConfig,
    rng: random.Random,
) -> tuple[Point, ...] | None:
    shortcuts = [
        (left, right)
        for left in range(len(path))
        for right in range(left + 2, len(path))
        if _is_legal_step(grid, path[left], path[right], movement)
    ]
    if not shortcuts:
        return None
    left, right = rng.choice(shortcuts)
    candidate = tuple(path[: left + 1]) + tuple(path[right:])
    if _is_valid_simple(candidate, grid, start, goal, movement):
        return candidate
    return None


def apply_crossover(
    parent_a: Sequence[Point],
    parent_b: Sequence[Point],
    grid: GridMap,
    start: Point,
    goal: Point,
    config: GAConfig,
    rng: random.Random,
) -> CrossoverOutcome:
    fallback = GAIndividual(parent_a), GAIndividual(parent_b)
    if rng.random() >= config.crossover_probability:
        return CrossoverOutcome(*fallback, "skipped", 0, 0)
    repair_successes = 0
    repair_failures = 0
    if config.crossover_method == "common_node":
        children = common_node(parent_a, parent_b, rng)
    else:
        splice_outcome = splice_repair(
            parent_a,
            parent_b,
            grid,
            start,
            goal,
            config.movement,
            config.max_initialization_steps,
            rng,
        )
        children = splice_outcome.children
        repair_successes = splice_outcome.repair_successes
        repair_failures = splice_outcome.repair_failures
    if children is None or not all(
        _is_valid_simple(child, grid, start, goal, config.movement)
        for child in children
    ):
        return CrossoverOutcome(
            *fallback,
            "failed",
            repair_successes,
            repair_failures,
        )
    return CrossoverOutcome(
        GAIndividual(children[0]),
        GAIndividual(children[1]),
        "succeeded",
        repair_successes,
        repair_failures,
    )


def apply_mutation(
    parent: Sequence[Point],
    grid: GridMap,
    start: Point,
    goal: Point,
    config: GAConfig,
    rng: random.Random,
) -> MutationOutcome:
    fallback = GAIndividual(parent)
    if rng.random() >= config.mutation_probability:
        return MutationOutcome(fallback, "skipped")
    if config.mutation_method == "reroute_segment":
        child = reroute_segment(
            parent,
            grid,
            start,
            goal,
            config.movement,
            config.max_initialization_steps,
            rng,
        )
    else:
        child = shortcut(parent, grid, start, goal, config.movement, rng)
    if child is None or child == tuple(parent):
        return MutationOutcome(fallback, "failed")
    return MutationOutcome(GAIndividual(child), "succeeded")


def _evaluate_population(
    population: Sequence[Sequence[Point]],
    grid: GridMap,
    start: Point,
    goal: Point,
    config: GAConfig,
) -> int:
    for individual in population:
        individual.fitness.values = evaluate_individual(  # type: ignore[attr-defined]
            individual,
            grid,
            start,
            goal,
            config,
        )
    return len(population)


def _initialize_path(
    grid: GridMap,
    start: Point,
    goal: Point,
    config: GAConfig,
    rng: random.Random,
) -> tuple[Point, ...]:
    if start == goal:
        return (start,)

    for _ in range(config.initialization_attempts):
        path = _bounded_random_dfs(
            grid,
            start,
            goal,
            config.movement,
            config.max_initialization_steps,
            rng,
        )
        if path is not None:
            return _erase_loops(path)
    raise GAInitializationError("bounded random DFS failed to initialize a path")


def _bounded_random_dfs(
    grid: GridMap,
    start: Point,
    goal: Point,
    movement: MovementConfig,
    max_steps: int,
    rng: random.Random,
) -> tuple[Point, ...] | None:
    path = [start]
    visited = {start}
    neighbor_stacks = [_shuffled_neighbors(grid, start, movement, rng)]
    steps = 0

    while neighbor_stacks and steps < max_steps:
        if not neighbor_stacks[-1]:
            neighbor_stacks.pop()
            if neighbor_stacks:
                path.pop()
            continue

        following = neighbor_stacks[-1].pop()
        steps += 1
        if following in visited:
            continue
        visited.add(following)
        path.append(following)
        if following == goal:
            return tuple(path)
        neighbor_stacks.append(_shuffled_neighbors(grid, following, movement, rng))
    return None


def _shuffled_neighbors(
    grid: GridMap,
    point: Point,
    movement: MovementConfig,
    rng: random.Random,
) -> list[Point]:
    neighbors = [neighbor for neighbor, _ in iter_neighbors(grid, point, movement)]
    rng.shuffle(neighbors)
    return neighbors


def _is_traversable(grid: GridMap, point: Point) -> bool:
    return grid.is_within(point) and not grid.is_blocked(point)


def _is_legal_step(
    grid: GridMap,
    current: Point,
    following: Point,
    movement: MovementConfig,
) -> bool:
    if not _is_traversable(grid, current) or not _is_traversable(grid, following):
        return False
    return any(
        neighbor == following for neighbor, _ in iter_neighbors(grid, current, movement)
    )


def _is_valid_simple(
    path: tuple[Point, ...],
    grid: GridMap,
    start: Point,
    goal: Point,
    movement: MovementConfig,
) -> bool:
    return (
        len(path) == len(set(path))
        and validate_path(grid, path, start, goal, movement).valid
    )


def _erase_loops(path: Sequence[Point]) -> tuple[Point, ...]:
    simple: list[Point] = []
    positions: dict[Point, int] = {}
    for point in path:
        if point in positions:
            loop_start = positions[point]
            for removed in simple[loop_start + 1 :]:
                del positions[removed]
            del simple[loop_start + 1 :]
            continue
        positions[point] = len(simple)
        simple.append(point)
    return tuple(simple)


def _turn_count(path: Sequence[Point]) -> int:
    directions = [
        (following[0] - current[0], following[1] - current[1])
        for current, following in zip(path, path[1:], strict=False)
    ]
    return sum(
        current != following
        for current, following in zip(directions, directions[1:], strict=False)
    )


def _coordinate_path_length(
    path: Sequence[Point],
    movement: MovementConfig,
) -> float:
    total = 0.0
    for current, following in zip(path, path[1:], strict=False):
        row_delta = abs(following[0] - current[0])
        column_delta = abs(following[1] - current[1])
        diagonal_steps = min(row_delta, column_delta)
        cardinal_steps = max(row_delta, column_delta) - diagonal_steps
        total += diagonal_steps * movement.diagonal_cost + cardinal_steps
    return total


def _collision_count(
    grid: GridMap,
    path: Sequence[Point],
    start: Point,
    goal: Point,
    movement: MovementConfig,
) -> int:
    collisions = int(not path or path[0] != start) + int(not path or path[-1] != goal)
    collisions += sum(
        not grid.is_within(point) or (grid.is_within(point) and grid.is_blocked(point))
        for point in path
    )
    for current, following in zip(path, path[1:], strict=False):
        if not grid.is_within(current) or grid.is_blocked(current):
            collisions += 1
            continue
        legal_neighbors = {
            neighbor for neighbor, _ in iter_neighbors(grid, current, movement)
        }
        if following not in legal_neighbors:
            collisions += 1
    return collisions


def _distance_to_goal(path: Sequence[Point], goal: Point) -> float:
    if not path:
        return 0.0
    return math.dist(path[-1], goal)


def _fitness_value(individual: Sequence[Point]) -> float:
    fitness = getattr(individual, "fitness", None)
    if fitness is None or not fitness.valid:
        raise ValueError("selection requires evaluated individuals")
    value = float(fitness.values[0])
    if not math.isfinite(value):
        raise ValueError("selection requires finite fitness values")
    return value


def _evolution_snapshot(
    population: Sequence[Sequence[Point]],
    counts: OperatorCounts,
) -> EvolutionSnapshot:
    return EvolutionSnapshot(
        population=tuple(tuple(individual) for individual in population),
        fitness_values=tuple(_fitness_value(individual) for individual in population),
        operator_counts=_operator_count_values(counts),
    )


def _operator_count_values(counts: OperatorCounts) -> tuple[int, ...]:
    return (
        counts.crossover_attempts,
        counts.crossover_succeeded,
        counts.crossover_failed,
        counts.crossover_skipped,
        counts.mutation_attempts,
        counts.mutation_succeeded,
        counts.mutation_failed,
        counts.mutation_skipped,
        counts.repair_successes,
        counts.repair_failures,
    )


def _operator_metadata(counts: OperatorCounts) -> dict[str, JsonValue]:
    return {
        "crossover": {
            "attempts": counts.crossover_attempts,
            "succeeded": counts.crossover_succeeded,
            "failed": counts.crossover_failed,
            "skipped": counts.crossover_skipped,
        },
        "mutation": {
            "attempts": counts.mutation_attempts,
            "succeeded": counts.mutation_succeeded,
            "failed": counts.mutation_failed,
            "skipped": counts.mutation_skipped,
        },
        "repair": {
            "successes": counts.repair_successes,
            "failures": counts.repair_failures,
        },
    }


def _trajectory_digest(
    initial_population: tuple[tuple[Point, ...], ...],
    trajectory: tuple[EvolutionSnapshot, ...],
) -> str:
    payload = {
        "initial_population": initial_population,
        "generations": [
            {
                "population": snapshot.population,
                "fitness_values": snapshot.fitness_values,
                "operator_counts": snapshot.operator_counts,
            }
            for snapshot in trajectory
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _require_positive_integer(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_non_negative_integer(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_probability(name: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and between 0 and 1")


def _require_positive_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


def _require_non_negative_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
