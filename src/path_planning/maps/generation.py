import math
from dataclasses import dataclass

import numpy as np

from path_planning.core.grid import GridMap
from path_planning.core.types import Point
from path_planning.maps.io import MapScenario


@dataclass(frozen=True, slots=True)
class RandomMapConfig:
    rows: int
    columns: int
    target_density: float
    seed: int
    start: Point
    goal: Point
    guarantee_reachable: bool

    def __post_init__(self) -> None:
        for name, value in (("rows", self.rows), ("columns", self.columns)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (
            not isinstance(self.target_density, (int, float))
            or isinstance(self.target_density, bool)
            or not math.isfinite(self.target_density)
            or not 0 <= self.target_density < 1
        ):
            raise ValueError("target_density must be finite and in [0, 1)")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")
        if not isinstance(self.guarantee_reachable, bool):
            raise TypeError("guarantee_reachable must be boolean")
        for name, point in (("start", self.start), ("goal", self.goal)):
            if (
                not isinstance(point, tuple)
                or len(point) != 2
                or any(
                    isinstance(value, bool) or not isinstance(value, int)
                    for value in point
                )
            ):
                raise TypeError(f"{name} must be an integer coordinate tuple")
            if not (0 <= point[0] < self.rows and 0 <= point[1] < self.columns):
                raise ValueError(f"{name} is outside configured map bounds")


def generated_scenario_name(config: RandomMapConfig) -> str:
    density_percent = round(config.target_density * 100)
    return (
        f"random_{config.rows}x{config.columns}_"
        f"d{density_percent:02d}_seed{config.seed}"
    )


def generate_random_scenario(
    config: RandomMapConfig,
    name: str | None = None,
) -> MapScenario:
    protected = {config.start, config.goal}
    strategy = "random_obstacles"
    if config.guarantee_reachable:
        protected.update(_manhattan_corridor(config.start, config.goal))
        strategy = "protected_manhattan_corridor"

    candidates = [
        (row, column)
        for row in range(config.rows)
        for column in range(config.columns)
        if (row, column) not in protected
    ]
    obstacle_count = round(config.rows * config.columns * config.target_density)
    if obstacle_count > len(candidates):
        raise ValueError("target obstacle count exceeds unprotected cell capacity")

    cells = np.zeros((config.rows, config.columns), dtype=bool)
    if obstacle_count:
        rng = np.random.default_rng(config.seed)
        selected = rng.choice(len(candidates), size=obstacle_count, replace=False)
        for index in selected:
            cells[candidates[int(index)]] = True

    actual_density = obstacle_count / (config.rows * config.columns)
    return MapScenario(
        name=name or generated_scenario_name(config),
        grid=GridMap(cells),
        start=config.start,
        goal=config.goal,
        metadata={
            "rows": config.rows,
            "columns": config.columns,
            "target_density": float(config.target_density),
            "actual_density": actual_density,
            "seed": config.seed,
            "generation_strategy": strategy,
            "guarantee_reachable": config.guarantee_reachable,
        },
    )


def _manhattan_corridor(start: Point, goal: Point) -> set[Point]:
    row_step = 1 if goal[0] >= start[0] else -1
    column_step = 1 if goal[1] >= start[1] else -1
    corridor = {
        (row, start[1]) for row in range(start[0], goal[0] + row_step, row_step)
    }
    corridor.update(
        (goal[0], column)
        for column in range(start[1], goal[1] + column_step, column_step)
    )
    return corridor
