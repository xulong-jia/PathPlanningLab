# Path-planning algorithms

## Deterministic planner scope

Stage 2 implements the deterministic Dijkstra and A* planners. Both consume the
shared `GridMap` and `MovementConfig`, expand neighbors only through
`iter_neighbors()`, validate endpoints and reconstructed paths with the shared
core validators, and return the stable `PlanningResult` schema. Stage 3 adds ACO,
and Stage 4 adds the coordinate-path GA documented below. Benchmarking, tuning,
visualization, and CLI configuration loading remain later-stage work.

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

## Genetic Algorithm

`GeneticPlanner` uses DEAP's `Toolbox`, minimizing `Fitness`, and list-based
`Individual` types, while keeping the evolution loop and every random choice
under project control. Creator names are project-specific and are created only
when absent, so repeated imports do not redefine DEAP types. A chromosome is a
variable-length coordinate sequence `[start, ..., goal]`; every population path
that enters evolution is simple and legal under the shared movement rules.
The Toolbox registers `individual`, `evaluate`, `select`, `mate`, `mutate`, and
`elite` aliases. The evolution loop calls the last four aliases directly;
selection and genetic operators bind the same explicit local RNG rather than
DEAP's global-random helpers or a packaged DEAP evolution loop.

### Initialization and repair

Initialization uses bounded randomized depth-first search. Each individual gets
its own `random.Random` stream derived from the planner-local RNG. Neighbor order
is shuffled, visited coordinates are not revisited, and both
`max_initialization_steps` and `initialization_attempts` bound failure. Loop
erasure is applied defensively before accepting a path.

Repair first erases loops and finds the first illegal segment. It then attempts
one bounded randomized local DFS connection between that segment's endpoints,
erases any resulting loop, and validates the complete path. Repair failure
returns a bounded failure outcome; operator wrappers retain copies of the
parents. Initialization, repair, crossover, and mutation never call A*,
Dijkstra, or any other deterministic shortest-path fallback.

### Fitness and strict invalid-path dominance

For a legal simple path `p`, the minimized objective is

```text
path_length_penalty * movement_cost(p) + turn_penalty * turns(p)
```

An invalid or repeated path starts at `unreachable_base_penalty`, then adds the
same length and turn terms plus configured repeat, collision, and remaining-goal
distance penalties. All coefficients are finite and non-negative, except that
the base penalty must be positive.

Before evolution, `validate_for_grid()` computes a legal-path upper bound from
at most `free_cell_count - 1` edges, the maximum configured cardinal/diagonal
step cost, and at most one turn between consecutive edges. The maximum step
cost is accumulated edge by edge, matching fitness arithmetic at floating-point
boundaries. `unreachable_base_penalty` must be strictly greater than this bound;
because every additional invalid-path term is non-negative, every invalid
individual is strictly worse than every legal simple individual on that grid.

### Selection and genetic operators

- Tournament selection samples `tournament_size` candidates with the local RNG
  and copies the lowest-fitness candidate.
- Roulette selection converts finite minimization fitness values to stable,
  non-negative weights after scaling by the largest absolute value. Equal or
  zero-weight populations fall back to uniform local-RNG sampling.
- `common_node` crossover swaps suffixes at a shared internal coordinate and
  erases loops.
- `splice_repair` crossover chooses one cut in each parent, exchanges suffixes,
  and repairs both children with bounded randomized DFS.
- `reroute_segment` mutation replaces a selected internal segment with a bounded
  randomized DFS connection.
- `shortcut` mutation removes a detour when its endpoints are already one legal
  shared-grid move apart.

The best `elite_size` individuals are copied directly into the next generation.
For each non-elite parent pair, crossover is attempted exactly when the local
draw is below `crossover_probability`; each child considered for insertion gets
the analogous independent mutation decision. A zero rate records skips without
attempts, a rate of one records attempts but does not promise the chosen operator
can change the path, and failed attempts retain parent copies. Metadata keeps
skip, attempt, success, failure, and splice-repair success/failure counts
separate.

### Budgets, results, and reproducibility

The initial population is evaluated once, and every complete next-generation
population is evaluated once. Thus `evaluations` is the actual number of fitness
calls. `iterations` is the number of completed generations. Both
`best_fitness_history` in metadata and path-cost `convergence_history` are
best-so-far values with one entry per completed generation. A strict fitness
improvement resets stagnation; execution stops at `generations` or after
`stagnation_generations` consecutive non-improving generations. If both limits
are reached together, the metadata still reports the generation budget as
exhausted.

Metadata records movement, every GA configuration field, operator and repair
counts, both budgets and the stop reason, the fitness history, and a SHA-256
trajectory digest. The digest covers the actual initial population and each
recorded population, fitness vector, and cumulative operator-count snapshot; it
does not substitute the seed for executed trajectory data. All randomness comes
from a hierarchy of local `random.Random` instances. Equal seeds reproduce all
non-time result fields, while `runtime_ms` is intentionally excluded.

Grid-specific configuration validation runs before every public result path,
including endpoint failures, no-path prechecks, and `start == goal`. Endpoint
validation and the shared reachability precheck then run before random work.
They return stable endpoint reasons or `no_path_precheck` with zero evaluations
and generations. `start == goal` is an immediate zero-work success. Exhausting
the bounded initialization budget returns `initialization_failed`, preserves a
digest of any partial population actually created, and does not hide unrelated
runtime errors. The final selected path is revalidated with `validate_path()`;
an internal invalid selection is treated as an invariant error rather than a
successful result.

### GA complexity and limitations

Let `F` be the free-cell count, `P` the population size, `G` the executed
generation count, `B` the DFS step budget, and `L <= F` a simple chromosome
length. Initialization is bounded by `O(P * initialization_attempts * B)`.
Fitness evaluation is `O(L)`. Tournament selection costs `O(tournament_size)`
per draw; the current roulette implementation recomputes population weights per
draw and is therefore `O(P^2)` per generation. Common-node crossover is
`O(L^2)` in the worst case because candidate suffixes may each require loop
erasure; splice repair is bounded by `O(B)`, shortcut enumeration is `O(L^2)`,
and the reroute mutation's exhaustive candidate-pair search is bounded by
`O(L^2 * B)`. These are conservative implementation bounds, not measured
performance claims.

The live population uses `O(P * F)` path storage. Reproducibility metadata keeps
an initial and per-generation population snapshot for the trajectory digest, so
the current run can use `O(G * P * F)` additional memory. GA is not guaranteed
to find a path even when the precheck proves reachability, is not guaranteed to
find an optimal path, and currently supports only the shared uniform
cardinal/diagonal grid costs. Baseline parameters are not tuned at the Stage 4
boundary.

## Configuration

`configs/dijkstra.yaml`, `configs/astar.yaml`, `configs/aco_baseline.yaml`, and
`configs/ga_baseline.yaml` record auditable defaults. The A* configuration
additionally records the Manhattan heuristic; ACO records every construction,
pheromone, iteration, and stagnation budget; GA records movement, population,
selection, elite, operator, initialization, fitness, generation, and stagnation
settings. Configuration parsing through the public CLI is assigned to a later
stage, so Stages 2–4 verify typed planner configurations directly.

## Verified boundaries and limitations

The deterministic matrix covers all six handcrafted maps with 4-way and 8-way
movement, allowed and forbidden corner cutting, compatible A* heuristics,
custom diagonal costs, invalid endpoints, and explicit no-path scenarios. The
Stage 3 ACO matrix directly covers tensor shape, probability exponents, complete
bidirectional deposits, update order, every pheromone parameter, bounded dead
ends, complex maps, seed behavior, global-RNG isolation, budgets, convergence,
corner rules, and no-path prechecks.

The Stage 4 GA matrix covers creator reuse, legal randomized initialization,
strict fitness dominance, both selection methods, both crossovers, both
mutations, repair outcomes, elite/rate semantics, generation and stagnation
budgets, complex maps, corner rules, stable failures, configuration flow,
trajectory digests, seed behavior, global-RNG isolation, and final shared-path
validation.

Movement costs remain uniform cardinal/diagonal costs. Weighted terrain,
dynamic obstacles, incremental replanning, benchmark performance, tuned ACO/GA
parameters, visualization, and CLI configuration loading are not implemented or
claimed at the Stage 4 boundary.
