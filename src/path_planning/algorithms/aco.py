import hashlib
import json
import math
from dataclasses import dataclass
from time import perf_counter

import numpy as np
from numpy.typing import NDArray

from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig, iter_neighbors
from path_planning.core.result import PlanningResult
from path_planning.core.types import JsonValue, Point
from path_planning.core.validation import (
    is_reachable,
    validate_endpoints,
    validate_path,
)

_CARDINAL_OFFSETS = ((-1, 0), (0, 1), (1, 0), (0, -1))
_DIAGONAL_OFFSETS = ((-1, -1), (-1, 1), (1, 1), (1, -1))
_HEURISTIC_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class ACOConfig:
    movement: MovementConfig
    ants: int
    alpha: float
    beta: float
    evaporation_rate: float
    pheromone_deposit: float
    elite_weight: float
    min_pheromone: float
    max_pheromone: float
    iterations: int
    max_steps: int
    max_restarts: int
    max_backtracks: int
    stagnation_iterations: int

    def __post_init__(self) -> None:
        for name in ("ants", "iterations", "max_steps", "stagnation_iterations"):
            _require_positive_integer(name, getattr(self, name))
        for name in ("max_restarts", "max_backtracks"):
            _require_non_negative_integer(name, getattr(self, name))
        for name in ("alpha", "beta", "elite_weight"):
            _require_non_negative_number(name, getattr(self, name))
        _require_non_negative_number("evaporation_rate", self.evaporation_rate)
        if self.evaporation_rate >= 1:
            raise ValueError("evaporation_rate must be less than 1")
        _require_positive_number("pheromone_deposit", self.pheromone_deposit)
        _require_positive_number("min_pheromone", self.min_pheromone)
        _require_positive_number("max_pheromone", self.max_pheromone)
        if self.max_pheromone < self.min_pheromone:
            raise ValueError("max_pheromone must be at least min_pheromone")


@dataclass(frozen=True, slots=True)
class AntConstruction:
    path: tuple[Point, ...] | None
    steps: int
    restarts: int
    backtracks: int
    sampling_trace: tuple[float, ...]


class AntColonyPlanner:
    name = "aco"

    def plan(
        self,
        grid: GridMap,
        start: Point,
        goal: Point,
        config: ACOConfig,
        seed: int | None = None,
    ) -> PlanningResult:
        started_at = perf_counter()
        trajectory_hasher = hashlib.sha256()
        precheck_failure = _precheck_failure(
            grid,
            start,
            goal,
            config.movement,
        )
        if precheck_failure is not None:
            return self._result(
                started_at=started_at,
                config=config,
                seed=seed,
                failure_reason=precheck_failure,
                trajectory_digest=trajectory_hasher.hexdigest(),
            )
        if start == goal:
            return self._result(
                started_at=started_at,
                config=config,
                seed=seed,
                path=(start,),
                path_length=0.0,
                trajectory_digest=trajectory_hasher.hexdigest(),
            )

        rng = np.random.default_rng(seed)
        pheromone = _initialize_pheromone(grid, config)
        global_best_path: tuple[Point, ...] | None = None
        global_best_cost: float | None = None
        convergence_history: list[float | None] = []
        stagnant_rounds = 0
        constructed_paths = 0
        successful_path_count = 0
        construction_steps = 0
        restart_count = 0
        backtrack_count = 0

        for iteration in range(config.iterations):
            successful_paths: list[tuple[tuple[Point, ...], float]] = []
            round_best_path: tuple[Point, ...] | None = None
            round_best_cost: float | None = None

            for ant in range(config.ants):
                construction = _construct_ant_path(
                    grid,
                    start,
                    goal,
                    config,
                    pheromone,
                    rng,
                )
                constructed_paths += 1
                construction_steps += construction.steps
                restart_count += construction.restarts
                backtrack_count += construction.backtracks
                _record_trajectory(trajectory_hasher, iteration, ant, construction)

                if construction.path is None:
                    continue
                validation = validate_path(
                    grid,
                    construction.path,
                    start,
                    goal,
                    config.movement,
                )
                if not validation.valid or validation.path_length is None:
                    raise RuntimeError("ACO constructed an invalid path")
                cost = validation.path_length
                successful_paths.append((construction.path, cost))
                successful_path_count += 1
                if round_best_cost is None or cost < round_best_cost:
                    round_best_path = construction.path
                    round_best_cost = cost

            next_best_cost, stagnant_rounds = _update_convergence(
                global_best_cost,
                round_best_cost,
                stagnant_rounds,
            )
            if next_best_cost != global_best_cost:
                if round_best_path is None:
                    raise RuntimeError("ACO best cost is missing its path")
                global_best_path = round_best_path
            global_best_cost = next_best_cost
            elite_best = None
            if global_best_path is not None and global_best_cost is not None:
                elite_best = global_best_path, global_best_cost
            _update_pheromone(
                pheromone,
                tuple(successful_paths),
                elite_best,
                config,
            )
            convergence_history.append(global_best_cost)
            if stagnant_rounds >= config.stagnation_iterations:
                break

        if global_best_path is None or global_best_cost is None:
            return self._result(
                started_at=started_at,
                config=config,
                seed=seed,
                failure_reason="construction_failed",
                iterations=len(convergence_history),
                convergence_history=tuple(convergence_history),
                constructed_paths=constructed_paths,
                successful_paths=successful_path_count,
                construction_steps=construction_steps,
                restarts=restart_count,
                backtracks=backtrack_count,
                trajectory_digest=trajectory_hasher.hexdigest(),
            )

        final_validation = validate_path(
            grid,
            global_best_path,
            start,
            goal,
            config.movement,
        )
        if not final_validation.valid or final_validation.path_length is None:
            raise RuntimeError("ACO selected an invalid global best path")
        return self._result(
            started_at=started_at,
            config=config,
            seed=seed,
            path=global_best_path,
            path_length=final_validation.path_length,
            iterations=len(convergence_history),
            convergence_history=tuple(convergence_history),
            constructed_paths=constructed_paths,
            successful_paths=successful_path_count,
            construction_steps=construction_steps,
            restarts=restart_count,
            backtracks=backtrack_count,
            trajectory_digest=trajectory_hasher.hexdigest(),
        )

    def _result(
        self,
        *,
        started_at: float,
        config: ACOConfig,
        seed: int | None,
        path: tuple[Point, ...] = (),
        path_length: float | None = None,
        failure_reason: str | None = None,
        iterations: int = 0,
        convergence_history: tuple[float | None, ...] = (),
        constructed_paths: int = 0,
        successful_paths: int = 0,
        construction_steps: int = 0,
        restarts: int = 0,
        backtracks: int = 0,
        trajectory_digest: str,
    ) -> PlanningResult:
        success = failure_reason is None
        return PlanningResult(
            algorithm=self.name,
            success=success,
            path=path,
            path_length=path_length,
            runtime_ms=(perf_counter() - started_at) * 1000,
            expanded_nodes=None,
            evaluations=constructed_paths,
            iterations=iterations,
            convergence_history=convergence_history,
            seed=seed,
            failure_reason=failure_reason,
            metadata=self._metadata(
                config,
                constructed_paths,
                successful_paths,
                construction_steps,
                restarts,
                backtracks,
                trajectory_digest,
            ),
        )

    @staticmethod
    def _metadata(
        config: ACOConfig,
        constructed_paths: int,
        successful_paths: int,
        construction_steps: int,
        restarts: int,
        backtracks: int,
        trajectory_digest: str,
    ) -> dict[str, JsonValue]:
        movement: dict[str, JsonValue] = {
            "connectivity": config.movement.connectivity,
            "diagonal_cost": config.movement.diagonal_cost,
            "allow_corner_cutting": config.movement.allow_corner_cutting,
        }
        config_values: dict[str, JsonValue] = {
            "ants": config.ants,
            "alpha": config.alpha,
            "beta": config.beta,
            "evaporation_rate": config.evaporation_rate,
            "pheromone_deposit": config.pheromone_deposit,
            "elite_weight": config.elite_weight,
            "min_pheromone": config.min_pheromone,
            "max_pheromone": config.max_pheromone,
            "iterations": config.iterations,
            "max_steps": config.max_steps,
            "max_restarts": config.max_restarts,
            "max_backtracks": config.max_backtracks,
            "stagnation_iterations": config.stagnation_iterations,
        }
        return {
            "movement": movement,
            "config": config_values,
            "constructed_paths": constructed_paths,
            "successful_paths": successful_paths,
            "construction_steps": construction_steps,
            "restarts": restarts,
            "backtracks": backtracks,
            "trajectory_digest": trajectory_digest,
        }


def _initialize_pheromone(
    grid: GridMap,
    config: ACOConfig,
) -> NDArray[np.float64]:
    initial = min(max(1.0, config.min_pheromone), config.max_pheromone)
    shape = (*grid.shape, len(_movement_offsets(config.movement)))
    return np.full(shape, initial, dtype=np.float64)


def _transition_weights(
    pheromone_values: NDArray[np.float64],
    goal_distances: NDArray[np.float64],
    config: ACOConfig,
) -> NDArray[np.float64]:
    heuristic = 1.0 / (goal_distances + _HEURISTIC_EPSILON)
    return np.power(pheromone_values, config.alpha) * np.power(
        heuristic,
        config.beta,
    )


def _construct_ant_path(
    grid: GridMap,
    start: Point,
    goal: Point,
    config: ACOConfig,
    pheromone: NDArray[np.float64],
    rng: np.random.Generator,
) -> AntConstruction:
    expected_shape = (*grid.shape, len(_movement_offsets(config.movement)))
    if pheromone.shape != expected_shape:
        raise ValueError(f"pheromone shape must be {expected_shape}")
    if start == goal:
        return AntConstruction((start,), 0, 0, 0, ())

    offset_indices = {
        offset: index for index, offset in enumerate(_movement_offsets(config.movement))
    }
    total_steps = 0
    restarts = 0
    backtracks = 0
    sampling_trace: list[float] = []

    for attempt in range(config.max_restarts + 1):
        path = [start]
        visited = {start}
        attempt_steps = 0

        while attempt_steps < config.max_steps:
            current = path[-1]
            candidates: list[Point] = []
            pheromone_values: list[float] = []
            goal_distances: list[float] = []

            for neighbor, _ in iter_neighbors(grid, current, config.movement):
                if neighbor in visited:
                    continue
                offset = neighbor[0] - current[0], neighbor[1] - current[1]
                candidates.append(neighbor)
                pheromone_values.append(
                    float(pheromone[current[0], current[1], offset_indices[offset]])
                )
                goal_distances.append(math.dist(neighbor, goal))

            if not candidates:
                if len(path) > 1 and backtracks < config.max_backtracks:
                    path.pop()
                    backtracks += 1
                    continue
                break

            weights = _transition_weights(
                np.asarray(pheromone_values, dtype=np.float64),
                np.asarray(goal_distances, dtype=np.float64),
                config,
            )
            selected, draw = _weighted_choice(weights, rng)
            sampling_trace.append(draw)
            following = candidates[selected]
            path.append(following)
            visited.add(following)
            attempt_steps += 1
            total_steps += 1

            if following == goal:
                return AntConstruction(
                    tuple(path),
                    total_steps,
                    restarts,
                    backtracks,
                    tuple(sampling_trace),
                )

        if attempt < config.max_restarts:
            restarts += 1

    return AntConstruction(
        None,
        total_steps,
        restarts,
        backtracks,
        tuple(sampling_trace),
    )


def _deposit_path(
    pheromone: NDArray[np.float64],
    path: tuple[Point, ...],
    amount: float,
    movement: MovementConfig,
) -> None:
    _require_positive_number("amount", amount)
    offset_indices = {
        offset: index for index, offset in enumerate(_movement_offsets(movement))
    }
    for current, following in zip(path, path[1:], strict=False):
        offset = following[0] - current[0], following[1] - current[1]
        reverse = -offset[0], -offset[1]
        if offset not in offset_indices or reverse not in offset_indices:
            raise ValueError(
                f"path contains an invalid movement: {current} -> {following}"
            )
        pheromone[current[0], current[1], offset_indices[offset]] += amount
        pheromone[following[0], following[1], offset_indices[reverse]] += amount


def _update_pheromone(
    pheromone: NDArray[np.float64],
    successful_paths: tuple[tuple[tuple[Point, ...], float], ...],
    global_best: tuple[tuple[Point, ...], float] | None,
    config: ACOConfig,
) -> None:
    pheromone *= 1.0 - config.evaporation_rate
    for path, length in successful_paths:
        _require_positive_number("path length", length)
        _deposit_path(
            pheromone,
            path,
            config.pheromone_deposit / length,
            config.movement,
        )
    if global_best is not None and config.elite_weight > 0:
        path, length = global_best
        _require_positive_number("global best length", length)
        _deposit_path(
            pheromone,
            path,
            config.elite_weight * config.pheromone_deposit / length,
            config.movement,
        )
    np.clip(
        pheromone,
        config.min_pheromone,
        config.max_pheromone,
        out=pheromone,
    )


def _update_convergence(
    global_best_cost: float | None,
    round_best_cost: float | None,
    stagnant_rounds: int,
) -> tuple[float | None, int]:
    if round_best_cost is not None and (
        global_best_cost is None or round_best_cost < global_best_cost
    ):
        return round_best_cost, 0
    return global_best_cost, stagnant_rounds + 1


def _precheck_failure(
    grid: GridMap,
    start: Point,
    goal: Point,
    movement: MovementConfig,
) -> str | None:
    endpoint_failure = validate_endpoints(grid, start, goal)
    if endpoint_failure is not None:
        return endpoint_failure
    if not is_reachable(grid, start, goal, movement):
        return "no_path_precheck"
    return None


def _movement_offsets(movement: MovementConfig) -> tuple[tuple[int, int], ...]:
    if movement.connectivity == 8:
        return _CARDINAL_OFFSETS + _DIAGONAL_OFFSETS
    return _CARDINAL_OFFSETS


def _weighted_choice(
    weights: NDArray[np.float64],
    rng: np.random.Generator,
) -> tuple[int, float]:
    finite_weights = weights
    if np.isinf(weights).any():
        finite_weights = np.isinf(weights).astype(np.float64)
    total = float(finite_weights.sum())
    if not math.isfinite(total) or total <= 0:
        finite_weights = np.ones_like(finite_weights)
        total = float(len(finite_weights))

    draw = float(rng.random())
    threshold = draw * total
    cumulative = 0.0
    for index, weight in enumerate(finite_weights):
        cumulative += float(weight)
        if threshold < cumulative:
            return index, draw
    return len(finite_weights) - 1, draw


def _record_trajectory(
    hasher: "hashlib._Hash",
    iteration: int,
    ant: int,
    construction: AntConstruction,
) -> None:
    payload = {
        "iteration": iteration,
        "ant": ant,
        "path": construction.path,
        "steps": construction.steps,
        "restarts": construction.restarts,
        "backtracks": construction.backtracks,
        "sampling_trace": construction.sampling_trace,
    }
    hasher.update(
        json.dumps(
            payload,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _require_positive_integer(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_non_negative_integer(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


def _require_non_negative_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
