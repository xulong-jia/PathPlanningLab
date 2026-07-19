import json
import math

import pandas as pd
import pytest

from path_planning.benchmark.statistics import best_worst_runs, summarize_runs


def _row(
    algorithm: str,
    *,
    config_name: str | None = None,
    seed: int | None = None,
    status: str = "success",
    success: bool | None = True,
    error: str | None = None,
    path: object = ((0, 0), (0, 1)),
    path_length: float | None = 1.0,
    runtime_ms: float | None = 1.0,
    wall_runtime_ms: float = 2.0,
    expanded_nodes: int | None = None,
    evaluations: int | None = None,
    iterations: int | None = None,
    map_name: str = "map",
    map_path: str = "maps/map.json",
    start: tuple[int, int] = (0, 0),
    goal: tuple[int, int] = (0, 2),
    connectivity: int = 4,
    diagonal_cost: float = math.sqrt(2.0),
    allow_corner_cutting: bool = False,
) -> dict[str, object]:
    return {
        "algorithm": algorithm,
        "map_name": map_name,
        "map_path": map_path,
        "start_row": start[0],
        "start_column": start[1],
        "goal_row": goal[0],
        "goal_column": goal[1],
        "connectivity": connectivity,
        "diagonal_cost": diagonal_cost,
        "allow_corner_cutting": allow_corner_cutting,
        "config_name": config_name or f"configs/{algorithm}.yaml",
        "seed": seed,
        "status": status,
        "error": error,
        "success": success,
        "path_json": None if path is None else json.dumps(path),
        "path_length": path_length,
        "runtime_ms": runtime_ms,
        "wall_runtime_ms": wall_runtime_ms,
        "expanded_nodes": expanded_nodes,
        "evaluations": evaluations,
        "iterations": iterations,
    }


def _summary_row(summary: pd.DataFrame, algorithm: str, config_name: str):
    matches = summary[
        (summary["algorithm"] == algorithm) & (summary["config_name"] == config_name)
    ]
    assert len(matches) == 1
    return matches.iloc[0]


def test_summarize_runs_keeps_failures_and_computes_each_metric_family() -> None:
    rows = [
        _row(
            "dijkstra",
            path=((0, 0), (0, 1), (0, 2)),
            path_length=4.0,
            expanded_nodes=20,
            iterations=0,
        ),
        _row(
            "aco",
            config_name="configs/aco-a.yaml",
            seed=11,
            path=((0, 0), (0, 1), (1, 1)),
            path_length=6.0,
            runtime_ms=10.0,
            wall_runtime_ms=12.0,
            evaluations=100,
            iterations=3,
        ),
        _row(
            "aco",
            config_name="configs/aco-a.yaml",
            seed=29,
            path=((0, 0), (0, 0), (0, 1), (0, 2)),
            path_length=4.0,
            runtime_ms=20.0,
            wall_runtime_ms=22.0,
            evaluations=200,
            iterations=5,
        ),
        _row(
            "aco",
            config_name="configs/aco-a.yaml",
            seed=47,
            status="failed",
            success=False,
            error="no path",
            path=((0, 0), (1, 0), (1, 1)),
            path_length=999.0,
            runtime_ms=999.0,
            wall_runtime_ms=32.0,
            evaluations=999,
            iterations=999,
        ),
        _row(
            "aco",
            config_name="configs/aco-b.yaml",
            seed=11,
            path_length=8.0,
            evaluations=300,
            iterations=7,
        ),
    ]

    summary = summarize_runs(pd.DataFrame(rows))
    aco = _summary_row(summary, "aco", "configs/aco-a.yaml")

    assert aco["run_count"] == 3
    assert aco["success_count"] == 2
    assert aco["success_rate"] == pytest.approx(2 / 3)
    assert aco["path_length_mean"] == 5.0
    assert aco["path_length_std"] == pytest.approx(math.sqrt(2.0))
    assert aco["path_length_min"] == 4.0
    assert aco["path_length_max"] == 6.0
    assert aco["path_length_median"] == 5.0
    assert aco["normalized_path_cost_mean"] == 1.25
    assert aco["normalized_path_cost_std"] == pytest.approx(math.sqrt(0.125))
    assert aco["runtime_ms_mean"] == 15.0
    assert aco["runtime_ms_std"] == pytest.approx(math.sqrt(50.0))
    assert aco["wall_runtime_ms_mean"] == 17.0
    assert aco["evaluations_mean"] == 150.0
    assert aco["iterations_mean"] == 4.0
    assert aco["turning_count_mean"] == 0.5
    assert aco["turning_count_std"] == pytest.approx(math.sqrt(0.5))
    assert aco["expanded_nodes_mean"] is None

    dijkstra = _summary_row(summary, "dijkstra", "configs/dijkstra.yaml")
    assert dijkstra["expanded_nodes_mean"] == 20.0
    assert dijkstra["evaluations_mean"] is None

    singleton = _summary_row(summary, "aco", "configs/aco-b.yaml")
    assert singleton["path_length_std"] is None
    assert singleton["normalized_path_cost_mean"] == 2.0
    json.dumps(summary.to_dict(orient="records"), allow_nan=False)


def test_normalization_uses_minimum_valid_dijkstra_cost_for_exact_task() -> None:
    rows = [
        _row("dijkstra", path_length=5.0),
        _row("dijkstra", path_length=4.0),
        _row("aco", seed=11, path_length=6.0),
        _row("aco", seed=29, path_length=3.0, connectivity=8),
        _row(
            "dijkstra",
            path_length=0.0,
            start=(1, 1),
            goal=(1, 1),
            map_name="same-point",
        ),
        _row(
            "ga",
            seed=11,
            path_length=0.0,
            start=(1, 1),
            goal=(1, 1),
            map_name="same-point",
        ),
    ]

    summary = summarize_runs(pd.DataFrame(rows))

    four_way = summary[
        (summary["algorithm"] == "aco") & (summary["connectivity"] == 4)
    ].iloc[0]
    eight_way = summary[
        (summary["algorithm"] == "aco") & (summary["connectivity"] == 8)
    ].iloc[0]
    same_point = summary[summary["algorithm"] == "ga"].iloc[0]
    assert four_way["normalized_path_cost_mean"] == 1.5
    assert eight_way["normalized_path_cost_mean"] is None
    assert same_point["normalized_path_cost_mean"] == 1.0


def test_same_named_distinct_map_paths_never_merge_or_share_an_optimum() -> None:
    rows = [
        _row(
            "dijkstra",
            map_name="duplicate-name",
            map_path="maps/a.json",
            path_length=4.0,
        ),
        _row(
            "aco",
            seed=11,
            map_name="duplicate-name",
            map_path="maps/a.json",
            path_length=6.0,
        ),
        _row(
            "aco",
            seed=29,
            map_name="duplicate-name",
            map_path="maps/b.json",
            path_length=6.0,
        ),
    ]

    summary = summarize_runs(pd.DataFrame(rows))

    aco = summary[summary["algorithm"] == "aco"]
    assert len(aco) == 2
    by_path = {row["map_path"]: row for row in aco.to_dict(orient="records")}
    assert by_path["maps/a.json"]["run_count"] == 1
    assert by_path["maps/a.json"]["normalized_path_cost_mean"] == 1.5
    assert by_path["maps/b.json"]["run_count"] == 1
    assert by_path["maps/b.json"]["normalized_path_cost_mean"] is None


@pytest.mark.parametrize(
    "path_json",
    ["not-json", "[0, 1]", "[[0, 0], [true, 1]]", "[[0, 0, 1]]"],
)
def test_invalid_path_json_or_schema_propagates(path_json: str) -> None:
    row = _row("aco", seed=11)
    row["path_json"] = path_json

    with pytest.raises(ValueError):
        summarize_runs(pd.DataFrame([row]))


def test_best_worst_runs_is_stable_and_keeps_empty_stochastic_cohorts() -> None:
    rows = [
        _row("dijkstra", path_length=5.0),
        _row(
            "aco",
            seed=11,
            path=((0, 0), (0, 1), (1, 1)),
            path_length=5.0,
        ),
        _row(
            "aco",
            seed=29,
            path=((0, 0), (0, 1), (0, 2)),
            path_length=5.0,
        ),
        _row("aco", seed=47, path_length=7.0),
        _row(
            "aco",
            seed=53,
            status="failed",
            success=False,
            error="failed",
            path_length=100.0,
        ),
        _row(
            "ga",
            seed=11,
            status="failed",
            success=False,
            error="failed",
            path=None,
            path_length=None,
        ),
    ]
    frame = pd.DataFrame(rows)

    report = best_worst_runs(frame)

    assert report == best_worst_runs(frame.iloc[::-1].reset_index(drop=True))
    assert report["ordering"] == {
        "best": ["path_length asc", "turning_count asc", "seed asc"],
        "worst": ["path_length desc", "turning_count desc", "seed asc"],
    }
    assert len(report["cohorts"]) == 2
    aco = next(item for item in report["cohorts"] if item["algorithm"] == "aco")
    assert aco["best"] == {
        "seed": 29,
        "path_length": 5.0,
        "normalized_path_cost": 1.0,
        "turning_count": 0,
    }
    assert aco["worst"] == {
        "seed": 47,
        "path_length": 7.0,
        "normalized_path_cost": 1.4,
        "turning_count": 0,
    }
    ga = next(item for item in report["cohorts"] if item["algorithm"] == "ga")
    assert ga["best"] is None
    assert ga["worst"] is None
    json.dumps(report, allow_nan=False)
