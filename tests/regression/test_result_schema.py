import inspect
import json
import subprocess
import sys
from dataclasses import fields

from path_planning.algorithms.base import Planner
from path_planning.core.result import PlanningResult

EXPECTED_FIELDS = {
    "algorithm",
    "success",
    "path",
    "path_length",
    "runtime_ms",
    "expanded_nodes",
    "evaluations",
    "iterations",
    "convergence_history",
    "seed",
    "failure_reason",
    "metadata",
}


def test_result_schema_field_names_are_stable() -> None:
    assert {field.name for field in fields(PlanningResult)} == EXPECTED_FIELDS


def test_failure_schema_preserves_null_work_metrics() -> None:
    result = PlanningResult(
        algorithm="example",
        success=False,
        path=(),
        path_length=None,
        runtime_ms=0.1,
        expanded_nodes=None,
        evaluations=None,
        iterations=0,
        convergence_history=(),
        seed=None,
        failure_reason="no_path",
        metadata={},
    )

    payload = json.loads(result.to_json())

    assert payload["expanded_nodes"] is None
    assert payload["evaluations"] is None


def test_planner_protocol_has_the_unified_plan_signature() -> None:
    parameters = list(inspect.signature(Planner.plan).parameters)

    assert parameters == ["self", "grid", "start", "goal", "config", "seed"]


def test_result_and_protocol_import_without_output() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import path_planning.core.result; import path_planning.algorithms.base",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
