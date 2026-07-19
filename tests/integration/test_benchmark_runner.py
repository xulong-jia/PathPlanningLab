import json
from pathlib import Path

import pytest

from path_planning.benchmark.runner import run_benchmark


def _write_benchmark_fixture(
    root: Path,
    *,
    warmup_runs: int = 1,
    measurement_runs: int = 2,
    seeds: tuple[int, ...] = (5, 9),
    connectivity: int = 4,
) -> Path:
    configs = root / "configs"
    maps = root / "maps"
    configs.mkdir(parents=True)
    maps.mkdir()
    (maps / "same.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "same-map",
                "cells": [[0]],
                "start": [0, 0],
                "goal": [0, 0],
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )
    (configs / "dijkstra.yaml").write_text("movement: {}\n", encoding="utf-8")
    (configs / "astar_benchmark.yaml").write_text(
        "heuristic: auto\n",
        encoding="utf-8",
    )
    (configs / "aco.yaml").write_text(
        """movement: {}
ants: 1
alpha: 1.0
beta: 1.0
evaporation_rate: 0.25
pheromone_deposit: 1.0
elite_weight: 0.0
min_pheromone: 0.01
max_pheromone: 1.0
iterations: 1
max_steps: 1
max_restarts: 0
max_backtracks: 0
stagnation_iterations: 1
""",
        encoding="utf-8",
    )
    (configs / "ga.yaml").write_text(
        """movement: {}
population_size: 4
generations: 1
crossover_probability: 0.0
mutation_probability: 0.0
tournament_size: 2
elite_size: 1
max_initialization_steps: 1
initialization_attempts: 1
stagnation_generations: 1
path_length_penalty: 1.0
turn_penalty: 0.0
repeat_penalty: 0.0
unreachable_base_penalty: 1000.0
collision_penalty: 1.0
remaining_distance_penalty: 1.0
""",
        encoding="utf-8",
    )
    config_path = configs / "benchmark.yaml"
    seed_values = ", ".join(str(seed) for seed in seeds)
    config_path.write_text(
        f"""schema_version: 1
name: test
algorithm_configs:
  dijkstra: configs/dijkstra.yaml
  astar: configs/astar_benchmark.yaml
  aco: configs/aco.yaml
  ga: configs/ga.yaml
deterministic:
  warmup_runs: {warmup_runs}
  measurement_runs: {measurement_runs}
stochastic:
  seeds: [{seed_values}]
tasks:
  - map: maps/same.json
    movement:
      connectivity: {connectivity}
      diagonal_cost: 1.4142135623730951
      allow_corner_cutting: false
""",
        encoding="utf-8",
    )
    return config_path


def test_run_benchmark_records_exact_formal_run_count(tmp_path: Path) -> None:
    config_path = _write_benchmark_fixture(tmp_path)
    output_dir = tmp_path / "output"

    artifacts = run_benchmark(config_path, output_dir)

    rows = json.loads((output_dir / artifacts.records_json).read_text())
    assert len(rows) == 8
    assert [row["algorithm"] for row in rows].count("dijkstra") == 2
    assert [row["algorithm"] for row in rows].count("astar") == 2
    assert [row["algorithm"] for row in rows].count("aco") == 2
    assert [row["algorithm"] for row in rows].count("ga") == 2
    assert {row["map_path"] for row in rows} == {"maps/same.json"}
    assert {path.name for path in output_dir.iterdir()} == {
        "raw_runs.csv",
        "raw_runs.json",
        "run_metadata.json",
        "summary.csv",
        "summary.json",
        "best_worst.json",
        "manifest.json",
    }
    assert all(row["status"] == "success" for row in rows)
    assert artifacts.records_csv == Path("raw_runs.csv")
    assert artifacts.metadata_json == Path("run_metadata.json")
    assert artifacts.summary_csv == Path("summary.csv")
    assert artifacts.summary_json == Path("summary.json")
    assert artifacts.best_worst_json == Path("best_worst.json")
    assert artifacts.manifest_json == Path("manifest.json")
    summary = json.loads((output_dir / artifacts.summary_json).read_text())
    assert len(summary) == 4
    assert all(row["run_count"] == 2 for row in summary)
    assert all(row["success_rate"] == 1.0 for row in summary)
    extrema = json.loads((output_dir / artifacts.best_worst_json).read_text())
    assert {row["algorithm"] for row in extrema["cohorts"]} == {"aco", "ga"}
    astar_rows = [row for row in rows if row["algorithm"] == "astar"]
    assert {row["config_name"] for row in astar_rows} == {
        "configs/astar_benchmark.yaml"
    }
    resolved_heuristics = {
        json.loads(row["result_metadata_json"])["heuristic"] for row in astar_rows
    }
    assert resolved_heuristics == {"manhattan"}


def test_auto_astar_config_resolves_to_traceable_eight_way_default(
    tmp_path: Path,
) -> None:
    config_path = _write_benchmark_fixture(tmp_path, connectivity=8)
    output_dir = tmp_path / "output"

    artifacts = run_benchmark(config_path, output_dir)

    rows = json.loads((output_dir / artifacts.records_json).read_text())
    astar_rows = [row for row in rows if row["algorithm"] == "astar"]
    assert {row["config_name"] for row in astar_rows} == {
        "configs/astar_benchmark.yaml"
    }
    resolved_heuristics = {
        json.loads(row["result_metadata_json"])["heuristic"] for row in astar_rows
    }
    assert resolved_heuristics == {"octile"}


def test_explicit_incompatible_astar_heuristic_is_rejected(tmp_path: Path) -> None:
    config_path = _write_benchmark_fixture(tmp_path, connectivity=8)
    (tmp_path / "configs" / "astar_benchmark.yaml").write_text(
        "heuristic: manhattan\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    with pytest.raises(ValueError, match="Manhattan heuristic requires 4-way"):
        run_benchmark(config_path, output_dir)

    assert not output_dir.exists()


def test_run_benchmark_rejects_existing_output_before_loading_config(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "existing"
    output_dir.mkdir()

    with pytest.raises(FileExistsError, match="output directory already exists"):
        run_benchmark(tmp_path / "missing.yaml", output_dir)
