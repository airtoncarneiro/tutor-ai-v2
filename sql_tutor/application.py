from __future__ import annotations

from .config import Settings
from .database import Database, SQLBlocked
from .evaluator import evaluate_explanation, evaluate_plan, evaluate_sql, evaluate_rubric
from .exercises import ContractError, adapt_provider_contract, contract_hash, example_contract, validate_contract
from .llm import FakeLLM, HTTPChatLLM
from .provision import provision
from .repositories import Repository
from .policy import apply_attempt, choose_next_policy, retrieval_due
from .models import EvaluationResult, TutorResponse


class TutorApplication:
    def __init__(self, settings: Settings, *, llm=None):
        settings.validate_urls()
        self.settings = settings
        self.contract = example_contract()
        self.repo = Repository(settings.database_app_url, settings.database_admin_url)
        self.db = Database(settings.database_app_url, settings.database_runner_url, settings.database_evaluator_url, timeout_ms=settings.sql_timeout_ms, lock_timeout_ms=settings.sql_lock_timeout_ms, max_chars=settings.sql_max_chars, row_limit=settings.evaluation_row_limit, byte_limit=settings.result_byte_limit)
        self.llm = llm or (HTTPChatLLM(settings.llm_base_url, settings.llm_model, settings.llm_api_key, settings.llm_timeout_seconds, settings.llm_max_attempts) if settings.llm_base_url and settings.llm_model else FakeLLM())

    def initialize(self, goal: str = "Learn SQL aggregation", mode: str = "FOCUSED_LEARNING", declaration: str | None = None) -> None:
        self.learning_goal = goal
        self.knowledge_declaration = declaration.strip() if declaration else None
        self.profile_id = self.repo.ensure_profile()
        self.session_id = self.repo.ensure_active_session(self.profile_id, goal, mode, self.knowledge_declaration)
        self.repo.recover_operations(self.session_id)
        self.repo.apply_aging(self.profile_id)
        states = self.repo.list_skill_states(self.profile_id)
        due = {state.skill_key for state in states if retrieval_due(state.retrieval_due_at)}
        self.policy_decision = choose_next_policy(states, due=due)
        if not self.repo.current_run_exists(self.session_id):
            initial_mode = self._initial_response_mode_for_goal(goal)
            self.contract = self.generate_exercise(
                self._initial_skill_for_goal(goal),
                difficulty=1,
                response_mode=initial_mode,
                evidence_kind="isolated",
            )
            provision(self.contract, self.settings.database_app_url)
            self._save_contract_and_run()
        else:
            with self.repo.connect() as conn:
                self.run_id = str(conn.execute("SELECT current_run_id FROM tutor_state.learning_sessions WHERE id=%s", (self.session_id,)).fetchone()[0])
            stored_contract = self.repo.current_contract(self.session_id)
            if stored_contract is None:
                raise RuntimeError("Active session points to a missing exercise contract")
            self.contract = stored_contract
        self.failed_count, self.hint_level = self.repo.run_help_stats(self.run_id)
        self.run_snapshot = self.repo.run_snapshot(self.run_id)
        self.skill_states = self.repo.list_skill_states(self.profile_id)
        self.evidence_events = self.repo.recent_evidence(self.profile_id)
        self.evidence_details = self.repo.evidence_details(self.profile_id)

    @staticmethod
    def _initial_skill_for_goal(goal: str) -> str:
        """Choose a bounded seed skill before the first LLM-generated exercise."""
        normalized = goal.casefold()
        if "window" in normalized or "janela" in normalized or "row_number" in normalized:
            return "window_functions.row_number"
        if "recursive" in normalized or "recurs" in normalized or "cte" in normalized:
            return "recursive_cte.recursive_structure.anchor_member"
        if "plan" in normalized or "performance" in normalized or "desempenho" in normalized:
            return "query_performance.execution_plan_analysis.node_types"
        if "count" in normalized or "contagem" in normalized:
            # The MVP catalog starts aggregation at grouping granularity; a
            # real LLM may refine this seed to COUNT during generation.
            return "aggregation.grouping.group_by"
        return "aggregation.grouping.group_by"

    @staticmethod
    def _initial_response_mode_for_goal(goal: str) -> str:
        normalized = goal.casefold()
        if "plan" in normalized or "performance" in normalized or "desempenho" in normalized:
            return "EXPLANATION_ONLY"
        return "SQL_ONLY"

    def decompose_goal(self, goal: str | None = None) -> dict:
        """Return the bounded official competency graph used by the MVP."""
        nodes = [
            {"key": "aggregation.grouping.group_by", "description": "Group rows at the intended result granularity.", "response_modes": ["SQL_ONLY", "SQL_PLUS_REASONING", "EXPLANATION_ONLY"]},
            {"key": "aggregation.aggregate_functions.sum", "description": "Apply SUM to measure values within each group.", "response_modes": ["SQL_ONLY", "SQL_PLUS_REASONING"]},
            {"key": "aggregation.aggregate_functions.count", "description": "Count rows or non-null values deliberately.", "response_modes": ["SQL_ONLY", "EXPLANATION_ONLY"]},
            {"key": "window_functions.row_number", "description": "Number rows within a defined window.", "response_modes": ["SQL_ONLY", "EXPLANATION_ONLY"]},
            {"key": "window_functions.partition_by", "description": "Define independent window partitions.", "response_modes": ["SQL_ONLY", "EXPLANATION_ONLY"]},
            {"key": "recursive_cte.recursive_structure.anchor_member", "description": "Define the anchor member of a recursive query.", "response_modes": ["SQL_ONLY", "EXPLANATION_ONLY"]},
            {"key": "query_performance.execution_plan_analysis.node_types", "description": "Interpret operators in an observed PostgreSQL plan.", "response_modes": ["EXPLANATION_ONLY"]},
        ]
        return {"goal": goal or getattr(self, "learning_goal", ""), "nodes": nodes, "prerequisite_edges": [{"from": "aggregation.grouping.group_by", "to": "aggregation.aggregate_functions.sum"}, {"from": "window_functions.partition_by", "to": "window_functions.row_number"}]}

    def select_next(self):
        """Select one next action using the deterministic global policy."""
        states = self.repo.list_skill_states(self.profile_id) if hasattr(self, "profile_id") else []
        eligible = {self.contract.task.primary_skill, *self.contract.task.secondary_skills}
        due = {state.skill_key for state in states if retrieval_due(state.retrieval_due_at)}
        decision = choose_next_policy(states, eligible=eligible, current_focus=self.contract.task.primary_skill, due=due)
        if decision is None:
            decision = choose_next_policy([self.repo.get_skill_state(self.profile_id, self.contract.task.primary_skill)]) if hasattr(self, "profile_id") else None
        if decision is None:
            return None
        return {"primary_skill": decision.skill_key, "policy_rule": decision.rule, "prerequisite_subrule": None, "action": decision.action, "uncertainty": decision.reason, "context_tag": self.contract.task.context_tag, "evidence_kind": self.contract.task.evidence_kind.value, "difficulty": self.contract.task.difficulty, "response_mode": self.contract.task.response_mode.value}

    def review_exercise(self, candidate: dict) -> dict:
        """Review a candidate without executing or publishing it."""
        try:
            contract = validate_contract(candidate)
            return {"valid": True, "issues": [], "exercise_id": contract.exercise_id}
        except Exception as exc:
            return {"valid": False, "issues": [{"code": "invalid_contract", "message": str(exc)[:500], "field_path": "contract"}]}

    def generate_exercise(self, skill_key: str | None = None, *, difficulty: int = 1, response_mode: str = "SQL_ONLY", evidence_kind: str = "isolated"):
        skill_key = skill_key or self.contract.task.primary_skill
        request = {"learning_goal": getattr(self, "learning_goal", "Learn SQL aggregation"), "target_skill": skill_key, "difficulty": difficulty, "response_mode": response_mode, "evidence_kind": evidence_kind}
        candidate = None
        errors: list[str] = []
        for attempt in range(self.settings.llm_max_attempts):
            context = dict(request)
            if candidate is not None:
                context.update({"candidate_contract": candidate, "repair_errors": errors[-8:]})
            try:
                complete = getattr(self.llm, "complete_with_budget", self.llm.complete)
                candidate = complete("generate_exercise", context, 1) if hasattr(self.llm, "complete_with_budget") else complete("generate_exercise", context)
                candidate = adapt_provider_contract(candidate, request)
                contract = validate_contract(candidate)
                if contract.task.primary_skill != skill_key:
                    raise ContractError("LLM changed the requested primary skill")
                if contract.task.response_mode.value != response_mode:
                    raise ContractError("LLM changed the requested response mode")
                if contract.task.evidence_kind.value != evidence_kind:
                    raise ContractError("LLM changed the requested evidence kind")
                if contract.task.difficulty > difficulty:
                    raise ContractError("LLM returned an exercise above the requested difficulty")
                return contract
            except Exception as exc:
                if hasattr(exc, "errors"):
                    locations = [".".join(str(part) for part in item.get("loc", ())) for item in exc.errors()]
                    errors.extend(locations[:8] or [type(exc).__name__])
                else:
                    errors.append(str(exc)[:160])
        from pathlib import Path
        import json
        catalog_dir = Path(__file__).resolve().parent.parent / "catalog"
        for path in sorted(catalog_dir.glob("*.json")):
            try:
                catalog_contract = validate_contract(json.loads(path.read_text(encoding="utf-8")))
                if (catalog_contract.task.primary_skill == skill_key
                        and catalog_contract.task.response_mode.value == response_mode
                        and catalog_contract.task.evidence_kind.value == evidence_kind
                        and catalog_contract.task.difficulty <= difficulty):
                    return catalog_contract
            except Exception:
                continue
        raise ContractError(f"No compatible exercise is available for skill {skill_key} after {self.settings.llm_max_attempts} generation attempts")

    def run_sql(self, sql: str, *, action_id: str | None = None, persist: bool = True):
        try:
            result = self.db.execute(self.contract, sql, preview_limit=self.settings.display_row_limit)
            if persist and hasattr(self, "session_id"):
                self.repo.record_sql_run(self.session_id, self.run_id, sql, result.model_dump(mode="json"), action_id=action_id)
            return result
        except SQLBlocked as exc:
            from .models import ExecutionResult
            result = ExecutionResult(status="blocked", submitted_sql=sql, safe_error=str(exc), failure_kind="unsupported_capability")
            if persist and hasattr(self, "session_id"):
                self.repo.record_sql_run(self.session_id, self.run_id, sql, result.model_dump(mode="json"), action_id=action_id)
            return result

    def submit(self, sql: str, reasoning: str | None = None, *, action_id: str | None = None):
        visible = self.run_sql(sql, persist=False)
        if visible.status != "ok" or not visible.complete:
            decision = {"blocked": "blocked", "inconclusive": "inconclusive", "error": "learner_sql_error"}.get(visible.status, "inconclusive")
            evaluation = EvaluationResult(decision=decision, score=None, execution_status=visible.status, issues=[visible.safe_error or "The submission did not produce assessable evidence."])
            if hasattr(self, "session_id"):
                self.repo.record_submission(self.session_id, self.run_id, sql, evaluation.model_dump(mode="json"), reasoning=reasoning, action_id=action_id)
            return visible, evaluation
        hidden = self.db.execute(self.contract, sql, hidden=True, preview_limit=self.settings.evaluation_row_limit)
        evaluation = evaluate_sql(self.contract, visible, hidden)
        if evaluation.decision == "correct" and self.contract.validation.reasoning_rubric:
            rubric = self._assess_reasoning(reasoning)
            if rubric is None:
                evaluation = EvaluationResult(decision="pending_review", score=None, execution_status="ok", issues=["The SQL result is correct, but the required rationale awaits a valid rubric review."])
            else:
                rubric_result = evaluate_rubric(self.contract, rubric, execution_status="ok", response_text=reasoning)
                if rubric_result.decision != "correct":
                    evaluation = rubric_result
        if hasattr(self, "session_id"):
            was_existing = bool(action_id and self.repo.operation_exists(action_id))
            current = self.repo.get_skill_state(self.profile_id, self.contract.task.primary_skill)
            independent = self.repo.run_attempt_count(self.run_id) == 0
            updated = apply_attempt(current, correct=evaluation.decision == "correct", assisted=False, independent=independent)
            should_update = not was_existing and (evaluation.decision == "correct" or evaluation.primary_skill_affected)
            self.repo.record_submission(
                self.session_id, self.run_id, sql, evaluation.model_dump(mode="json"), action_id=action_id,
                profile_id=self.profile_id if should_update else None,
                skill_state=current if should_update else None,
                updated_skill_state=updated if should_update else None,
                skill_key=self.contract.task.primary_skill if should_update else None,
                independent=independent,
                reasoning=reasoning,
            )
        self.last_feedback = self._feedback(evaluation)
        states = self.repo.list_skill_states(self.profile_id)
        self.policy_decision = choose_next_policy(states, current_focus=self.contract.task.primary_skill, due={state.skill_key for state in states if retrieval_due(state.retrieval_due_at)})
        return visible, evaluation

    def _assess_reasoning(self, reasoning: str | None):
        try:
            from .models import RubricAssessment
            payload = self.llm.complete("assess_response", {"exercise": self.contract.task.statement, "response": reasoning or "", "rubric": [item.model_dump(mode="json") for item in self.contract.validation.reasoning_rubric]})
            return RubricAssessment.model_validate(payload)
        except Exception:
            return None

    def _feedback(self, evaluation: EvaluationResult):
        fallback = {
            "correct": {"message": "Correct. The submitted query matched the required evidence.", "pedagogical_move": "acknowledge_progress", "hint_level": 0, "next_action": "next_exercise"},
            "incorrect": {"message": "The result does not satisfy the exercise yet. Compare the output with the required grouping and aggregate.", "pedagogical_move": "suggest_revision", "hint_level": 0, "next_action": "retry"},
        }.get(evaluation.decision, {"message": "The submission could not be assessed as learner evidence. Try again when the environment is available.", "pedagogical_move": "request_clarification", "hint_level": 0, "next_action": "retry"})
        payload = {**fallback, "concepts": [self.contract.task.primary_skill], "evidence_ids": []}
        try:
            candidate = self.llm.complete("feedback", {"exercise": self.contract.task.statement, "evaluation": evaluation.model_dump(mode="json"), "allowed_hint_level": 0})
            payload = self._safe_tutor_response(candidate, allowed_hint_level=0).model_dump(mode="json")
        except Exception:
            pass
        if hasattr(self, "session_id"):
            self.repo.record_tutor_message(self.session_id, self.run_id, "tutor", payload["message"], model_id=getattr(self.llm, "model_id", None))
        return payload

    def hint(self, current_level: int = 0, *, action_id: str | None = None):
        level = min(current_level + 1, self.contract.pedagogy.max_hint_level)
        if level < 1:
            return {"message": "Hints are not available for this exercise.", "hint_level": 0, "pedagogical_move": "request_clarification", "next_action": "retry", "concepts": [self.contract.task.primary_skill], "evidence_ids": []}
        if hasattr(self, "run_id"):
            self.repo.increment_hint(self.run_id, level, session_id=self.session_id, action_id=action_id)
            self.hint_level = max(getattr(self, "hint_level", 0), level)
        return {"message": self.contract.private.hints[level - 1], "hint_level": level, "pedagogical_move": "give_concept_hint", "next_action": "retry", "concepts": [self.contract.task.primary_skill], "evidence_ids": []}

    def chat(self, message: str):
        response = self.llm.complete("chat", {"student_input": {"chat_message": message}, "exercise": self.contract.task.statement})
        try:
            response = self._safe_tutor_response(response, allowed_hint_level=getattr(self.contract.pedagogy, "max_hint_level", 0)).model_dump(mode="json")
        except Exception:
            response = {"message": "I can help you reason about the current exercise. What part is unclear?", "pedagogical_move": "ask_guiding_question", "hint_level": 0, "next_action": "retry", "concepts": [], "evidence_ids": []}
        if hasattr(self, "session_id"):
            self.repo.record_tutor_message(self.session_id, self.run_id, "student", message, model_id=None)
            self.repo.record_tutor_message(self.session_id, self.run_id, "tutor", response["message"], model_id=getattr(self.llm, "model_id", None))
        return response

    def _safe_tutor_response(self, payload: dict, *, allowed_hint_level: int) -> TutorResponse:
        response = TutorResponse.model_validate(payload)
        if response.hint_level > allowed_hint_level:
            raise ValueError("Tutor response exceeded the allowed hint level")
        allowed_concepts = {self.contract.task.primary_skill, *self.contract.task.secondary_skills}
        if any(concept not in allowed_concepts for concept in response.concepts):
            raise ValueError("Tutor response introduced an undeclared concept")
        private_reference = self.contract.private.reference_sql
        if private_reference and private_reference.strip().lower() in response.message.strip().lower():
            raise ValueError("Tutor response leaked the private reference SQL")
        return response

    def summarize(self):
        """Return a bounded session summary without changing learning state."""
        snapshot = {
            "learning_goal": getattr(self, "learning_goal", ""),
            "current_focus": self.contract.task.primary_skill,
            "exercise_title": self.contract.task.title,
            "failed_attempts": getattr(self, "failed_count", 0),
            "hint_level": getattr(self, "hint_level", 0),
        }
        try:
            response = self.llm.complete("summarize", {"snapshot": snapshot})
            message = str(response.get("message", "")).strip()
            if not message or len(message) > 2500:
                raise ValueError("invalid summary")
            return {"message": message}
        except Exception:
            return {"message": f"Current focus: {snapshot['current_focus']}. Continue with the active exercise when you return."}

    def show_solution(self, failed_count: int, hint_level: int, *, action_id: str | None = None):
        if hasattr(self, "run_id"):
            persisted_failed, persisted_hints = self.repo.run_help_stats(self.run_id)
            failed_count = max(failed_count, persisted_failed)
            hint_level = max(hint_level, persisted_hints)
        if not self.contract.pedagogy.allow_solution_reveal or (failed_count < 3 and hint_level < 2):
            raise ValueError("Show Solution requires three failed submissions or two hints.")
        if hasattr(self, "session_id"):
            self.repo.reveal_solution(self.session_id, self.run_id, action_id=action_id)
        return {"reference_sql": self.contract.private.reference_sql, "explanation": self.contract.private.solution_explanation}

    def close(self, *, action_id: str | None = None) -> None:
        self.repo.close_session_command(self.session_id, action_id=action_id)

    def change_goal(self, goal: str) -> None:
        self.session_id = self.repo.change_goal(self.profile_id, self.session_id, goal)
        self.learning_goal = goal
        self.contract = self.generate_exercise()
        provision(self.contract, self.settings.database_app_url)
        self._save_contract_and_run()
        self.failed_count, self.hint_level = 0, 0

    def _save_contract_and_run(self) -> None:
        payload = self.contract.model_dump(mode="json")
        _, self.run_id, persisted_payload, _ = self.repo.save_contract_and_run(self.session_id, payload, contract_hash(self.contract))
        # The repository may allocate a new immutable version when a provider
        # reuses an existing logical exercise id with changed content.
        self.contract = validate_contract(persisted_payload)

    def submit_response(self, response: str, reasoning: str | None = None, *, action_id: str | None = None):
        mode = self.contract.task.response_mode.value
        if mode == "SQL_PLUS_REASONING" and not (reasoning or "").strip():
            raise ValueError("SQL_PLUS_REASONING requires a technical rationale.")
        if not response or not response.strip():
            raise ValueError("An answer is required.")
        if mode in {"SQL_ONLY", "SQL_PLUS_REASONING"}:
            return self.submit(response, reasoning, action_id=action_id)
        if self.contract.validation.mode.value == "PLAN_ANALYSIS":
            supplied = self.contract.validation.supplied_query or response
            plan = self.db.explain(self.contract, supplied)
            try:
                rubric_payload = self.llm.complete("assess_response", {"exercise": self.contract.task.statement, "response": response, "reasoning": reasoning, "plan": plan.plan_json})
                from .models import RubricAssessment
                rubric = RubricAssessment.model_validate(rubric_payload)
            except Exception:
                rubric = None
            evaluation = evaluate_plan(self.contract, plan, rubric)
            self._persist_non_sql_response(response, reasoning, evaluation, action_id)
            return plan, evaluation
        try:
            rubric_payload = self.llm.complete("assess_response", {"exercise": self.contract.task.statement, "response": response})
            from .models import RubricAssessment
            rubric = RubricAssessment.model_validate(rubric_payload)
        except Exception:
            rubric = None
        evaluation = evaluate_explanation(self.contract, response, rubric)
        self._persist_non_sql_response(response, reasoning, evaluation, action_id)
        return None, evaluation

    def retry_review(self):
        pending = self.repo.pending_submission(self.run_id)
        if not pending:
            raise ValueError("There is no pending review for the current exercise.")
        submission_id, submitted_sql, stored_reasoning, _ = pending
        response = stored_reasoning or ""
        if self.contract.validation.mode.value == "PLAN_ANALYSIS":
            supplied = self.contract.validation.supplied_query or submitted_sql or ""
            plan = self.db.explain(self.contract, supplied)
            rubric_payload = self.llm.complete("assess_response", {"exercise": self.contract.task.statement, "response": response, "plan": plan.plan_json})
            from .models import RubricAssessment
            rubric = RubricAssessment.model_validate(rubric_payload)
            evaluation = evaluate_plan(self.contract, plan, rubric)
        else:
            rubric = self._assess_reasoning(response)
            if self.contract.task.response_mode.value == "SQL_PLUS_REASONING":
                evaluation = evaluate_rubric(self.contract, rubric, execution_status="ok", response_text=response) if rubric else EvaluationResult(decision="pending_review", score=None, execution_status="ok", issues=["A valid rationale review is still unavailable."])
            else:
                evaluation = evaluate_explanation(self.contract, response, rubric)
        current = self.repo.get_skill_state(self.profile_id, self.contract.task.primary_skill)
        independent = self.repo.run_attempt_count(self.run_id) == 0
        updated = apply_attempt(current, correct=evaluation.decision == "correct", assisted=False, independent=independent)
        self.repo.finalize_review(self.session_id, self.run_id, str(submission_id), evaluation.model_dump(mode="json"), profile_id=self.profile_id if evaluation.decision == "correct" or evaluation.primary_skill_affected else None, skill_state=current, updated_skill_state=updated, skill_key=self.contract.task.primary_skill, independent=independent)
        return evaluation

    def _persist_non_sql_response(self, response: str, reasoning: str | None, evaluation: EvaluationResult, action_id: str | None) -> None:
        if not hasattr(self, "session_id"):
            return
        current = self.repo.get_skill_state(self.profile_id, self.contract.task.primary_skill)
        should_update = evaluation.decision == "correct" or evaluation.primary_skill_affected
        independent = self.repo.run_attempt_count(self.run_id) == 0
        updated = apply_attempt(current, correct=evaluation.decision == "correct", assisted=False, independent=independent)
        self.repo.record_submission(self.session_id, self.run_id, None, evaluation.model_dump(mode="json"), reasoning=response, action_id=action_id, profile_id=self.profile_id if should_update else None, skill_state=current if should_update else None, updated_skill_state=updated if should_update else None, skill_key=self.contract.task.primary_skill if should_update else None, independent=independent)

    def save_draft(self, sql_text: str, reasoning: str | None = None, *, action_id: str | None = None) -> None:
        self.repo.save_draft(self.session_id, self.run_id, sql_text, reasoning, action_id=action_id)

    def skip(self, *, action_id: str | None = None) -> None:
        self.repo.skip_run(self.session_id, self.run_id, action_id=action_id)

    def next_exercise(self) -> None:
        if hasattr(self, "run_id") and self.repo.run_state(self.run_id) not in {"completed", "skipped", "revealed", "abandoned"}:
            raise ValueError("Finish, skip, or reveal the current exercise before requesting the next one.")
        session_id, session_revision = self.session_id, self.repo.session_revision(self.session_id)
        states = self.repo.list_skill_states(self.profile_id)
        eligible = {self.contract.task.primary_skill, *self.contract.task.secondary_skills}
        due = {state.skill_key for state in states if retrieval_due(state.retrieval_due_at)}
        decision = choose_next_policy(states, eligible=eligible, current_focus=self.contract.task.primary_skill, due=due)
        if decision is None:
            decision = choose_next_policy([self.repo.get_skill_state(self.profile_id, self.contract.task.primary_skill)])
        self.policy_decision = decision
        target_skill = decision.skill_key if decision else self.contract.task.primary_skill
        difficulty = min(5, max(1, self.contract.task.difficulty + (1 if decision and decision.rule in {"E2", "E3"} else 0)))
        evidence_kind = "delayed_retrieval" if decision and decision.rule == "F" else "transfer" if decision and decision.rule in {"D2.1", "E2"} else "isolated"
        candidate = self.generate_exercise(target_skill, difficulty=difficulty, evidence_kind=evidence_kind)
        if self.session_id != session_id or self.repo.session_revision(session_id) != session_revision:
            raise ValueError("The exercise response is stale because the learning session changed.")
        self.contract = candidate
        provision(self.contract, self.settings.database_app_url)
        self._save_contract_and_run()
