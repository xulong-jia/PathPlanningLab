from pathlib import Path

import pytest

from path_planning.algorithms.astar import AStarConfig, AStarPlanner
from path_planning.algorithms.dijkstra import DijkstraConfig, DijkstraPlanner
from path_planning.core.movement import MovementConfig
from path_planning.core.validation import validate_path
from path_planning.maps.io import load_scenario

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HANDCRAFTED = PROJECT_ROOT / "maps" / "handcrafted"
REACHABLE_MAP_NAMES = (
    "open_20",
    "narrow_channel_20",
    "maze_30",
    "dead_ends_30",
    "bottleneck_50",
)
ASTAR_CONFIGS = (
    AStarConfig(MovementConfig(4), "manhattan"),
    AStarConfig(MovementConfig(4), "euclidean"),
    AStarConfig(MovementConfig(8), "octile"),
    AStarConfig(MovementConfig(8), "euclidean"),
)


@pytest.mark.parametrize("map_name", REACHABLE_MAP_NAMES)
@pytest.mark.parametrize("astar_config", ASTAR_CONFIGS)
def test_astar_admissible_heuristics_match_dijkstra_optimal_cost(
    map_name: str,
    astar_config: AStarConfig,
) -> None:
    scenario = load_scenario(HANDCRAFTED / f"{map_name}.json")
    movement = astar_config.movement
    dijkstra = DijkstraPlanner().plan(
        scenario.grid,
        scenario.start,
        scenario.goal,
        DijkstraConfig(movement),
    )
    astar = AStarPlanner().plan(
        scenario.grid,
        scenario.start,
        scenario.goal,
        astar_config,
    )

    assert dijkstra.success
    assert astar.success
    assert astar.path_length == pytest.approx(dijkstra.path_length)
    validation = validate_path(
        scenario.grid,
        astar.path,
        scenario.start,
        scenario.goal,
        movement,
    )
    assert validation.valid
    assert astar.path_length == pytest.approx(validation.path_length)
