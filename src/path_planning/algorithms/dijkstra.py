import heapq
from dataclasses import dataclass
from time import perf_counter

from path_planning.algorithms.base import reconstruct_path
from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig, iter_neighbors
from path_planning.core.result import PlanningResult
from path_planning.core.types import JsonValue, Point
from path_planning.core.validation import validate_endpoints, validate_path


@dataclass(frozen=True, slots=True)
class DijkstraConfig:
    movement: MovementConfig


class DijkstraPlanner:
    name = "dijkstra"

    def plan(
        self,
        grid: GridMap,
        start: Point,
        goal: Point,
        config: DijkstraConfig,
        seed: int | None = None,
    ) -> PlanningResult:
        del seed
        started_at = perf_counter()
        endpoint_failure = validate_endpoints(grid, start, goal)
        if endpoint_failure is not None:
            return self._failure(started_at, endpoint_failure, 0, config)

        frontier: list[tuple[float, Point]] = [(0.0, start)]
        g_score = {start: 0.0}
        came_from: dict[Point, Point] = {}
        closed: set[Point] = set()

        while frontier:
            current_cost, current = heapq.heappop(frontier)
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
                    raise RuntimeError("Dijkstra reconstructed an invalid path")
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
                    heapq.heappush(frontier, (candidate_cost, neighbor))

        return self._failure(started_at, "no_path", len(closed), config)

    def _failure(
        self,
        started_at: float,
        reason: str,
        expanded_nodes: int,
        config: DijkstraConfig,
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
    def _metadata(config: DijkstraConfig) -> dict[str, JsonValue]:
        movement = config.movement
        return {
            "movement": {
                "connectivity": movement.connectivity,
                "diagonal_cost": movement.diagonal_cost,
                "allow_corner_cutting": movement.allow_corner_cutting,
            }
        }
