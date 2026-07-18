# Path-planning algorithms

## Stage 2 scope

Stage 2 implements the deterministic Dijkstra and A* planners. Both consume the
shared `GridMap` and `MovementConfig`, expand neighbors only through
`iter_neighbors()`, validate endpoints and reconstructed paths with the shared
core validators, and return the stable `PlanningResult` schema. ACO and GA are
outside this stage and remain unimplemented.

## Shared deterministic result semantics

- `runtime_ms` measures the complete `plan()` call, including validation.
- `expanded_nodes` counts nodes when they are first removed from the frontier
  and closed.
- `evaluations` is `null`; it is reserved for stochastic objective evaluations.
- `iterations` is `0`, `convergence_history` is empty, and `seed` is `null`.
- Invalid endpoints use the stable core validation reason. An exhausted
  frontier returns `failure_reason="no_path"` with an empty path and null cost.
- Every successful reconstructed path is checked with `validate_path()` before
  its cost is returned.

The deterministic planners accept the protocol's optional `seed` argument for
interface compatibility but do not use randomness.

## Dijkstra

`DijkstraPlanner` uses a `heapq` frontier ordered by accumulated movement cost.
The search maintains a best-known `g_score`, a `closed` set, and `came_from`
predecessors:

```text
push (0, start)
while frontier is not empty:
    pop the lowest-cost node not already closed
    close it and stop if it is the goal
    for each shared legal neighbor:
        relax the edge and push an improved cost
reconstruct and validate the goal path, or return no_path
```

With `V` free cells and `E` legal movement edges, the binary-heap
implementation uses `O((V + E) log V)` time and `O(V)` memory. The goal is
accepted only when removed from the heap, so it is final under positive edge
costs.

## A*

`AStarPlanner` maintains separate `g`, `h`, and `f = g + h` values, plus its own
frontier, closed set, and relaxation loop. It shares only movement, path
reconstruction, and validation infrastructure with Dijkstra. Frontier entries
are ordered by `f`, then `h`, `g`, and coordinate for deterministic tie-breaking.

Let `dr` and `dc` be absolute row and column distances, `a=max(dr, dc)`,
`b=min(dr, dc)`, and `d` be the configured diagonal cost:

- Manhattan: `dr + dc`.
- Euclidean: `hypot(dr, dc)` for 4-way movement. For 8-way movement it is
  multiplied by `min(1, d / sqrt(2))`, keeping it a lower bound for custom
  diagonal costs.
- Octile: an obstacle-free 8-way lattice lower bound using the actual diagonal
  cost:
  - `a + b` when `d >= 2`;
  - `b*d + (a-b)` when `1 <= d < 2`;
  - `a*d` when `d < 1` and `a-b` is even;
  - `(a-1)*d + 1` when `d < 1` and `a-b` is odd.

### Heuristic compatibility

| Movement | Manhattan | Euclidean | Octile | Default |
|---|---:|---:|---:|---|
| 4-way | Allowed | Allowed | Rejected | Manhattan |
| 8-way | Rejected | Allowed | Allowed | Octile |

Incompatible or unknown heuristics raise `ValueError` during configuration;
they never run silently. For all allowed combinations, regression tests compare
A* cost with the Dijkstra optimum. Equivalent shortest paths may use different
coordinate sequences, so equality is asserted on validated movement cost.

A* has the same `O((V + E) log V)` worst-case time and `O(V)` memory bounds as
Dijkstra. An admissible heuristic can change the number of expanded nodes, but
Stage 2 does not make a measured runtime or expansion-reduction claim.

## Configuration

`configs/dijkstra.yaml` and `configs/astar.yaml` record the default 4-way,
no-corner-cutting movement rules. The A* configuration additionally records the
Manhattan heuristic. Configuration parsing through the public CLI is assigned
to a later stage; Stage 2 verifies the typed planner configurations directly.

## Verified boundaries and limitations

The Stage 2 matrix covers all six handcrafted maps with 4-way and 8-way
movement, allowed and forbidden corner cutting, compatible A* heuristics,
custom diagonal costs, invalid endpoints, and explicit no-path scenarios.
Movement costs are uniform cardinal/diagonal costs; weighted terrain, dynamic
obstacles, incremental replanning, ACO, GA, benchmark performance, and CLI
configuration loading are not implemented or claimed in Stage 2.
