from typing import Protocol, TypeVar, runtime_checkable

from path_planning.core.grid import GridMap
from path_planning.core.result import PlanningResult
from path_planning.core.types import Point

ConfigT = TypeVar("ConfigT", contravariant=True)


@runtime_checkable
class Planner(Protocol[ConfigT]):
    name: str

    def plan(
        self,
        grid: GridMap,
        start: Point,
        goal: Point,
        config: ConfigT,
        seed: int | None = None,
    ) -> PlanningResult: ...
