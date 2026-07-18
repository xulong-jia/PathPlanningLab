import json
import math

import pytest

from path_planning.core.result import PlanningResult


def successful_result(**overrides: object) -> PlanningResult:
    values: dict[str, object] = {
        "algorithm": "example",
        "success": True,
        "path": ((0, 0), (0, 1)),
        "path_length": 1.0,
        "runtime_ms": 0.5,
        "expanded_nodes": 2,
        "evaluations": None,
        "iterations": 1,
        "convergence_history": (1.0,),
        "seed": None,
        "failure_reason": None,
        "metadata": {"config": {"connectivity": 4}, "labels": ["test"]},
    }
    values.update(overrides)
    return PlanningResult(**values)  # type: ignore[arg-type]


def test_successful_result_preserves_distinct_work_metrics() -> None:
    result = successful_result()

    assert result.success
    assert result.expanded_nodes == 2
    assert result.evaluations is None


def test_failure_result_requires_reason_and_empty_path() -> None:
    result = PlanningResult(
        algorithm="example",
        success=False,
        path=(),
        path_length=None,
        runtime_ms=0.2,
        expanded_nodes=None,
        evaluations=3,
        iterations=1,
        convergence_history=(None,),
        seed=7,
        failure_reason="no_path",
        metadata={},
    )

    assert not result.success
    assert result.failure_reason == "no_path"


@pytest.mark.parametrize(
    "overrides",
    [
        {"path": ()},
        {"path_length": None},
        {"failure_reason": "unexpected"},
        {"runtime_ms": -1.0},
        {"expanded_nodes": -1},
        {"iterations": -1},
        {"convergence_history": (math.inf,)},
    ],
)
def test_result_rejects_invalid_success_state(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        successful_result(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"path": ((0, 0),)},
        {"path_length": 0.0},
        {"failure_reason": None},
    ],
)
def test_result_rejects_invalid_failure_state(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "algorithm": "example",
        "success": False,
        "path": (),
        "path_length": None,
        "runtime_ms": 0.2,
        "expanded_nodes": None,
        "evaluations": None,
        "iterations": 0,
        "convergence_history": (),
        "seed": None,
        "failure_reason": "no_path",
        "metadata": {},
    }
    values.update(overrides)

    with pytest.raises(ValueError):
        PlanningResult(**values)  # type: ignore[arg-type]


def test_result_serializes_tuples_and_nested_metadata_to_standard_json() -> None:
    result = successful_result()

    payload = result.to_dict()

    assert payload["path"] == [[0, 0], [0, 1]]
    assert payload["convergence_history"] == [1.0]
    assert json.loads(result.to_json()) == payload


@pytest.mark.parametrize(
    "metadata",
    [{"bad": object()}, {"bad": math.nan}, {1: "non-string key"}],
)
def test_result_rejects_non_json_metadata(metadata: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        successful_result(metadata=metadata)


@pytest.mark.parametrize(
    "overrides",
    [
        {"algorithm": " "},
        {"metadata": []},
        {"path_length": -1.0},
        {"path_length": math.inf},
        {"path": [[0, 0], [0, 1]]},
        {"path": ((0, 0), (False, 1))},
        {"convergence_history": [1.0]},
    ],
)
def test_result_rejects_invalid_field_shapes(overrides: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        successful_result(**overrides)
