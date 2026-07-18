# PathPlanningLab

A reproducible four-algorithm grid path planning project implementing Dijkstra, A*, Ant Colony Optimization, and Genetic Algorithm.

## Current Status

Stage 3 is complete. The shared Stage 1 model and Stage 2 deterministic planners
remain verified. Dijkstra and A* pass optimality regressions; the grid-based ACO
planner now passes construction, pheromone-learning, path-validity, seed,
corner-rule, convergence, budget, and no-path matrices. Stage 4 has not started.

## Repository Status

- Local Git repository initialized.
- GitHub remote `origin` connected at `git@github.com:xulong-jia/PathPlanningLab.git`.
- Local `main` tracks `origin/main`.
- Implementation tasks completed: 16 / 42 (38.10%); Stage 3 verified.

## Development Setup

Requires Python 3.11 or newer. Create the project-local environment and install
the declared development dependencies:

```bash
/opt/homebrew/bin/python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Run the current checks with:

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src
```

## Documentation

- [Implementation Plan](docs/superpowers/plans/2026-07-18-path-planning-lab.md)
- [Stage 1 Architecture](docs/architecture.md)
- [Deterministic Algorithms](docs/algorithms.md)
- [Project Status](docs/progress/PROJECT_STATUS.md)
- [Work Log](docs/progress/WORK_LOG.md)
- [Current Handoff](docs/progress/HANDOFF.md)

## Important

The historical materials under `/Users/jiaxulong/Desktop/论文与实习` are read-only references and are not modified by this project.
