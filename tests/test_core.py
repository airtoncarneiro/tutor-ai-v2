from sql_tutor.exercises import example_contract, explanation_contract, plan_contract, validate_contract
from sql_tutor.models import SkillState
from sql_tutor.policy import choose_policy


def test_example_contract_is_closed_and_valid():
    contract = example_contract()
    assert contract.schema_version == 2
    assert validate_contract(contract.model_dump()) == contract


def test_unknown_skill_diagnoses():
    decision = choose_policy(SkillState(skill_key="aggregation.grouping.group_by"))
    assert decision.rule == "D1"


def test_policy_prioritizes_low_confidence():
    decision = choose_policy(SkillState(skill_key="x", mastery_score=5, evidence_status="mastered", confidence="low"))
    assert decision.rule == "C"


def test_contract_rejects_unknown_fields():
    payload = example_contract().model_dump()
    payload["unexpected"] = True
    try:
        validate_contract(payload)
    except Exception:
        pass
    else:
        raise AssertionError("unknown contract fields must be rejected")


def test_row_comparison_preserves_duplicates():
    from sql_tutor.evaluator import compare_rows
    assert compare_rows([[1], [1]], [[1], [1]], False)
    assert not compare_rows([[1], [1]], [[1]], False)


def test_sql_allowlist_blocks_schema_and_dangerous_function():
    from sql_tutor.database import SQLBlocked, validate_sql
    contract = example_contract()
    for query in ("SELECT * FROM tutor_state.student_profiles", "SELECT pg_sleep(1)"):
        try:
            validate_sql(query, contract)
        except SQLBlocked:
            continue
        raise AssertionError("unsafe SQL must be blocked")


def test_policy_required_cases():
    cases = [
        (SkillState(skill_key="x", confidence="low", evidence_status="validated", mastery_score=2), "C"),
        (SkillState(skill_key="x", evidence_status="self_declared", mastery_score=4), "D1"),
        (SkillState(skill_key="x", evidence_status="observed", mastery_score=2), "D2.2"),
        (SkillState(skill_key="x", evidence_status="observed", mastery_score=3), "D2.1"),
        (SkillState(skill_key="x", evidence_status="validated", confidence="high", mastery_score=2), "E1"),
        (SkillState(skill_key="x", evidence_status="validated", confidence="high", mastery_score=3), "E2"),
        (SkillState(skill_key="x", evidence_status="validated", confidence="high", mastery_score=4), "E3"),
    ]
    for state, expected in cases:
        assert choose_policy(state).rule == expected


def test_protocol_echoes_request_identity():
    from sql_tutor.protocol import make_request, validate_response
    request = make_request("chat", {"student_input": {"chat_message": "hello"}})
    payload = {"message": "Keep working on the exercise.", "pedagogical_move": "request_clarification", "hint_level": 0, "next_action": "retry", "concepts": [], "evidence_ids": []}
    response = validate_response(request, payload)
    assert response.request_id == request.request_id
    assert response.operation == "chat"


def test_evidence_progression_and_retrieval():
    from datetime import datetime, timezone
    from sql_tutor.learning_state import Evidence, next_retrieval, update_state
    state = SkillState(skill_key="x")
    evidence = Evidence(True, False, True, "isolated", "a", datetime.now(timezone.utc))
    state = update_state(state, evidence, independent_successes=0)
    state = update_state(state, evidence, independent_successes=1)
    assert state.evidence_status == "validated"
    assert next_retrieval().day >= 1


def test_count_sales_catalog_contract_is_valid_and_structural():
    import json
    from pathlib import Path
    contract = validate_contract(json.loads(Path("catalog/count_sales.json").read_text()))
    assert contract.validation.constraints[0].type == "grouped_aggregate"
    from sql_tutor.database import validate_constraints
    assert validate_constraints("SELECT customer_id, COUNT(*) AS sale_count FROM sales GROUP BY customer_id", contract) == {"grouped_count": "pass"}


def test_sql_security_blocks_mutation_cte_into_lock_and_multiple_statements():
    from sql_tutor.database import SQLBlocked, validate_sql
    contract = example_contract()
    unsafe = [
        "WITH changed AS (DELETE FROM sales RETURNING sale_id) SELECT * FROM changed",
        "SELECT * INTO new_table FROM sales",
        "SELECT * FROM sales FOR UPDATE",
        "SELECT 1; SELECT 2",
        "SELECT * FROM sales; DROP TABLE sales;",
    ]
    for query in unsafe:
        try:
            validate_sql(query, contract)
        except SQLBlocked:
            continue
        raise AssertionError(f"unsafe query was accepted: {query}")


def test_repeated_run_failure_does_not_regress_twice():
    from sql_tutor.policy import apply_attempt
    state = SkillState(skill_key="x", mastery_score=4, evidence_status="validated", confidence="high")
    first = apply_attempt(state, correct=False, assisted=False, independent=True)
    second = apply_attempt(first, correct=False, assisted=False, independent=False)
    assert first.confidence == "medium"
    assert second.confidence == first.confidence
    assert second.mastery_score == first.mastery_score


def test_pending_conceptual_assessment_has_no_score():
    from sql_tutor.evaluator import evaluate_explanation
    from sql_tutor.models import ExerciseContract
    contract = example_contract().model_copy(deep=True)
    contract.task.response_mode = "EXPLANATION_ONLY"
    contract.validation.mode = "EXPLANATION"
    contract.environment = None
    result = evaluate_explanation(contract, "GROUP BY creates one group per customer.")
    assert result.decision == "pending_review" and result.score is None


def test_global_policy_prioritizes_low_confidence_over_retrieval():
    from sql_tutor.policy import choose_next_policy
    decision = choose_next_policy([
        SkillState(skill_key="retrieval", mastery_score=5, evidence_status="mastered", confidence="high"),
        SkillState(skill_key="gap", mastery_score=3, evidence_status="validated", confidence="low"),
    ], due={"retrieval", "gap"})
    assert decision and decision.skill_key == "gap" and decision.rule == "C"


def test_explanation_and_plan_contracts_are_closed_and_valid():
    assert explanation_contract().validation.mode.value == "EXPLANATION"
    assert plan_contract().validation.mode.value == "PLAN_ANALYSIS"


def test_rubric_cannot_invent_evidence_quote():
    from sql_tutor.evaluator import evaluate_rubric
    from sql_tutor.models import RubricAssessment
    contract = explanation_contract()
    rubric = RubricAssessment.model_validate({"criteria": [{"id": "granularity", "result": "met", "evidence_quote": "not in answer", "explanation": "ok"}], "primary_skill_affected": True})
    result = evaluate_rubric(contract, rubric, response_text="GROUP BY creates one group per customer.")
    assert result.decision == "pending_review" and result.score is None


def test_generation_retries_invalid_contract_before_catalog_fallback():
    from sql_tutor.application import TutorApplication
    from sql_tutor.config import Settings
    from sql_tutor.llm import FakeLLM
    class SequenceLLM(FakeLLM):
        def __init__(self): self.calls = 0
        def complete(self, operation, context):
            self.calls += 1
            if self.calls < 2:
                return {"invalid": True}
            return super().complete(operation, context)
    settings = Settings("postgresql://x", "postgresql://x", "postgresql://x", None, None, None, None, llm_max_attempts=3)
    llm = SequenceLLM()
    app = TutorApplication(settings, llm=llm)
    assert app.generate_exercise().exercise_id == "sales_by_customer"
    assert llm.calls == 2


def test_aging_reduces_confidence_without_erasing_mastery():
    from datetime import datetime, timedelta, timezone
    from sql_tutor.learning_state import aging
    state = SkillState(skill_key="x", mastery_score=4, evidence_status="validated", confidence="high")
    aged = aging(state, last_seen=datetime.now(timezone.utc) - timedelta(days=180))
    assert aged.confidence == "low"
    assert aged.mastery_score == 4 and aged.evidence_status == "validated"


def test_catalog_has_fallback_for_plan_analysis_skill():
    import json
    from pathlib import Path
    contract = validate_contract(json.loads(Path("catalog/plan_grouping.json").read_text()))
    assert contract.validation.mode.value == "PLAN_ANALYSIS"


def test_catalog_has_fallback_for_explanation_mode():
    import json
    from pathlib import Path
    contract = validate_contract(json.loads(Path("catalog/explanation_grouping.json").read_text()))
    assert contract.task.response_mode.value == "EXPLANATION_ONLY"
    assert contract.task.evidence_kind.value == "isolated"


def test_generation_fallback_matches_skill_mode_and_evidence_kind():
    from sql_tutor.application import TutorApplication
    from sql_tutor.config import Settings
    from sql_tutor.llm import FakeLLM
    settings = Settings("postgresql://x", "postgresql://x", "postgresql://x", None, None, None, None)
    app = TutorApplication(settings, llm=FakeLLM())
    contract = app.generate_exercise("window_functions.row_number", difficulty=2, evidence_kind="transfer")
    assert contract.exercise_id == "sales_row_number_by_customer"
    explanation = app.generate_exercise("aggregation.grouping.group_by", response_mode="EXPLANATION_ONLY", evidence_kind="isolated")
    assert explanation.exercise_id == "explain_grouping"


def test_tutor_response_is_bounded_to_declared_concepts_and_hints():
    from sql_tutor.application import TutorApplication
    from sql_tutor.config import Settings
    from sql_tutor.llm import FakeLLM
    settings = Settings("postgresql://x", "postgresql://x", "postgresql://x", None, None, None, None)
    app = TutorApplication(settings, llm=FakeLLM())
    app.contract = example_contract()
    valid = app._safe_tutor_response(FakeLLM().complete("feedback", {}), allowed_hint_level=1)
    assert valid.hint_level == 1
    invalid = valid.model_dump(mode="json")
    invalid["concepts"] = ["undeclared.skill"]
    try:
        app._safe_tutor_response(invalid, allowed_hint_level=1)
    except ValueError:
        pass
    else:
        raise AssertionError("undeclared tutor concepts must be rejected")


def test_known_provider_shorthand_is_adapted_then_strictly_validated():
    from sql_tutor.exercises import adapt_provider_contract
    provider = {
        "schema_version": 2, "exercise_id": "provider_example", "version": 1,
        "task": {"description": "Return totals by customer.", "skills": ["aggregation.grouping.group_by"], "mode": "SQL_ONLY"},
        "environment": {"type": "PostgreSQL", "setup": {"tables": [{"name": "sales", "columns": [{"name": "customer_id", "type": "integer"}, {"name": "amount", "type": "numeric"}]}]}, "visible_data": {"sales": [[1, 2.0]]}, "hidden_data": {"sales": [[2, 3.0]]}},
        "validation": {"type": "result_equivalence", "options": {"ignore_order": True}},
        "pedagogy": {"target_skill": "aggregation.grouping.group_by", "difficulty": 1},
        "private": {"reference_sql": "SELECT customer_id, SUM(amount) AS total FROM sales GROUP BY customer_id", "expected_visible_rows": [{"customer_id": 1, "total": 2.0}], "expected_hidden_rows": [{"customer_id": 2, "total": 3.0}], "hints": ["a", "b", "c"], "solution_explanation": "Grouping."},
    }
    adapted = adapt_provider_contract(provider, {"target_skill": "aggregation.grouping.group_by", "difficulty": 1, "response_mode": "SQL_ONLY", "evidence_kind": "isolated"})
    assert validate_contract(adapted).task.primary_skill == "aggregation.grouping.group_by"


def test_http_llm_requests_strict_schema_for_closed_operations(monkeypatch):
    from sql_tutor.llm import HTTPChatLLM
    captured = {}
    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": '{"message":"ok"}'}}]}
    def fake_post(endpoint, **kwargs):
        captured.update(kwargs)
        return Response()
    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    result = HTTPChatLLM("https://openrouter.ai/api/v1", "fixed/model", "key", 1, 1).complete("chat", {})
    assert result == {"message": "ok"}
    response_format = captured["json"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert captured["json"]["provider"]["require_parameters"] is True


def test_incomplete_result_and_hidden_permission_are_inconclusive():
    from sql_tutor.evaluator import evaluate_sql
    from sql_tutor.models import ExecutionResult
    contract = example_contract()
    visible = ExecutionResult(status="ok", submitted_sql="SELECT 1", complete=False, preview_rows=[])
    hidden = ExecutionResult(status="ok", submitted_sql="SELECT 1", complete=True, preview_rows=[])
    assert evaluate_sql(contract, visible, hidden).decision == "inconclusive"
    hidden_error = ExecutionResult(status="error", submitted_sql="SELECT 1", failure_kind="permission_error", safe_error="SQL execution failed.")
    complete_visible = ExecutionResult(status="ok", submitted_sql="SELECT 1", complete=True, preview_rows=[])
    assert evaluate_sql(contract, complete_visible, hidden_error).decision == "inconclusive"


def test_application_exposes_bounded_goal_decomposition_and_review():
    from sql_tutor.application import TutorApplication
    from sql_tutor.config import Settings
    from sql_tutor.llm import FakeLLM
    app = TutorApplication(Settings("postgresql://x", "postgresql://x", "postgresql://x", None, None, None, None), llm=FakeLLM())
    graph = app.decompose_goal("Learn aggregation")
    assert len(graph["nodes"]) <= 20
    assert app.review_exercise(example_contract().model_dump(mode="json"))["valid"] is True
    assert app.review_exercise({"invalid": True})["valid"] is False


def test_next_exercise_rejects_stale_session_revision():
    from sql_tutor.application import TutorApplication
    from sql_tutor.config import Settings
    from sql_tutor.llm import FakeLLM
    class RepoDouble:
        def __init__(self): self.revisions = 0
        def run_state(self, run_id): return "completed"
        def session_revision(self, session_id):
            self.revisions += 1
            return ("active", 0 if self.revisions == 1 else 1)
        def list_skill_states(self, profile_id): return []
        def get_skill_state(self, profile_id, skill_key): return SkillState(skill_key=skill_key)
    app = TutorApplication(Settings("postgresql://x", "postgresql://x", "postgresql://x", None, None, None, None), llm=FakeLLM())
    app.repo, app.profile_id, app.session_id, app.run_id = RepoDouble(), "p", "s", "r"
    app.contract = example_contract()
    app.generate_exercise = lambda *args, **kwargs: example_contract()
    try:
        app.next_exercise()
    except ValueError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale exercise responses must be rejected")


def test_zero_hint_contract_does_not_index_private_hints():
    from sql_tutor.application import TutorApplication
    from sql_tutor.config import Settings
    from sql_tutor.exercises import example_contract
    from sql_tutor.llm import FakeLLM
    settings = Settings("postgresql://x", "postgresql://x", "postgresql://x", None, None, None, None)
    app = TutorApplication(settings, llm=FakeLLM())
    app.contract = example_contract().model_copy(deep=True)
    app.contract.pedagogy.max_hint_level = 0
    assert app.hint(0)["hint_level"] == 0


def test_registered_alias_normalization_respects_input_column_collision():
    from sql_tutor.dialects import normalize_sql
    contract = example_contract()
    normalized = normalize_sql("SELECT customer_id, SUM(amount) AS total_sales FROM sales GROUP BY customer_id HAVING total_sales > 100", contract)
    assert normalized.extension_ids == ["redshift.having_alias_reference"]
    assert "HAVING SUM(amount) > 100" in normalized.executed_sql
    unchanged = normalize_sql("SELECT customer_id, amount FROM sales", contract)
    assert unchanged.extension_ids == [] and unchanged.executed_sql == "SELECT customer_id, amount FROM sales"
