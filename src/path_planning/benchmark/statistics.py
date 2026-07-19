"""Transparent benchmark summaries with sample standard deviation (ddof=1)."""

import json
import math
from collections.abc import Iterable
from numbers import Real
from typing import cast

import pandas as pd  # type: ignore[import-untyped]

from path_planning.core.metrics import normalized_path_cost
from path_planning.core.types import JsonValue, Point, validated_json_value

_TASK_COLUMNS = (
    "map_name",
    "map_path",
    "start_row",
    "start_column",
    "goal_row",
    "goal_column",
    "connectivity",
    "diagonal_cost",
    "allow_corner_cutting",
)
_GROUP_COLUMNS = ("algorithm", "config_name", *_TASK_COLUMNS)
_METRIC_COLUMNS = (
    "path_length",
    "normalized_path_cost",
    "runtime_ms",
    "wall_runtime_ms",
    "expanded_nodes",
    "evaluations",
    "iterations",
    "turning_count",
)
_STATISTICS = ("mean", "std", "min", "max", "median")
_REQUIRED_COLUMNS = {
    *_GROUP_COLUMNS,
    "seed",
    "status",
    "error",
    "success",
    "path_json",
    "path_length",
    "runtime_ms",
    "wall_runtime_ms",
    "expanded_nodes",
    "evaluations",
    "iterations",
}


def summarize_runs(runs: pd.DataFrame) -> pd.DataFrame:
    """Summarize every run by algorithm, config, and exact task identity.

    The denominator is the minimum usable successful Dijkstra cost for the
    exact task. Metric standard deviations are sample standard deviations;
    singleton samples therefore have a null standard deviation.
    """
    records = _prepared_records(runs)
    groups = _groups(records)
    rows: list[dict[str, object]] = []
    for identity in _sorted_identities(groups):
        cohort = groups[identity]
        successful = [row for row in cohort if row["_retained_success"]]
        summary = dict(zip(_GROUP_COLUMNS, identity, strict=True))
        summary.update(
            {
                "run_count": len(cohort),
                "success_count": len(successful),
                "success_rate": len(successful) / len(cohort),
            }
        )
        for metric in _METRIC_COLUMNS:
            values = _metric_values(successful, metric)
            summary.update(
                {
                    f"{metric}_{statistic}": value
                    for statistic, value in _summary_statistics(values).items()
                }
            )
        rows.append(summary)

    columns = [
        *_GROUP_COLUMNS,
        "run_count",
        "success_count",
        "success_rate",
        *(
            f"{metric}_{statistic}"
            for metric in _METRIC_COLUMNS
            for statistic in _STATISTICS
        ),
    ]
    summary_frame = pd.DataFrame(rows, columns=columns).astype(object)
    return summary_frame.where(pd.notna(summary_frame), None)


def best_worst_runs(runs: pd.DataFrame) -> dict[str, JsonValue]:
    """Return deterministic path-quality extrema for each seeded cohort."""
    records = _prepared_records(runs)
    groups = _groups(records)
    cohorts: list[dict[str, object]] = []
    for identity in _sorted_identities(groups):
        cohort = groups[identity]
        if not any(row["seed"] is not None for row in cohort):
            continue
        eligible = [
            row
            for row in cohort
            if row["_retained_success"]
            and row["seed"] is not None
            and row["path_length"] is not None
        ]
        entry = dict(zip(_GROUP_COLUMNS, identity, strict=True))
        if eligible:
            best = min(eligible, key=_best_key)
            worst = min(eligible, key=_worst_key)
            entry.update({"best": _extreme(best), "worst": _extreme(worst)})
        else:
            entry.update({"best": None, "worst": None})
        cohorts.append(entry)

    report: dict[str, object] = {
        "ordering": {
            "best": ["path_length asc", "turning_count asc", "seed asc"],
            "worst": ["path_length desc", "turning_count desc", "seed asc"],
        },
        "cohorts": cohorts,
    }
    return cast(dict[str, JsonValue], validated_json_value(report))


def _prepared_records(runs: pd.DataFrame) -> list[dict[str, object]]:
    missing = sorted(_REQUIRED_COLUMNS - set(runs.columns))
    if missing:
        raise ValueError(f"missing benchmark columns: {', '.join(missing)}")
    records = cast(list[dict[str, object]], runs.to_dict(orient="records"))
    for row in records:
        for name, value in tuple(row.items()):
            row[name] = _none_if_missing(value)
        path_json = row["path_json"]
        turns: int | None = None
        if path_json is not None:
            if not isinstance(path_json, str):
                raise ValueError("path_json must be a JSON string or null")
            turns = _turning_count(_parse_path(path_json))
        retained = _is_retained_success(row)
        if retained and turns is None:
            raise ValueError("successful benchmark rows require path_json")
        row["_retained_success"] = retained
        row["turning_count"] = turns if retained else None

    optima: dict[tuple[object, ...], float] = {}
    for row in records:
        if row["algorithm"] != "dijkstra" or not row["_retained_success"]:
            continue
        cost = _number(row["path_length"], "path_length")
        if cost is None or not _usable_optimum(row, cost):
            continue
        task = _identity(row, _TASK_COLUMNS)
        optima[task] = min(cost, optima.get(task, cost))

    for row in records:
        candidate = (
            _number(row["path_length"], "path_length")
            if row["_retained_success"]
            else None
        )
        row["normalized_path_cost"] = normalized_path_cost(
            candidate,
            optima.get(_identity(row, _TASK_COLUMNS)),
        )
    return records


def _groups(
    records: Iterable[dict[str, object]],
) -> dict[tuple[object, ...], list[dict[str, object]]]:
    groups: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for row in records:
        groups.setdefault(_identity(row, _GROUP_COLUMNS), []).append(row)
    return groups


def _sorted_identities(
    groups: dict[tuple[object, ...], list[dict[str, object]]],
) -> list[tuple[object, ...]]:
    return sorted(
        groups,
        key=lambda identity: json.dumps(
            identity,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )


def _identity(row: dict[str, object], columns: Iterable[str]) -> tuple[object, ...]:
    return tuple(row[column] for column in columns)


def _is_retained_success(row: dict[str, object]) -> bool:
    return (
        row["status"] == "success" and row["error"] is None and row["success"] is True
    )


def _usable_optimum(row: dict[str, object], cost: float) -> bool:
    if cost > 0.0:
        return True
    return (row["start_row"], row["start_column"]) == (
        row["goal_row"],
        row["goal_column"],
    )


def _metric_values(records: Iterable[dict[str, object]], metric: str) -> list[float]:
    values: list[float] = []
    for row in records:
        value = _number(row[metric], metric)
        if value is not None:
            values.append(value)
    return values


def _summary_statistics(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {statistic: None for statistic in _STATISTICS}
    ordered = sorted(values)
    count = len(ordered)
    mean = math.fsum(ordered) / count
    middle = count // 2
    median = (
        ordered[middle] if count % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    standard_deviation = (
        math.sqrt(math.fsum((value - mean) ** 2 for value in ordered) / (count - 1))
        if count > 1
        else None
    )
    return {
        "mean": mean,
        "std": standard_deviation,
        "min": ordered[0],
        "max": ordered[-1],
        "median": median,
    }


def _parse_path(path_json: str) -> tuple[Point, ...]:
    payload = json.loads(path_json)
    if not isinstance(payload, list):
        raise ValueError("path_json must contain a list")
    path: list[Point] = []
    for point in payload:
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int) for value in point
            )
        ):
            raise ValueError("path_json points must contain two integer coordinates")
        path.append((point[0], point[1]))
    return tuple(path)


def _turning_count(path: tuple[Point, ...]) -> int:
    directions = [
        (following[0] - current[0], following[1] - current[1])
        for current, following in zip(path, path[1:], strict=False)
        if following != current
    ]
    return sum(
        first != second
        for first, second in zip(directions, directions[1:], strict=False)
    )


def _best_key(row: dict[str, object]) -> tuple[float, float, int]:
    return (
        _required_number(row["path_length"], "path_length"),
        _required_number(row["turning_count"], "turning_count"),
        _seed(row["seed"]),
    )


def _worst_key(row: dict[str, object]) -> tuple[float, float, int]:
    path_length, turns, seed = _best_key(row)
    return (-path_length, -turns, seed)


def _extreme(row: dict[str, object]) -> dict[str, object]:
    return {
        "seed": _seed(row["seed"]),
        "path_length": _required_number(row["path_length"], "path_length"),
        "normalized_path_cost": row["normalized_path_cost"],
        "turning_count": int(_required_number(row["turning_count"], "turning_count")),
    }


def _seed(value: object) -> int:
    number = _number(value, "seed")
    if number is None or not number.is_integer():
        raise ValueError("seed must be a non-negative integer")
    return int(number)


def _required_number(value: object, field: str) -> float:
    number = _number(value, field)
    if number is None:
        raise ValueError(f"{field} must not be null")
    return number


def _number(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field} must be numeric or null")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{field} must be finite and non-negative")
    return number


def _none_if_missing(value: object) -> object:
    missing = pd.isna(value)
    if isinstance(missing, bool) and missing:
        return None
    return value
