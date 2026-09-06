"""Opt-in lifecycle coverage against a disposable PostgreSQL instance."""

from __future__ import annotations

from copy import deepcopy
import uuid

import pytest

from sql_tutor.application import TutorApplication
from sql_tutor.exercises import contract_hash, validate_contract
from sql_tutor.llm import FakeLLM


pytestmark = pytest.mark.postgres


def _count(app: TutorApplication, table: str) -> int:
    allowed = {"sql_runs", "submissions", "evidence_events"}
    assert table in allowed
    with app.repo.connect() as conn:
        return int(conn.execute(f"SELECT count(*) FROM tutor_state.{table}").fetchone()[0])


def test_real_postgres_lifecycle_is_idempotent_and_contracts_are_immutable(postgres_settings):
    app = TutorApplication(postgres_settings, llm=FakeLLM())
    app.initialize("Learn SQL aggregation")
    sql = "SELECT customer_id, SUM(amount) AS total_sales FROM sales GROUP BY customer_id"

    run_action = str(uuid.uuid4())
    run_result = app.run_sql(sql, action_id=run_action)
    assert run_result.status == "ok"
    assert _count(app, "sql_runs") == 1
    assert _count(app, "submissions") == 0
    assert _count(app, "evidence_events") == 0

    # Replaying the same command is safe; reusing its id for other input is not.
    app.run_sql(sql, action_id=run_action)
    assert _count(app, "sql_runs") == 1
    with pytest.raises(ValueError, match="different payload"):
        app.run_sql("SELECT 1", action_id=run_action)

    draft_action = str(uuid.uuid4())
    app.save_draft(sql, "draft rationale", action_id=draft_action)
    app.save_draft(sql, "draft rationale", action_id=draft_action)
    with pytest.raises(ValueError, match="different draft"):
        app.save_draft("SELECT 1", action_id=draft_action)

    session_id, run_id, profile_id = app.session_id, app.run_id, app.profile_id
    resumed = TutorApplication(postgres_settings, llm=FakeLLM())
    resumed.initialize("Learn SQL aggregation")
    assert (resumed.session_id, resumed.run_id, resumed.profile_id) == (
        session_id,
        run_id,
        profile_id,
    )
    assert resumed.run_snapshot["draft_sql"] == sql
    assert resumed.run_snapshot["draft_reasoning"] == "draft rationale"
    app = resumed

    submit_action = str(uuid.uuid4())
    _, evaluation = app.submit_response(sql, action_id=submit_action)
    assert evaluation.decision == "correct"
    assert _count(app, "sql_runs") == 1
    assert _count(app, "submissions") == 1
    assert _count(app, "evidence_events") == 1
    assert app.repo.run_attempt_count(app.run_id) == 1

    app.submit_response(sql, action_id=submit_action)
    assert _count(app, "submissions") == 1
    assert _count(app, "evidence_events") == 1
    assert app.repo.run_attempt_count(app.run_id) == 1
    with pytest.raises(ValueError, match="different payload"):
        app.submit_response("SELECT 1", action_id=submit_action)

    original = app.contract.model_dump(mode="json")
    same_contract = validate_contract(deepcopy(original))
    _, _, persisted_same, _ = app.repo.save_contract_and_run(
        app.session_id,
        deepcopy(original),
        contract_hash(same_contract),
    )
    assert persisted_same["version"] == original["version"]

    changed = deepcopy(original)
    changed["task"]["title"] = "Sales totals by customer, revised"
    changed_contract = validate_contract(changed)
    _, _, persisted, _ = app.repo.save_contract_and_run(
        app.session_id,
        changed,
        contract_hash(changed_contract),
    )

    assert persisted["version"] == original["version"] + 1
    with app.repo.connect() as conn:
        versions = conn.execute(
            """SELECT version, contract_json->'task'->>'title'
               FROM tutor_state.exercise_contracts
               WHERE exercise_id=%s
               ORDER BY version""",
            (original["exercise_id"],),
        ).fetchall()
    assert versions == [
        (original["version"], original["task"]["title"]),
        (original["version"] + 1, changed["task"]["title"]),
    ]
