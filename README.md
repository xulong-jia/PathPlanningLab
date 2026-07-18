# PathPlanningLab

A reproducible four-algorithm grid path planning project implementing Dijkstra, A*, Ant Colony Optimization, and Genetic Algorithm.

## Current Status

Stage 2 is complete. The shared Stage 1 model remains verified, and the Dijkstra
and A* planners now pass deterministic optimality, path-validity, corner-rule,
and no-path regression matrices. Stage 3 has not been started.

## Repository Status

- Local Git repository initialized.
- GitHub remote `origin` connected at `git@github.com:xulong-jia/PathPlanningLab.git`.
- Local `main` tracks `origin/main`.
- Implementation tasks completed: 12 / 42 (28.57%); Stage 2 verified.

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
