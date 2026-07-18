from collections import deque
from dataclasses import dataclass

from path_planning.core.grid import GridMap
from path_planning.core.movement import MovementConfig, iter_neighbors
from path_planning.core.types import Point


@dataclass(frozen=True, slots=True)
class PathValidation:
    valid: bool
    path_length: float | None
    failure_reason: str | None


def validate_endpoints(grid: GridMap, start: Point, goal: Point) -> str | None:
    if not grid.is_within(start):
        return "start_out_of_bounds"
    if not grid.is_within(goal):
        return "goal_out_of_bounds"
    if grid.is_blocked(start):
        return "start_blocked"
    if grid.is_blocked(goal):
        return "goal_blocked"
    return None


def validate_path(
    grid: GridMap,
    path: tuple[Point, ...],
    start: Point,
    goal: Point,
    movement: MovementConfig,
) -> PathValidation:
    endpoint_failure = validate_endpoints(grid, start, goal)
    if endpoint_failure is not None:
        return PathValidation(False, None, endpoint_failure)
    if not path:
        return PathValidation(False, None, "empty_path")
    if path[0] != start:
        return PathValidation(False, None, "wrong_start")
    if path[-1] != goal:
        return PathValidation(False, None, "wrong_goal")

    for point in path:
        if not grid.is_within(point):
            return PathValidation(False, None, "path_out_of_bounds")
        if grid.is_blocked(point):
            return PathValidation(False, None, "path_hits_obstacle")

    total = 0.0
    for current, following in zip(path, path[1:], strict=False):
        neighbors = dict(iter_neighbors(grid, current, movement))
        cost = neighbors.get(following)
        if cost is None:
            return PathValidation(False, None, "invalid_step")
        total += cost

    return PathValidation(True, total, None)


def is_reachable(
    grid: GridMap,
    start: Point,
    goal: Point,
    movement: MovementConfig,
) -> bool:
    if validate_endpoints(grid, start, goal) is not None:
        return False
    if start == goal:
        return True

    frontier = deque([start])
    visited = {start}
    while frontier:
        current = frontier.popleft()
        for neighbor, _ in iter_neighbors(grid, current, movement):
            if neighbor == goal:
                return True
            if neighbor not in visited:
                visited.add(neighbor)
                frontier.append(neighbor)
    return False
