# Benchmark methodology

## Scope and execution model

Stage 5 provides a serial, reproducible benchmark pipeline for Dijkstra, A*,
ACO, and GA on the shared grid model. Every algorithm in an exact task receives
the same loaded `GridMap`, start, goal, and `MovementConfig`; successful paths
are checked again by the shared validator. A successful planner result is only
retained as successful when its reported seed exactly matches the requested
seed (including `None`) and its reported path length matches the validator's
recomputed length under explicit `rel_tol=1e-12` and `abs_tol=1e-12`. The runner
does not use parallel workers. It refuses an output directory that already
exists, before reading the benchmark configuration or invoking a planner, so an
experiment cannot be silently overwritten or resumed.

The configuration identities are:

| Algorithm | Smoke | Standard |
|---|---|---|
| Dijkstra | `configs/dijkstra.yaml` | `configs/dijkstra.yaml` |
| A* | `configs/astar_benchmark.yaml` (`auto`, resolved per movement) | `configs/astar_benchmark.yaml` (`auto`, resolved per movement) |
| ACO | `configs/aco_smoke.yaml` | `configs/aco_baseline.yaml` |
| GA | `configs/ga_smoke.yaml` | `configs/ga_baseline.yaml` |

The Smoke-specific ACO and GA files preserve every non-budget baseline value
but reduce only explicit execution budgets. ACO uses 8 ants, 12 iterations,
3,000 maximum steps, one restart, 100 backtracks, and five stagnation
iterations, instead of 32/50/10,000/2/200/10. GA uses population 24, 25
generations, 10,000 initialization steps, five initialization attempts, and
eight stagnation generations, instead of 80/100/50,000/10/20. These are
runtime-bounded executions of the real algorithms, not tuned configurations or
algorithm substitutes. Standard retains the baseline files. Parameter tuning
and tuning/evaluation isolation are future Stage 6 concerns and are not
implemented in Stage 5.

## Experiment designs

The Smoke design has three handcrafted 4-way tasks: `open_20`, `maze_30`, and
`no_path_20`. Corner cutting is disabled and the configured diagonal cost is
`sqrt(2)`, although diagonal movement is unavailable in these tasks.
Deterministic planners have no warm-up and one measured run per task. ACO and GA
each run once for seeds 11, 29, and 47. The formal raw-row count is therefore
`3 * (1 + 1 + 3 + 3) = 24`.

The Standard design has 21 exact tasks. Fifteen 4-way tasks cover all six
handcrafted maps and all nine generated evaluation maps. Six representative
8-way tasks cover handcrafted `maze_30`, `bottleneck_50`, and `no_path_20`, plus
the 20%-density generated evaluation map at each of 20x20, 50x50, and 100x100.
All tasks disable corner cutting and use a diagonal cost of `sqrt(2)`.
Deterministic planners perform three unrecorded warm-up calls followed by ten
recorded measurements. Each stochastic planner performs one recorded run for
each fixed seed from 101 through 120. Standard execution is not part of the
Stage 5 Smoke result.

Warm-up calls exercise the same planner and exact task but never enter raw or
summary results. Deterministic measured rows have a null seed. ACO and GA use
the explicit seed shown in each row; the runner performs no hidden retry or
best-seed filtering. A warm-up result must also preserve its requested null
seed; a protocol mismatch aborts before raw artifacts are written. An ordinary
unsuccessful warm-up remains unrecorded and does not abort later formal calls.

## Retention and metric semantics

Every formal measured call produces a raw row. Expected planner failures,
planner exceptions, path-validation failures, and slow or otherwise unusual
observations are retained; the runner does not remove failures or outliers.
`success_rate` uses every row in its exact algorithm/configuration/task cohort
as the denominator. Only rows whose retained status is formally successful
contribute numeric path, runtime, work, and turning-count samples. A failure is
never converted to numeric zero.

Work fields are intentionally separate:

- `expanded_nodes` is deterministic graph-search work for Dijkstra and A*.
- `evaluations` is stochastic objective/construction work for ACO and GA.
- `iterations` is completed ACO rounds or GA generations; deterministic
  planners report their established zero-iteration convention.

The pipeline does not combine these fields into a cross-algorithm work score.
`runtime_ms` is the planner-reported runtime, while `wall_runtime_ms` measures
the surrounding formal call.

Path cost is normalized only against a retained successful Dijkstra result for
the same repository-relative `map_path`, start, goal, connectivity, diagonal
cost, and corner-cutting rule. `map_name` remains a display label and is not a
substitute for `map_path`; same-named maps at different paths cannot merge or
share an optimum. If more than one such Dijkstra row exists, the minimum usable
cost is the denominator. A positive optimum uses the ordinary
candidate/optimum ratio. A zero optimum is valid only when start equals goal,
where a zero-cost successful candidate normalizes to 1.0. If no usable
exact-task Dijkstra optimum exists, normalized cost remains null.

For each metric family, summaries report mean, sample standard deviation
(`ddof=1`), minimum, maximum, and median. Empty samples are null and a singleton
sample has a null standard deviation; JSON outputs forbid NaN and Infinity.
Best/worst records are descriptive only. Within each seeded algorithm,
configuration, and exact-task cohort, they order retained successful runs by
path length, then turning count, with seed as the stable tie-break. They do not
select parameters, discard seeds, or imply statistical superiority.

## Traceability and artifacts

`raw_runs.csv` and `raw_runs.json` are generated from the same ordered 27-field
records and preserve the same null semantics, including both display
`map_name` and identity-bearing repository-relative `map_path`. `summary.csv`
and `summary.json` likewise share one ordered summary source.
`best_worst.json` retains seeded cohorts even when no successful candidate
exists.

`run_metadata.json` records a run UUID, UTC execution time, benchmark-config
SHA-256, current Git commit and dirty flag, Python/platform identity, direct
dependency versions, exact locked and installed dependency versions, lockfile
SHA-256, and a source snapshot. The snapshot stores repository-relative file
names and SHA-256 values for `src/path_planning/**/*.py`, `configs/**/*.yaml`,
`maps/**/*.json`, `pyproject.toml`, and `requirements.lock`; its aggregate is the
SHA-256 of the canonical sorted file-hash mapping. It includes uncommitted Stage
5 inputs, which is why the real Smoke correctly records `git_dirty: true`.

`manifest.json` is written last. It binds the run UUID and configuration hash
to the exact bytes and SHA-256 values of the six non-manifest artifacts. The
manifest does not self-hash. Artifacts and metadata use relative identities and
do not store local absolute paths.

## Observed Stage 5 Smoke

The current remediation-candidate Smoke was invoked once through the public Python API after the
pre-review run was rejected and moved intact to a recoverable temporary audit
location. It ran from 2026-07-19T01:45:17Z to 2026-07-19T01:45:52Z and exited
successfully after 35.735 seconds. The environment reported Python 3.12.2 on
`macOS-26.5.2-arm64-arm-64bit`. The result contains exactly 24 raw rows, 12
summary rows, and six stochastic best/worst cohorts. Each of the four
algorithms has all expected rows. All eight `no_path_20` rows are retained as
failures: Dijkstra and A* report `no_path`, while ACO and GA report their shared
precheck outcome `no_path_precheck` for all three seeds. The manifest verifies
all six payload artifacts. All 16 successful paths pass independent shared
validation and exact cost recomputation; all 24 formal rows preserve requested
versus result seed equality. The 56-file source snapshot aggregate is
`9e00d0fb3f89df84de65390834bea1e2343f56d547702c22ec09fbf56b6333b5`.

This Smoke demonstrates the minimum execution and persistence loop; it is not
a statistical comparison and supports no performance ranking. Runtime values
depend on hardware, OS scheduling, interpreter state, cache temperature, and
other process noise. Serial execution avoids concurrent planner contention but
does not remove those limitations. UTC timestamps describe provenance, not a
controlled performance laboratory.
