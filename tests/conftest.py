from __future__ import annotations

import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from sql_tutor.config import Settings
from sql_tutor.exercises import example_contract
from sql_tutor.models import EvaluationResult, ExecutionResult


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def contract_factory():
    """Return a valid v2 payload with one requested mutation."""

    def make(
        *,
        valid: bool = True,
        extra_fields: bool = False,
        enum_invalid: bool = False,
        type_mismatch: bool = False,
        unsupported_skill: bool = False,
        invalid_combo: bool = False,
        alias_optional: bool = False,
    ):
        contract = example_contract().model_dump(mode="json")
        if alias_optional:
            contract["validation"]["constraints"][0].pop("output_alias", None)
        if extra_fields:
            contract["unexpected"] = "value"
        if enum_invalid:
            contract["task"]["response_mode"] = "UNKNOWN_MODE"
        if type_mismatch:
            contract["exercise_id"] = 123
        if unsupported_skill:
            contract["task"]["primary_skill"] = "nonexistent"
        if invalid_combo:
            contract["task"]["response_mode"] = "SQL_ONLY"
            contract["validation"]["mode"] = "EXPLANATION"
        if not valid:
            contract.pop("exercise_id", None)
        return contract

    return make


class UITutorRepoDouble:
    def ensure_profile(self):
        return "00000000-0000-0000-0000-000000000001"

    def active_session(self, profile_id):
        return ("00000000-0000-0000-0000-000000000002", "Learn SQL", "FOCUSED_LEARNING", 0)

    def current_run_exists(self, session_id):
        return True


class UITutorDouble:
    """Stateful UI double; it never opens PostgreSQL or calls an LLM API."""

    def __init__(self, contract, *, submit_decision: str = "correct"):
        self.repo = UITutorRepoDouble()
        self.contract = contract
        self.submit_decision = submit_decision
        self.skill_states = []
        self.evidence_events = []
        self.evidence_details = []
        self.run_snapshot = {"draft_sql": ""}
        self.hint_level = 0
        self.failed_count = 0
        self.last_feedback = None
        self.calls: list[tuple] = []

    def initialize(self, goal, mode, declaration=None):
        self.calls.append(("initialize", goal, mode, declaration))

    def run_sql(self, sql, *, action_id=None):
        self.calls.append(("run_sql", sql, action_id))
        return ExecutionResult(
            status="ok",
            submitted_sql=sql,
            executed_sql=sql,
            columns=[{"name": "customer_id", "type": "integer"}, {"name": "total", "type": "numeric"}],
            preview_rows=[[101, 800]],
            total_row_count=1,
            complete=True,
        )

    def submit_response(self, response, reasoning=None, *, action_id=None):
        self.calls.append(("submit_response", response, reasoning, action_id))
        execution = self.run_sql(response, action_id=action_id) if self.contract.task.response_mode.value != "EXPLANATION_ONLY" else None
        score = 1 if self.submit_decision == "correct" else None
        evaluation = EvaluationResult(
            decision=self.submit_decision,
            score=score,
            execution_status="ok" if execution else "not_required",
            primary_skill_affected=self.submit_decision == "correct",
        )
        self.last_feedback = {"message": "Deterministic tutor feedback."}
        return execution, evaluation

    def hint(self, current_level=0, *, action_id=None):
        self.calls.append(("hint", current_level, action_id))
        self.hint_level = max(self.hint_level, current_level + 1)
        return {"message": "Deterministic hint.", "hint_level": self.hint_level}

    def chat(self, message):
        self.calls.append(("chat", message))
        return {"message": "Deterministic chat response."}

    def show_solution(self, failed_count, hint_level, *, action_id=None):
        self.calls.append(("show_solution", failed_count, hint_level, action_id))
        return {"reference_sql": self.contract.private.reference_sql, "explanation": self.contract.private.solution_explanation}

    def change_goal(self, goal):
        self.calls.append(("change_goal", goal))

    def close(self, *, action_id=None):
        self.calls.append(("close", action_id))

    def summarize(self):
        self.calls.append(("summarize",))
        return {"message": "Deterministic session summary."}

    def next_exercise(self):
        self.calls.append(("next_exercise",))

    def save_draft(self, response, reasoning=None, *, action_id=None):
        self.calls.append(("save_draft", response, reasoning, action_id))

    def skip(self, *, action_id=None):
        self.calls.append(("skip", action_id))

    def retry_review(self):
        self.calls.append(("retry_review",))
        return EvaluationResult(decision="correct", score=1, execution_status="ok", primary_skill_affected=True)


@pytest.fixture
def app_test_factory():
    """Build an AppTest with deterministic settings and tutor dependencies."""
    from streamlit.testing.v1 import AppTest
    from sql_tutor import ui_runtime

    def make(contract=None, *, submit_decision="correct"):
        tutor = UITutorDouble(contract or example_contract(), submit_decision=submit_decision)
        settings = Settings(
            "postgresql://unused/app",
            "postgresql://unused/runner",
            "postgresql://unused/evaluator",
            None,
            None,
            None,
            None,
        )
        ui_runtime.configure_for_tests(
            settings_factory=lambda _: settings,
            tutor_factory=lambda _: tutor,
        )
        return AppTest.from_file(ROOT / "sql_tutor" / "app.py"), tutor

    yield make
    ui_runtime.reset_factories()


@pytest.fixture
def postgres_settings():
    """Start an isolated PostgreSQL container for opt-in integration tests."""
    if os.getenv("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("set RUN_POSTGRES_TESTS=1 to run disposable PostgreSQL tests")

    container = f"tutor-ai-v2-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    image = os.getenv("TEST_POSTGRES_IMAGE", "postgres:17.6-alpine")
    database = "tutor_test"
    owner_password = "test-owner-password"
    app_password = "test-app-password"
    runner_password = "test-runner-password"
    evaluator_password = "test-evaluator-password"
    init_dir = ROOT / "docker" / "postgres" / "init"
    command = [
        "docker", "run", "--detach", "--rm", "--name", container,
        "--publish", "127.0.0.1::5432",
        "--env", f"POSTGRES_DB={database}",
        "--env", "POSTGRES_USER=tutor_owner",
        "--env", f"POSTGRES_PASSWORD={owner_password}",
        "--env", f"TUTOR_APP_PASSWORD={app_password}",
        "--env", f"TUTOR_RUNNER_PASSWORD={runner_password}",
        "--env", f"TUTOR_EVALUATOR_PASSWORD={evaluator_password}",
        "--volume", f"{init_dir}:/docker-entrypoint-initdb.d:ro",
        image,
    ]
    started = subprocess.run(command, check=True, capture_output=True, text=True)
    assert started.stdout.strip()
    try:
        port_output = subprocess.run(
            ["docker", "port", container, "5432/tcp"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        port = int(port_output.rsplit(":", 1)[1])

        def url(user, password):
            return f"postgresql://{user}:{password}@127.0.0.1:{port}/{database}"

        import psycopg

        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                with psycopg.connect(url("tutor_owner", owner_password), connect_timeout=1):
                    break
            except psycopg.OperationalError:
                time.sleep(0.25)
        else:
            pytest.fail("disposable PostgreSQL did not accept an owner connection")

        settings = Settings(
            url("tutor_app", app_password),
            url("tutor_runner", runner_password),
            url("tutor_evaluator", evaluator_password),
            url("tutor_owner", owner_password),
            None,
            None,
            None,
        )
        from sql_tutor.repositories import Repository

        Repository(settings.database_app_url, settings.database_admin_url).migrate(str(ROOT / "migrations" / "001_initial.sql"))
        yield settings
    finally:
        subprocess.run(["docker", "rm", "--force", container], capture_output=True)
