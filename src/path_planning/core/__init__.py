"""Core grid, movement, result, validation, and metric models."""

from path_planning.core.grid import GridMap
from path_planning.core.metrics import normalized_path_cost, path_length, turning_count
from path_planning.core.movement import MovementConfig, iter_neighbors
from path_planning.core.result import PlanningResult
from path_planning.core.types import JsonValue, Point, validated_json_value
from path_planning.core.validation import (
    PathValidation,
    is_reachable,
    validate_endpoints,
    validate_path,
)

__all__ = [
    "GridMap",
    "JsonValue",
    "MovementConfig",
    "PathValidation",
    "PlanningResult",
    "Point",
    "is_reachable",
    "iter_neighbors",
    "normalized_path_cost",
    "path_length",
    "turning_count",
    "validate_endpoints",
    "validated_json_value",
    "validate_path",
]
