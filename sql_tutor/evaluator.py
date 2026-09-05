from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from .database import validate_constraints
from .models import EvaluationResult, ExerciseContract, ExecutionResult, RubricAssessment


def _normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return ("decimal", str(value))
    return value


def compare_rows(actual: list[list[Any]], expected: list[list[Any]], order_sensitive: bool) -> bool:
    left = [[_normalize(v) for v in row] for row in actual]
    right = [[_normalize(v) for v in row] for row in expected]
    return left == right if order_sensitive else Counter(map(tuple, left)) == Counter(map(tuple, right))


def _typed(rows: list[list[Any]], contract: ExerciseContract) -> list[list[Any]]:
    typed = []
    for row in rows:
        converted = []
        for value, column in zip(row, contract.validation.output_columns):
            converted.append(Decimal(value) if value is not None and column.type in {"numeric", "bigint", "integer"} and isinstance(value, str) else value)
        typed.append(converted)
    return typed


def evaluate_sql(contract: ExerciseContract, visible: ExecutionResult, hidden: ExecutionResult) -> EvaluationResult:
    for result in (visible, hidden):
        if result.status == "error" and result.failure_kind in {"environment_error", "tool_error", "timeout", "permission_error"}:
            return EvaluationResult(decision="inconclusive", score=None, execution_status=result.failure_kind, issues=["The execution environment did not provide complete assessment evidence."])
        if result.status == "error":
            return EvaluationResult(decision="learner_sql_error", score=None, execution_status="error", issues=[result.safe_error or "The submitted SQL could not be executed."])
    if visible.status in {"blocked", "inconclusive"} or hidden.status in {"blocked", "inconclusive"}:
        return EvaluationResult(decision="blocked" if "blocked" in {visible.status, hidden.status} else "inconclusive", score=None, execution_status=visible.status, issues=[visible.safe_error or hidden.safe_error or "Execution did not produce complete evidence."])
    if not visible.complete or not hidden.complete:
        return EvaluationResult(decision="inconclusive", score=None, execution_status="inconclusive", issues=["The result limit prevented complete assessment evidence."])
    expected_v = contract.private.expected_visible_rows or []
    expected_h = contract.private.expected_hidden_rows or []
    valid_v = visible.complete and compare_rows(visible.preview_rows, _typed(expected_v, contract), contract.validation.order_sensitive)
    valid_h = hidden.complete and compare_rows(hidden.preview_rows, _typed(expected_h, contract), contract.validation.order_sensitive)
    constraints = validate_constraints(visible.executed_sql or visible.submitted_sql, contract)
    if not valid_v or not valid_h or "fail" in constraints.values():
        return EvaluationResult(decision="incorrect", score=0, execution_status="ok", dataset_results={"visible": "pass" if valid_v else "fail", "hidden": "pass" if valid_h else "fail"}, constraint_results=constraints, issues=["The result or a declared structural requirement was not satisfied."], primary_skill_affected=True)
    return EvaluationResult(decision="correct", score=1, execution_status="ok", dataset_results={"visible": "pass", "hidden": "pass"}, constraint_results=constraints, primary_skill_affected=True)


def evaluate_rubric(contract: ExerciseContract, rubric: RubricAssessment, *, execution_status: str = "not_required", response_text: str | None = None) -> EvaluationResult:
    expected = {item.id for item in (contract.validation.rubric or contract.validation.reasoning_rubric)}
    received = {item.id for item in rubric.criteria}
    if expected != received or len(rubric.criteria) != len(received):
        return EvaluationResult(decision="pending_review", score=None, execution_status=execution_status, issues=["The rubric response did not cover exactly the declared criteria."])
    if response_text is not None and any(item.evidence_quote and item.evidence_quote not in response_text for item in rubric.criteria):
        return EvaluationResult(decision="pending_review", score=None, execution_status=execution_status, issues=["A rubric evidence quote was not found in the submitted response."])
    declared = {item.id: item.required for item in (contract.validation.rubric or contract.validation.reasoning_rubric)}
    required = [item for item in rubric.criteria if declared[item.id]]
    if any(item.result == "not_assessable" for item in required):
        return EvaluationResult(decision="pending_review", score=None, execution_status=execution_status, issues=["A required criterion lacks sufficient evidence."])
    if any(item.result == "not_met" for item in required):
        return EvaluationResult(decision="incorrect", score=0, execution_status=execution_status, issues=[item.explanation for item in required if item.result == "not_met"], primary_skill_affected=rubric.primary_skill_affected)
    if any(item.result == "partial" for item in required):
        return EvaluationResult(decision="partial", score=0.5, execution_status=execution_status, issues=[item.explanation for item in required if item.result == "partial"], primary_skill_affected=rubric.primary_skill_affected)
    return EvaluationResult(decision="correct", score=1, execution_status=execution_status, primary_skill_affected=rubric.primary_skill_affected)


def evaluate_explanation(contract: ExerciseContract, text: str, rubric: RubricAssessment | None = None) -> EvaluationResult:
    if not text.strip():
        return EvaluationResult(decision="incorrect", score=0, execution_status="not_required", issues=["No explanation was submitted."])
    if rubric is None:
        return EvaluationResult(decision="pending_review", score=None, execution_status="not_required", issues=["Explanation requires a valid rubric review."])
    return evaluate_rubric(contract, rubric, response_text=text)


def evaluate_plan(contract: ExerciseContract, plan: ExecutionResult, rubric: RubricAssessment | None = None) -> EvaluationResult:
    if plan.status != "ok" or plan.plan_json is None:
        return EvaluationResult(decision="inconclusive", score=None, execution_status=plan.status, issues=[plan.safe_error or "A real execution plan was not available."])
    if rubric is None:
        return EvaluationResult(decision="pending_review", score=None, execution_status="ok", issues=["Plan analysis requires a valid rubric review."])
    return evaluate_rubric(contract, rubric, execution_status="ok")
