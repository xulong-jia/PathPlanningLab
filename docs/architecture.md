# Stage 1 Architecture

## Scope

Stage 1 establishes the shared grid, movement, result, validation, metric, and
map-data layers used by every planner. It intentionally contains no concrete
path-planning algorithm; Dijkstra begins in S2-T01.

## Dependency direction

Dependencies point inward toward stable shared types:

```text
algorithms/base.py ───────────────┐
                                  v
maps/generation.py -> maps/io.py -> core/grid.py -> core/types.py
maps/suites.py ─────┘                 ^     ^
                                      │     │
core/validation.py -> core/movement.py┘     │
core/metrics.py ────────────────────────────┘
core/result.py ─────────────────────> core/types.py
```

- `core` never imports `maps` or a concrete algorithm.
- `maps` may use `core` validation and types, but does not depend on planners.
- Concrete planners will implement the `Planner` protocol and return the shared
  `PlanningResult` without changing the core or map APIs.

## Core model

### Grid and movement

`GridMap` owns a copied, read-only, two-dimensional NumPy boolean array. `True`
means blocked and `False` means free. Coordinates are `(row, column)` integer
tuples. Empty, non-two-dimensional, non-numeric, or non-finite grids are
rejected.

`MovementConfig` supports 4-way or 8-way movement. Cardinal moves cost `1.0`;
diagonal moves use a finite positive configurable cost that defaults to
`sqrt(2)`. Diagonal corner cutting is disabled by default. `iter_neighbors()` is
the single source of movement and obstacle rules.

### Planner and result schema

`Planner` is a structural protocol with a `name` property and a `plan()` method
that receives a `GridMap`, start, goal, and optional seed, then returns a
`PlanningResult`.

`PlanningResult` has the following stable fields:

| Field | Type | Meaning |
|---|---|---|
| `algorithm` | `str` | Non-empty planner name |
| `success` | `bool` | Whether a legal path was found |
| `path` | `tuple[Point, ...]` | Ordered grid coordinates |
| `path_length` | `float \| None` | Unified movement cost |
| `runtime_ms` | `float` | Finite non-negative runtime |
| `expanded_nodes` | `int \| None` | Deterministic search work |
| `evaluations` | `int \| None` | Stochastic objective evaluations |
| `iterations` | `int` | Non-negative iteration count |
| `convergence_history` | `tuple[float \| None, ...]` | Per-iteration history |
| `seed` | `int \| None` | Explicit random seed when applicable |
| `failure_reason` | `str \| None` | Stable failure code |
| `metadata` | JSON object | Algorithm/configuration evidence |

A successful result requires a non-empty path and path length and forbids a
failure reason. A failed result requires an empty path, null path length, and a
non-empty failure reason. Serialization rejects non-standard JSON values and
converts tuples to JSON arrays.

### Validation and metrics

`validate_endpoints()`, `validate_path()`, and `is_reachable()` apply the same
grid and movement rules to every caller. Stable validation failures include
out-of-bounds or blocked endpoints, empty/wrong-endpoint paths, obstacle
collisions, out-of-bounds points, and invalid steps.

Shared metrics calculate path length, turning count, and normalized path cost.
Invalid inputs fail explicitly instead of being silently coerced.

## Map schema and collections

Map JSON uses `schema_version: 1` and exactly these top-level keys:
`schema_version`, `name`, `cells`, `start`, `goal`, and `metadata`. `cells` is a
two-dimensional JSON array using `0` for free and `1` for blocked; endpoints are
two-integer arrays. Names must be non-empty, endpoints must be valid free cells,
and metadata must be a standard-JSON object. Loading rejects unknown/missing
keys, unsupported versions, malformed coordinates, invalid numeric constants,
and invalid grid shapes or values.

The committed collections are:

- Six handcrafted maps under `maps/handcrafted`: open, narrow channel, maze,
  dead ends, bottleneck, and no-path scenarios.
- Nine evaluation maps under `maps/generated/evaluation`.
- Four tuning maps under `maps/generated/tuning`.

Generated maps use a local NumPy RNG with an explicit seed, an exact rounded
obstacle target, and an optional protected Manhattan corridor. Evaluation and
tuning seeds are fixed and disjoint. `configs/map_generation.yaml` is sufficient
to reproduce every generated map byte-for-byte.

## Exception semantics

- `TypeError` identifies a value of the wrong structural type.
- `ValueError` identifies a value with the correct broad type but invalid
  content, bounds, schema, invariant, or configuration.
- Expected planning failure is data (`success=False` plus `failure_reason`), not
  an exception.
- Filesystem and operating-system errors are not hidden; callers receive the
  original exception when a map cannot be read or written.

## Stage 1 verification boundary

Stage 1 verifies the complete `core` and `maps` test suites, branch coverage of
those packages at or above 90%, Ruff lint and format checks, strict mypy, wheel
build, generated-suite reconstruction, and the read-only legacy hash baseline.
Final project-wide independent verification remains assigned to Stage 8.
