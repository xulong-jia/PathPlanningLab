import heapq
import math
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from path_planning.algorithms.base import reconstruct_path
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig, iter_neighbors
from path_planning.core.result import PlanningResult
from path_planning.core.types import JsonValue, Point
from path_planning.core.validation import validate_endpoints, validate_path

HeuristicName = Literal["manhattan", "euclidean", "octile"]


@dataclass(frozen=True, slots=True)
class AStarConfig:
    movement: MovementConfig
    heuristic: HeuristicName | None = None

    def __post_init__(self) -> None:
        heuristic = self.heuristic
        if heuristic is None:
            heuristic = "manhattan" if self.movement.connectivity == 4 else "octile"
        if heuristic not in ("manhattan", "euclidean", "octile"):
            raise ValueError(f"unknown heuristic: {heuristic}")
        if heuristic == "manhattan" and self.movement.connectivity != 4:
            raise ValueError("Manhattan heuristic requires 4-way movement")
        if heuristic == "octile" and self.movement.connectivity != 8:
            raise ValueError("Octile heuristic requires 8-way movement")
        object.__setattr__(self, "heuristic", heuristic)


def estimate_cost(point: Point, goal: Point, config: AStarConfig) -> float:
    row_distance = abs(goal[0] - point[0])
    column_distance = abs(goal[1] - point[1])
    heuristic = config.heuristic

    if heuristic == "manhattan":
        return float(row_distance + column_distance)
    if heuristic == "euclidean":
        scale = 1.0
        if config.movement.connectivity == 8:
            scale = min(1.0, config.movement.diagonal_cost / math.sqrt(2))
        return math.hypot(row_distance, column_distance) * scale

    major = max(row_distance, column_distance)
    minor = min(row_distance, column_distance)
    diagonal_cost = config.movement.diagonal_cost
    if diagonal_cost >= 2:
        return float(major + minor)
    if diagonal_cost >= 1:
        return minor * diagonal_cost + (major - minor)
    if (major - minor) % 2 == 0:
        return major * diagonal_cost
    return (major - 1) * diagonal_cost + 1


class AStarPlanner:
    name = "astar"

    def plan(
        self,
        grid: GridMap,
        start: Point,
        goal: Point,
        config: AStarConfig,
        seed: int | None = None,
    ) -> PlanningResult:
        del seed
        started_at = perf_counter()
        endpoint_failure = validate_endpoints(grid, start, goal)
        if endpoint_failure is not None:
            return self._failure(started_at, endpoint_failure, 0, config)

        initial_h = estimate_cost(start, goal, config)
        frontier: list[tuple[float, float, float, Point]] = [
            (initial_h, initial_h, 0.0, start)
        ]
        g_score = {start: 0.0}
        came_from: dict[Point, Point] = {}
        closed: set[Point] = set()

        while frontier:
            _, _, current_cost, current = heapq.heappop(frontier)
            if current in closed:
                continue
            closed.add(current)

            if current == goal:
                path = reconstruct_path(came_from, goal)
                validation = validate_path(
                    grid,
                    path,
                    start,
                    goal,
                    config.movement,
                )
                if not validation.valid or validation.path_length is None:
                    raise RuntimeError("A* reconstructed an invalid path")
                return PlanningResult(
                    algorithm=self.name,
                    success=True,
                    path=path,
                    path_length=validation.path_length,
                    runtime_ms=self._runtime_ms(started_at),
                    expanded_nodes=len(closed),
                    evaluations=None,
                    iterations=0,
                    convergence_history=(),
                    seed=None,
                    failure_reason=None,
                    metadata=self._metadata(config),
                )

            for neighbor, step_cost in iter_neighbors(
                grid,
                current,
                config.movement,
            ):
                candidate_cost = current_cost + step_cost
                if candidate_cost < g_score.get(neighbor, float("inf")):
                    g_score[neighbor] = candidate_cost
                    came_from[neighbor] = current
                    heuristic_cost = estimate_cost(neighbor, goal, config)
                    heapq.heappush(
                        frontier,
                        (
                            candidate_cost + heuristic_cost,
                            heuristic_cost,
                            candidate_cost,
                            neighbor,
                        ),
                    )

        return self._failure(started_at, "no_path", len(closed), config)

    def _failure(
        self,
        started_at: float,
        reason: str,
        expanded_nodes: int,
        config: AStarConfig,
    ) -> PlanningResult:
        return PlanningResult(
            algorithm=self.name,
            success=False,
            path=(),
            path_length=None,
            runtime_ms=self._runtime_ms(started_at),
            expanded_nodes=expanded_nodes,
            evaluations=None,
            iterations=0,
            convergence_history=(),
            seed=None,
            failure_reason=reason,
            metadata=self._metadata(config),
        )

    @staticmethod
    def _runtime_ms(started_at: float) -> float:
        return (perf_counter() - started_at) * 1000

    @staticmethod
    def _metadata(config: AStarConfig) -> dict[str, JsonValue]:
        movement = config.movement
        return {
            "heuristic": config.heuristic,
            "movement": {
                "connectivity": movement.connectivity,
                "diagonal_cost": movement.diagonal_cost,
                "allow_corner_cutting": movement.allow_corner_cutting,
            },
        }
