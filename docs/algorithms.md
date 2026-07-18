# Path-planning algorithms

## Deterministic planner scope

Stage 2 implements the deterministic Dijkstra and A* planners. Both consume the
shared `GridMap` and `MovementConfig`, expand neighbors only through
`iter_neighbors()`, validate endpoints and reconstructed paths with the shared
core validators, and return the stable `PlanningResult` schema. Stage 3 adds the
ACO planner documented below; later-stage algorithms remain unimplemented.

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

## Ant Colony Optimization

`AntColonyPlanner` stores pheromone on directed grid edges in a
`rows × columns × movement_count` NumPy tensor. The last dimension follows the
shared movement order and therefore has four entries for 4-way movement and
eight for 8-way movement. Construction only consumes neighbors returned by
`iter_neighbors()`, so obstacle, diagonal-cost, and corner-cutting rules remain
shared with the deterministic planners.

For a legal candidate neighbor `j`, the sampling weight is

```text
tau(i, j) ** alpha * (1 / (euclidean_distance(j, goal) + epsilon)) ** beta
```

Each ant owns a visited set, so its returned path contains no repeated cells.
A dead end triggers bounded stack backtracking; an exhausted attempt may restart
from the start. `max_steps`, `max_backtracks`, and `max_restarts` bound all such
work. A shared reachability precheck runs before any ant and returns
`failure_reason="no_path_precheck"` with zero evaluations when no legal route
exists. The precheck is never used to construct or repair an ACO path.

All ants in a round see the same pheromone tensor. After every ant finishes, the
round update is strictly:

```text
tau = (1 - evaporation_rate) * tau
for each successful path:
    add pheromone_deposit / path_length to every forward and reverse edge
add elite_weight * pheromone_deposit / global_best_length to global-best edges
tau = clip(tau, min_pheromone, max_pheromone)
```

The planner retains the best validated path found across rounds. Its
`convergence_history` is the best-so-far cost after each completed round and is
`null` until a successful construction exists. A strict improvement resets the
stagnation counter; `stagnation_iterations` consecutive non-improving rounds
terminate the run early.

### ACO result and reproducibility semantics

- `evaluations` equals the number of attempted ant constructions.
- `iterations` is the number of completed rounds and matches convergence-history
  length.
- `expanded_nodes` is `null`; ACO work is not presented as deterministic node
  expansion.
- Metadata records constructed/successful paths, forward construction steps,
  backtracks, restarts, movement, every scalar ACO parameter, and a SHA-256
  sampling-trajectory digest.
- All sampling uses a local `numpy.random.Generator(seed)`. Equal seeds reproduce
  every non-time result field; `runtime_ms` is intentionally excluded.
- Every successful candidate and the returned global best pass the shared
  `validate_path()` contract.

## Configuration

`configs/dijkstra.yaml`, `configs/astar.yaml`, and `configs/aco_baseline.yaml`
record auditable defaults. The A* configuration additionally records the
Manhattan heuristic; the ACO configuration records every construction,
pheromone, iteration, and stagnation budget. Configuration parsing through the
public CLI is assigned to a later stage, so these stages verify typed planner
configurations directly.

## Verified boundaries and limitations

The deterministic matrix covers all six handcrafted maps with 4-way and 8-way
movement, allowed and forbidden corner cutting, compatible A* heuristics,
custom diagonal costs, invalid endpoints, and explicit no-path scenarios. The
Stage 3 ACO matrix directly covers tensor shape, probability exponents, complete
bidirectional deposits, update order, every pheromone parameter, bounded dead
ends, complex maps, seed behavior, global-RNG isolation, budgets, convergence,
corner rules, and no-path prechecks.

Movement costs remain uniform cardinal/diagonal costs. Weighted terrain,
dynamic obstacles, incremental replanning, later-stage algorithms, benchmark
performance, tuned ACO parameters, and CLI configuration loading are not
implemented or claimed at the Stage 3 boundary.
