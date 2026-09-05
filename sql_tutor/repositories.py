from __future__ import annotations

import json
import uuid
import hashlib


class Repository:
    """Small psycopg repository; SQL remains explicit and easy to audit."""

    def __init__(self, url: str, admin_url: str | None = None):
        self.url = url
        self.admin_url = admin_url or url

    def connect(self):
        import psycopg
        return psycopg.connect(self.url)

    def migrate(self, migration_path: str) -> None:
        sql = open(migration_path, encoding="utf-8").read()
        import psycopg
        with psycopg.connect(self.admin_url) as conn:
            conn.execute(sql)

    def ensure_profile(self) -> str:
        profile_id = str(uuid.uuid4())
        import psycopg
        try:
            with self.connect() as conn:
                row = conn.execute("SELECT id FROM tutor_state.student_profiles WHERE singleton_key=1").fetchone()
                if row:
                    return str(row[0])
                row = conn.execute("INSERT INTO tutor_state.student_profiles (id, singleton_key) VALUES (%s, 1) RETURNING id", (profile_id,)).fetchone()
                return str(row[0])
        except psycopg.errors.UniqueViolation:
            with self.connect() as conn:
                return str(conn.execute("SELECT id FROM tutor_state.student_profiles WHERE singleton_key=1").fetchone()[0])

    def active_session(self, profile_id: str):
        with self.connect() as conn:
            return conn.execute("SELECT id, learning_goal, mode, revision FROM tutor_state.learning_sessions WHERE profile_id=%s AND status='active'", (profile_id,)).fetchone()

    def create_session(self, profile_id: str, goal: str, mode: str = "FOCUSED_LEARNING", knowledge_declaration: str | None = None) -> str:
        session_id = str(uuid.uuid4())
        with self.connect() as conn:
            row = conn.execute("INSERT INTO tutor_state.learning_sessions (id, profile_id, learning_goal, mode, knowledge_declaration) VALUES (%s,%s,%s,%s,%s) RETURNING id", (session_id, profile_id, goal, mode, knowledge_declaration)).fetchone()
            return str(row[0])

    def ensure_active_session(self, profile_id: str, goal: str, mode: str = "FOCUSED_LEARNING", knowledge_declaration: str | None = None) -> str:
        existing = self.active_session(profile_id)
        if existing:
            if knowledge_declaration is not None:
                with self.connect() as conn:
                    conn.execute("UPDATE tutor_state.learning_sessions SET knowledge_declaration=%s WHERE id=%s AND status='active'", (knowledge_declaration, existing[0]))
            return str(existing[0])
        try:
            return self.create_session(profile_id, goal, mode, knowledge_declaration)
        except __import__("psycopg").errors.UniqueViolation:
            # Another local Streamlit process won the singleton active-session race.
            existing = self.active_session(profile_id)
            if existing:
                return str(existing[0])
            raise

    def current_run_exists(self, session_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM tutor_state.learning_sessions WHERE id=%s AND current_run_id IS NOT NULL", (session_id,)).fetchone()
            return row is not None

    def session_revision(self, session_id: str) -> tuple[str, int] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT status, revision FROM tutor_state.learning_sessions WHERE id=%s", (session_id,)).fetchone()
        return (str(row[0]), int(row[1])) if row else None

    def current_contract(self, session_id: str):
        row = None
        with self.connect() as conn:
            row = conn.execute("""SELECT c.contract_json
                FROM tutor_state.learning_sessions s
                JOIN tutor_state.exercise_runs r ON r.id=s.current_run_id
                JOIN tutor_state.exercise_contracts c ON c.id=r.contract_id
                WHERE s.id=%s""", (session_id,)).fetchone()
        if not row:
            return None
        from .exercises import validate_contract
        return validate_contract(row[0])

    def run_attempt_count(self, run_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT attempt_count FROM tutor_state.exercise_runs WHERE id=%s", (run_id,)).fetchone()
            return int(row[0]) if row else 0

    def run_state(self, run_id: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT state FROM tutor_state.exercise_runs WHERE id=%s", (run_id,)).fetchone()
            return str(row[0]) if row else None

    def run_help_stats(self, run_id: str) -> tuple[int, int]:
        with self.connect() as conn:
            row = conn.execute("SELECT failed_count, hint_level FROM tutor_state.exercise_runs WHERE id=%s", (run_id,)).fetchone()
            return (int(row[0]), int(row[1])) if row else (0, 0)

    def run_snapshot(self, run_id: str) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT state, draft_sql, draft_reasoning, attempt_count, failed_count, hint_level, solution_revealed FROM tutor_state.exercise_runs WHERE id=%s", (run_id,)).fetchone()
        if not row:
            return {}
        return {"state": row[0], "draft_sql": row[1], "draft_reasoning": row[2], "attempt_count": int(row[3]), "failed_count": int(row[4]), "hint_level": int(row[5]), "solution_revealed": bool(row[6])}

    def recent_evidence(self, profile_id: str, limit: int = 10) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT e.skill_key, e.result, e.independent, e.assisted, e.source, e.created_at FROM tutor_state.evidence_events e JOIN tutor_state.submissions sub ON sub.operation_id=e.submission_id JOIN tutor_state.exercise_runs r ON r.id=sub.run_id JOIN tutor_state.learning_sessions l ON l.id=r.session_id WHERE l.profile_id=%s ORDER BY e.created_at DESC LIMIT %s", (profile_id, limit)).fetchall()
        return [{"skill_key": row[0], "result": row[1], "independent": bool(row[2]), "assisted": bool(row[3]), "source": row[4], "created_at": row[5].isoformat() if row[5] else None} for row in rows]

    def evidence_details(self, profile_id: str, limit: int = 20) -> list[dict]:
        """Return the auditable, learner-facing evidence behind recent events."""
        with self.connect() as conn:
            rows = conn.execute("""SELECT e.id, e.skill_key, e.result, e.independent,
                    e.assisted, e.source, e.error_kind, e.before_state,
                    e.after_state, e.policy_version, e.created_at,
                    sub.submitted_sql, sub.reasoning, sub.hint_level_at_submit,
                    sub.evaluation_json, r.context_tag, r.evidence_kind,
                    c.exercise_id
                FROM tutor_state.evidence_events e
                JOIN tutor_state.submissions sub ON sub.operation_id=e.submission_id
                JOIN tutor_state.exercise_runs r ON r.id=sub.run_id
                JOIN tutor_state.learning_sessions l ON l.id=r.session_id
                JOIN tutor_state.exercise_contracts c ON c.id=r.contract_id
                WHERE l.profile_id=%s
                ORDER BY e.created_at DESC
                LIMIT %s""", (profile_id, limit)).fetchall()
        keys = ("id", "skill_key", "result", "independent", "assisted", "source", "error_kind", "before_state", "after_state", "policy_version", "created_at", "submitted_sql", "reasoning", "hint_level_at_submit", "evaluation", "context_tag", "evidence_kind", "exercise_id")
        details = []
        for row in rows:
            item = dict(zip(keys, row))
            if item["created_at"]:
                item["created_at"] = item["created_at"].isoformat()
            details.append(item)
        return details

    def get_skill_state(self, profile_id: str, skill_key: str):
        from .models import SkillState
        with self.connect() as conn:
            row = conn.execute("SELECT skill_key, mastery_score, evidence_status, confidence, successful_attempts, failed_attempts, hints_required, last_seen, retrieval_due_at, declared_level, recurring_errors, policy_version FROM tutor_state.skill_states WHERE profile_id=%s AND skill_key=%s", (profile_id, skill_key)).fetchone()
        fields = ("mastery_score", "evidence_status", "confidence", "successful_attempts", "failed_attempts", "hints_required", "last_seen", "retrieval_due_at", "declared_level", "recurring_errors", "policy_version")
        return SkillState(skill_key=skill_key, **dict(zip(fields, row[1:]))) if row else SkillState(skill_key=skill_key)

    def list_skill_states(self, profile_id: str):
        from .models import SkillState
        with self.connect() as conn:
            rows = conn.execute("SELECT skill_key, mastery_score, evidence_status, confidence, successful_attempts, failed_attempts, hints_required, last_seen, retrieval_due_at, declared_level, recurring_errors, policy_version FROM tutor_state.skill_states WHERE profile_id=%s ORDER BY skill_key", (profile_id,)).fetchall()
        fields = ("mastery_score", "evidence_status", "confidence", "successful_attempts", "failed_attempts", "hints_required", "last_seen", "retrieval_due_at", "declared_level", "recurring_errors", "policy_version")
        return [SkillState(skill_key=row[0], **dict(zip(fields, row[1:]))) for row in rows]

    def apply_aging(self, profile_id: str, *, now=None) -> None:
        from .learning_state import aging
        from datetime import datetime, timezone
        now = now or datetime.now(timezone.utc)
        for state in self.list_skill_states(profile_id):
            updated = aging(state, last_seen=state.last_seen, now=now)
            if updated.confidence == state.confidence:
                continue
            with self.connect() as conn:
                intervals = max(1, ((now - state.last_seen).days // 90) if state.last_seen else 1)
                dedup_key = f"aging:{profile_id}:{state.skill_key}:{intervals}"
                inserted = conn.execute("INSERT INTO tutor_state.lifecycle_events (id, session_id, skill_key, kind, dedup_key, before_state, after_state) VALUES (%s,NULL,%s,'aging',%s,%s,%s) ON CONFLICT (dedup_key) DO NOTHING", (str(uuid.uuid4()), state.skill_key, dedup_key, json.dumps(state.model_dump(mode="json")), json.dumps(updated.model_dump(mode="json")))).rowcount
                if inserted:
                    self._upsert_skill_state(conn, profile_id, updated)

    def save_skill_state(self, profile_id: str, state) -> None:
        with self.connect() as conn:
            self._upsert_skill_state(conn, profile_id, state)

    @staticmethod
    def _upsert_skill_state(conn, profile_id: str, state) -> None:
        conn.execute("""INSERT INTO tutor_state.skill_states
            (id, profile_id, skill_key, mastery_score, evidence_status, confidence,
             successful_attempts, failed_attempts, hints_required, last_seen,
             retrieval_due_at, declared_level, recurring_errors, policy_version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (profile_id,skill_key) DO UPDATE SET
             mastery_score=EXCLUDED.mastery_score, evidence_status=EXCLUDED.evidence_status,
             confidence=EXCLUDED.confidence, successful_attempts=EXCLUDED.successful_attempts,
             failed_attempts=EXCLUDED.failed_attempts, hints_required=EXCLUDED.hints_required,
             last_seen=EXCLUDED.last_seen, retrieval_due_at=EXCLUDED.retrieval_due_at,
             declared_level=EXCLUDED.declared_level, recurring_errors=EXCLUDED.recurring_errors,
             policy_version=EXCLUDED.policy_version""",
            (str(uuid.uuid4()), profile_id, state.skill_key, state.mastery_score,
             state.evidence_status, state.confidence, state.successful_attempts,
             state.failed_attempts, state.hints_required, state.last_seen,
             state.retrieval_due_at, state.declared_level,
             json.dumps(state.recurring_errors), state.policy_version))

    def operation_exists(self, action_id: str) -> bool:
        with self.connect() as conn:
            return conn.execute("SELECT 1 FROM tutor_state.operations WHERE action_id=%s", (action_id,)).fetchone() is not None

    def recover_operations(self, session_id: str) -> None:
        """Make operations from a crashed process retryable without replaying commits."""
        with self.connect() as conn:
            conn.execute("UPDATE tutor_state.operations SET status='pending', updated_at=now() WHERE session_id=%s AND status IN ('pending','running')", (session_id,))
            conn.execute("UPDATE tutor_state.operations SET status='stale', updated_at=now(), error_code='session_closed' WHERE session_id=%s AND status IN ('pending','running') AND EXISTS (SELECT 1 FROM tutor_state.learning_sessions s WHERE s.id=%s AND s.status='closed')", (session_id, session_id))

    def save_contract_and_run(self, session_id: str, contract: dict, content_hash: str) -> tuple[str, str]:
        contract_id, run_id = str(uuid.uuid4()), str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute("INSERT INTO tutor_state.exercise_contracts (id, exercise_id, version, contract_json, content_hash, source) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (exercise_id,version) DO NOTHING", (contract_id, contract["exercise_id"], contract["version"], json.dumps(contract), content_hash, "catalog"))
            row = conn.execute("SELECT id, content_hash FROM tutor_state.exercise_contracts WHERE exercise_id=%s AND version=%s", (contract["exercise_id"], contract["version"])).fetchone()
            if row[1] != content_hash:
                raise ValueError("An exercise contract version is immutable and has a different content hash")
            contract_id = str(row[0])
            conn.execute("INSERT INTO tutor_state.exercise_runs (id, session_id, contract_id, dataset_hash, context_tag, evidence_kind) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (run_id, session_id, contract_id, content_hash, contract["task"]["context_tag"], contract["task"]["evidence_kind"]))
            conn.execute("UPDATE tutor_state.learning_sessions SET current_run_id=%s, current_focus=%s, revision=revision+1 WHERE id=%s", (run_id, contract["task"]["primary_skill"], session_id))
            return contract_id, run_id

    def record_submission(self, session_id: str, run_id: str, sql_text: str | None, evaluation: dict, *, reasoning: str | None = None, hint_level: int = 0, action_id: str | None = None, profile_id: str | None = None, skill_state=None, updated_skill_state=None, skill_key: str | None = None, independent: bool = True) -> str:
        action_id = action_id or str(uuid.uuid4())
        payload = json.dumps({"sql": sql_text, "reasoning": reasoning})
        with self.connect() as conn:
            existing = conn.execute("SELECT action_id, payload_hash FROM tutor_state.operations WHERE action_id=%s", (action_id,)).fetchone()
            if existing:
                if existing[1] != hashlib.md5(payload.encode()).hexdigest():
                    raise ValueError("action_id was reused with a different payload")
                return str(existing[0])
            conn.execute("INSERT INTO tutor_state.operations (action_id, session_id, run_id, kind, payload_json, payload_hash, expected_revision, status) VALUES (%s,%s,%s,'submit',%s,md5(%s),0,'completed')", (action_id, session_id, run_id, payload, payload))
            submission_status = "pending_review" if evaluation["decision"] == "pending_review" else "finalized"
            finalized_at = None if submission_status == "pending_review" else "now()"
            if finalized_at:
                conn.execute("INSERT INTO tutor_state.submissions (operation_id, run_id, submitted_sql, reasoning, hint_level_at_submit, evaluation_json, status, feedback_status, finalized_at) VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',now())", (action_id, run_id, sql_text, reasoning, hint_level, json.dumps(evaluation), submission_status))
            else:
                conn.execute("INSERT INTO tutor_state.submissions (operation_id, run_id, submitted_sql, reasoning, hint_level_at_submit, evaluation_json, status, feedback_status, finalized_at) VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',NULL)", (action_id, run_id, sql_text, reasoning, hint_level, json.dumps(evaluation), submission_status))
            if evaluation["decision"] in {"correct", "partial", "incorrect", "learner_sql_error"}:
                conn.execute("UPDATE tutor_state.exercise_runs SET attempt_count=attempt_count+1, failed_count=failed_count+%s, state=%s, finalized_at=CASE WHEN %s THEN now() ELSE finalized_at END WHERE id=%s", (0 if evaluation["decision"] == "correct" else 1, "completed" if evaluation["decision"] == "correct" else "retry", evaluation["decision"] == "correct", run_id))
                conn.execute("""UPDATE tutor_state.learning_sessions
                    SET completed_count=completed_count+%s,
                        finalized_since_checkpoint=finalized_since_checkpoint+1,
                        revision=revision+1 WHERE id=%s""", (1 if evaluation["decision"] == "correct" else 0, session_id))
            if profile_id and skill_state is not None and updated_skill_state is not None and skill_key:
                self._upsert_skill_state(conn, profile_id, updated_skill_state)
                conn.execute("""INSERT INTO tutor_state.evidence_events
                    (id, submission_id, skill_key, result, independent, assisted,
                     before_state, after_state, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (submission_id, skill_key) DO NOTHING""",
                    (str(uuid.uuid4()), action_id, skill_key, evaluation["decision"],
                     independent, False,
                     json.dumps(skill_state.model_dump(mode="json")),
                     json.dumps(updated_skill_state.model_dump(mode="json")), "deterministic"))
                promotion = skill_state.evidence_status != updated_skill_state.evidence_status
            else:
                promotion = False
            session_row = conn.execute("SELECT finalized_since_checkpoint, learning_goal, current_focus, current_difficulty, revision FROM tutor_state.learning_sessions WHERE id=%s", (session_id,)).fetchone()
            if session_row and (session_row[0] >= 5 or promotion):
                snapshot = {"learning_goal": session_row[1], "current_focus": session_row[2], "current_difficulty": session_row[3], "revision": session_row[4], "run_id": run_id}
                reasons = ["five_finalized_runs"] if session_row[0] >= 5 else ["evidence_promotion"]
                conn.execute("""INSERT INTO tutor_state.checkpoints
                    (id, session_id, trigger_event_id, reasons, state_snapshot, summary)
                    VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (trigger_event_id) DO NOTHING""",
                    (str(uuid.uuid4()), session_id, action_id, json.dumps(reasons), json.dumps(snapshot), "Learning checkpoint created."))
                conn.execute("UPDATE tutor_state.learning_sessions SET finalized_since_checkpoint=0 WHERE id=%s", (session_id,))
            return action_id

    def pending_submission(self, run_id: str):
        with self.connect() as conn:
            return conn.execute("SELECT operation_id, submitted_sql, reasoning, evaluation_json FROM tutor_state.submissions WHERE run_id=%s AND status='pending_review' ORDER BY operation_id LIMIT 1", (run_id,)).fetchone()

    def finalize_review(self, session_id: str, run_id: str, submission_id: str, evaluation: dict, *, profile_id: str | None = None, skill_state=None, updated_skill_state=None, skill_key: str | None = None, independent: bool = True) -> None:
        with self.connect() as conn:
            row = conn.execute("SELECT status FROM tutor_state.submissions WHERE operation_id=%s AND run_id=%s FOR UPDATE", (submission_id, run_id)).fetchone()
            if not row:
                raise ValueError("The review submission does not exist for this run")
            if row[0] == "finalized":
                return
            if evaluation["decision"] == "pending_review":
                conn.execute("UPDATE tutor_state.submissions SET evaluation_json=%s WHERE operation_id=%s", (json.dumps(evaluation), submission_id))
                return
            conn.execute("UPDATE tutor_state.submissions SET evaluation_json=%s, status='finalized', feedback_status='pending', finalized_at=now() WHERE operation_id=%s", (json.dumps(evaluation), submission_id))
            if evaluation["decision"] in {"correct", "partial", "incorrect", "learner_sql_error"}:
                conn.execute("UPDATE tutor_state.exercise_runs SET attempt_count=attempt_count+1, failed_count=failed_count+%s, state=%s, finalized_at=CASE WHEN %s THEN now() ELSE finalized_at END WHERE id=%s", (0 if evaluation["decision"] == "correct" else 1, "completed" if evaluation["decision"] == "correct" else "retry", evaluation["decision"] == "correct", run_id))
                conn.execute("UPDATE tutor_state.learning_sessions SET completed_count=completed_count+%s, finalized_since_checkpoint=finalized_since_checkpoint+1, revision=revision+1 WHERE id=%s", (1 if evaluation["decision"] == "correct" else 0, session_id))
            if profile_id and skill_state is not None and updated_skill_state is not None and skill_key:
                self._upsert_skill_state(conn, profile_id, updated_skill_state)
                conn.execute("""INSERT INTO tutor_state.evidence_events
                    (id, submission_id, skill_key, result, independent, assisted,
                     before_state, after_state, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (submission_id, skill_key) DO NOTHING""",
                    (str(uuid.uuid4()), submission_id, skill_key, evaluation["decision"], independent, False,
                     json.dumps(skill_state.model_dump(mode="json")), json.dumps(updated_skill_state.model_dump(mode="json")), "rubric_llm"))

    def record_sql_run(self, session_id: str, run_id: str, sql_text: str, execution: dict, *, action_id: str | None = None) -> str:
        action_id = action_id or str(uuid.uuid4())
        payload = json.dumps({"sql": sql_text})
        with self.connect() as conn:
            existing = conn.execute("SELECT action_id, payload_hash FROM tutor_state.operations WHERE action_id=%s", (action_id,)).fetchone()
            if existing:
                if existing[1] != hashlib.md5(payload.encode()).hexdigest():
                    raise ValueError("action_id was reused with a different payload")
                return str(existing[0])
            conn.execute("INSERT INTO tutor_state.operations (action_id, session_id, run_id, kind, payload_json, payload_hash, expected_revision, status) VALUES (%s,%s,%s,'run_sql',%s,md5(%s),0,'completed')", (action_id, session_id, run_id, payload, payload))
            conn.execute("INSERT INTO tutor_state.sql_runs (operation_id, run_id, submitted_sql, executed_sql, execution_json) VALUES (%s,%s,%s,%s,%s)", (action_id, run_id, sql_text, execution.get("executed_sql"), json.dumps(execution)))
            return action_id

    def close_session(self, session_id: str) -> None:
        with self.connect() as conn:
            row = conn.execute("SELECT learning_goal, current_focus, current_difficulty, revision FROM tutor_state.learning_sessions WHERE id=%s AND status='active'", (session_id,)).fetchone()
            if not row:
                return
            trigger_id = str(uuid.uuid4())
            conn.execute("UPDATE tutor_state.learning_sessions SET status='closed', ended_at=now(), revision=revision+1 WHERE id=%s AND status='active'", (session_id,))
            conn.execute("""INSERT INTO tutor_state.checkpoints
                (id, session_id, trigger_event_id, reasons, state_snapshot, summary)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (trigger_event_id) DO NOTHING""",
                (str(uuid.uuid4()), session_id, trigger_id, json.dumps(["session_closed"]),
                 json.dumps({"learning_goal": row[0], "current_focus": row[1], "current_difficulty": row[2], "revision": row[3]}), "Session checkpoint."))

    def close_session_command(self, session_id: str, *, action_id: str | None = None) -> None:
        action_id = action_id or str(uuid.uuid4())
        payload = json.dumps({"session_id": session_id})
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM tutor_state.operations WHERE action_id=%s", (action_id,)).fetchone():
                return
            conn.execute("INSERT INTO tutor_state.operations (action_id, session_id, kind, payload_json, payload_hash, expected_revision, status) VALUES (%s,%s,'close_session',%s,md5(%s),0,'completed')", (action_id, session_id, payload, payload))
            row = conn.execute("SELECT learning_goal, current_focus, current_difficulty, revision FROM tutor_state.learning_sessions WHERE id=%s AND status='active'", (session_id,)).fetchone()
            if row:
                conn.execute("UPDATE tutor_state.learning_sessions SET status='closed', ended_at=now(), revision=revision+1 WHERE id=%s AND status='active'", (session_id,))
                conn.execute("INSERT INTO tutor_state.checkpoints (id, session_id, trigger_event_id, reasons, state_snapshot, summary) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (trigger_event_id) DO NOTHING", (str(uuid.uuid4()), session_id, action_id, json.dumps(["session_closed"]), json.dumps({"learning_goal": row[0], "current_focus": row[1], "current_difficulty": row[2], "revision": row[3]}), "Session checkpoint."))

    def set_goal(self, session_id: str, goal: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE tutor_state.learning_sessions SET learning_goal=%s, revision=revision+1 WHERE id=%s AND status='active'", (goal, session_id))

    def change_goal(self, profile_id: str, session_id: str, goal: str, mode: str = "FOCUSED_LEARNING") -> str:
        new_session_id = str(uuid.uuid4())
        with self.connect() as conn:
            old = conn.execute("SELECT learning_goal, current_focus, current_difficulty, revision FROM tutor_state.learning_sessions WHERE id=%s AND status='active'", (session_id,)).fetchone()
            if old:
                trigger_id = str(uuid.uuid4())
                conn.execute("""INSERT INTO tutor_state.checkpoints
                    (id, session_id, trigger_event_id, reasons, state_snapshot, summary)
                    VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (trigger_event_id) DO NOTHING""",
                    (str(uuid.uuid4()), session_id, trigger_id, json.dumps(["goal_changed"]),
                     json.dumps({"learning_goal": old[0], "current_focus": old[1], "current_difficulty": old[2], "revision": old[3]}), "Goal-change checkpoint."))
            conn.execute("UPDATE tutor_state.learning_sessions SET status='closed', ended_at=now(), revision=revision+1 WHERE id=%s AND status='active'", (session_id,))
            row = conn.execute("INSERT INTO tutor_state.learning_sessions (id, profile_id, learning_goal, mode) VALUES (%s,%s,%s,%s) RETURNING id", (new_session_id, profile_id, goal, mode)).fetchone()
            return str(row[0])

    def update_run(self, run_id: str, *, state: str | None = None, draft_sql: str | None = None, draft_reasoning: str | None = None) -> None:
        with self.connect() as conn:
            if state is not None:
                conn.execute("UPDATE tutor_state.exercise_runs SET state=%s, finalized_at=CASE WHEN %s IN ('skipped','revealed') THEN now() ELSE finalized_at END WHERE id=%s", (state, state, run_id))
            if draft_sql is not None or draft_reasoning is not None:
                conn.execute("UPDATE tutor_state.exercise_runs SET draft_sql=COALESCE(%s,draft_sql), draft_reasoning=COALESCE(%s,draft_reasoning) WHERE id=%s", (draft_sql, draft_reasoning, run_id))

    def save_draft(self, session_id: str, run_id: str, sql_text: str | None, reasoning: str | None = None, *, action_id: str | None = None) -> None:
        action_id = action_id or str(uuid.uuid4())
        payload = json.dumps({"sql": sql_text, "reasoning": reasoning})
        with self.connect() as conn:
            existing = conn.execute("SELECT payload_hash FROM tutor_state.operations WHERE action_id=%s", (action_id,)).fetchone()
            if existing:
                if existing[0] != hashlib.md5(payload.encode()).hexdigest():
                    raise ValueError("action_id was reused with a different draft")
                return
            conn.execute("INSERT INTO tutor_state.operations (action_id, session_id, run_id, kind, payload_json, payload_hash, expected_revision, status) VALUES (%s,%s,%s,'save_draft',%s,md5(%s),0,'completed')", (action_id, session_id, run_id, payload, payload))
            conn.execute("UPDATE tutor_state.exercise_runs SET draft_sql=%s, draft_reasoning=%s WHERE id=%s", (sql_text, reasoning, run_id))

    def reveal_solution(self, session_id: str, run_id: str, *, action_id: str | None = None) -> None:
        action_id = action_id or str(uuid.uuid4())
        payload = json.dumps({"run_id": run_id})
        with self.connect() as conn:
            existing = conn.execute("SELECT 1 FROM tutor_state.operations WHERE action_id=%s", (action_id,)).fetchone()
            if existing:
                return
            conn.execute("INSERT INTO tutor_state.operations (action_id, session_id, run_id, kind, payload_json, payload_hash, expected_revision, status) VALUES (%s,%s,%s,'reveal_solution',%s,md5(%s),0,'completed')", (action_id, session_id, run_id, payload, payload))
            conn.execute("UPDATE tutor_state.exercise_runs SET state='revealed', solution_revealed=true, finalized_at=now() WHERE id=%s AND state IN ('ready','awaiting_answer','retry')", (run_id,))

    def skip_run(self, session_id: str, run_id: str, *, action_id: str | None = None) -> None:
        action_id = action_id or str(uuid.uuid4())
        payload = json.dumps({"run_id": run_id})
        with self.connect() as conn:
            existing = conn.execute("SELECT 1 FROM tutor_state.operations WHERE action_id=%s", (action_id,)).fetchone()
            if existing:
                return
            conn.execute("INSERT INTO tutor_state.operations (action_id, session_id, run_id, kind, payload_json, payload_hash, expected_revision, status) VALUES (%s,%s,%s,'skip',%s,md5(%s),0,'completed')", (action_id, session_id, run_id, payload, payload))
            changed = conn.execute("UPDATE tutor_state.exercise_runs SET state='skipped', finalized_at=now() WHERE id=%s AND state IN ('ready','awaiting_answer','retry')", (run_id,)).rowcount
            if changed:
                conn.execute("UPDATE tutor_state.learning_sessions SET finalized_since_checkpoint=finalized_since_checkpoint+1, revision=revision+1 WHERE id=%s", (session_id,))

    def increment_hint(self, run_id: str, level: int, *, session_id: str | None = None, action_id: str | None = None) -> None:
        with self.connect() as conn:
            if session_id and action_id:
                payload = json.dumps({"level": level})
                existing = conn.execute("SELECT kind, payload_hash FROM tutor_state.operations WHERE action_id=%s", (action_id,)).fetchone()
                if existing:
                    if existing[0] != "hint" or existing[1] != __import__("hashlib").md5(payload.encode()).hexdigest():
                        raise ValueError("action_id was reused with a different operation")
                    return
                conn.execute("INSERT INTO tutor_state.operations (action_id, session_id, run_id, kind, payload_json, payload_hash, expected_revision, status) VALUES (%s,%s,%s,'hint',%s,md5(%s),0,'completed')", (action_id, session_id, run_id, payload, payload))
            conn.execute("UPDATE tutor_state.exercise_runs SET hint_level=GREATEST(hint_level,%s), hint_events=hint_events+1 WHERE id=%s", (level, run_id))

    def record_tutor_message(self, session_id: str, run_id: str | None, role: str, content: str, *, request_id: str | None = None, model_id: str | None = None) -> str:
        request_id = request_id or str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO tutor_state.tutor_messages
                   (id, session_id, run_id, request_id, role, content, model_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (request_id, role) DO NOTHING""",
                (str(uuid.uuid4()), session_id, run_id, request_id, role, content, model_id),
            )
        return request_id
