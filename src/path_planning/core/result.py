import json
import math
from dataclasses import dataclass

from path_planning.core.types import JsonValue, Point, validated_json_value


@dataclass(frozen=True, slots=True)
class PlanningResult:
    algorithm: str
    success: bool
    path: tuple[Point, ...]
    path_length: float | None
    runtime_ms: float
    expanded_nodes: int | None
    evaluations: int | None
    iterations: int
    convergence_history: tuple[float | None, ...]
    seed: int | None
    failure_reason: str | None
    metadata: dict[str, JsonValue]

    def __post_init__(self) -> None:
        if not self.algorithm.strip():
            raise ValueError("algorithm must not be empty")
        if not math.isfinite(self.runtime_ms) or self.runtime_ms < 0:
            raise ValueError("runtime_ms must be finite and non-negative")
        self._validate_count("expanded_nodes", self.expanded_nodes)
        self._validate_count("evaluations", self.evaluations)
        self._validate_count("iterations", self.iterations)
        self._validate_path()
        self._validate_convergence()

        metadata = validated_json_value(self.metadata)
        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a JSON object")
        object.__setattr__(self, "metadata", metadata)

        if self.success:
            if not self.path or self.path_length is None:
                raise ValueError("successful results require a path and path_length")
            if self.failure_reason is not None:
                raise ValueError("successful results cannot have a failure_reason")
        else:
            if self.path or self.path_length is not None:
                raise ValueError(
                    "failed results require an empty path and null path_length"
                )
            if not self.failure_reason:
                raise ValueError("failed results require a failure_reason")

        if self.path_length is not None and (
            not math.isfinite(self.path_length) or self.path_length < 0
        ):
            raise ValueError("path_length must be finite and non-negative")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "algorithm": self.algorithm,
            "success": self.success,
            "path": [[row, column] for row, column in self.path],
            "path_length": self.path_length,
            "runtime_ms": self.runtime_ms,
            "expanded_nodes": self.expanded_nodes,
            "evaluations": self.evaluations,
            "iterations": self.iterations,
            "convergence_history": list(self.convergence_history),
            "seed": self.seed,
            "failure_reason": self.failure_reason,
            "metadata": validated_json_value(self.metadata),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def _validate_count(name: str, value: int | None) -> None:
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ValueError(f"{name} must be a non-negative integer or null")

    def _validate_path(self) -> None:
        if not isinstance(self.path, tuple):
            raise TypeError("path must be a tuple")
        for point in self.path:
            if (
                not isinstance(point, tuple)
                or len(point) != 2
                or any(
                    isinstance(value, bool) or not isinstance(value, int)
                    for value in point
                )
            ):
                raise TypeError("path must contain integer coordinate tuples")

    def _validate_convergence(self) -> None:
        if not isinstance(self.convergence_history, tuple):
            raise TypeError("convergence_history must be a tuple")
        if any(
            value is not None and not math.isfinite(value)
            for value in self.convergence_history
        ):
            raise ValueError("convergence history values must be finite or null")
