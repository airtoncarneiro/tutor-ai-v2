"""Validate one real adaptive transition in an isolated temporary database."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from sql_tutor.application import TutorApplication
from sql_tutor.config import ConfigurationError, Settings
from sql_tutor.exercises import contract_hash
from sql_tutor.repositories import Repository


def _database_url(url: str, database: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{database}", parsed.query, parsed.fragment))


def _bootstrap_database(admin_url: str, database: str, app_role: str, runner_role: str, evaluator_role: str) -> None:
    import psycopg
    from psycopg import sql

    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database)))
    database_url = _database_url(admin_url, database)
    Repository(database_url, database_url).migrate("migrations/001_initial.sql")
    with psycopg.connect(database_url) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA exercise AUTHORIZATION {}" ).format(sql.Identifier(app_role)))
        conn.execute(sql.SQL("CREATE SCHEMA exercise_validation AUTHORIZATION {}" ).format(sql.Identifier(app_role)))
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}, {}").format(sql.Identifier(database), sql.Identifier(app_role), sql.Identifier(runner_role), sql.Identifier(evaluator_role)))
        conn.execute("REVOKE ALL ON SCHEMA public, tutor_state, exercise, exercise_validation FROM PUBLIC")
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA tutor_state TO {}" ).format(sql.Identifier(app_role)))
        conn.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA tutor_state TO {}" ).format(sql.Identifier(app_role)))
        conn.execute(sql.SQL("GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA tutor_state TO {}" ).format(sql.Identifier(app_role)))
        conn.execute(sql.SQL("GRANT USAGE, CREATE ON SCHEMA exercise, exercise_validation TO {}" ).format(sql.Identifier(app_role)))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA exercise TO {}, {}" ).format(sql.Identifier(runner_role), sql.Identifier(evaluator_role)))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA exercise_validation TO {}" ).format(sql.Identifier(evaluator_role)))
        conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA tutor_state GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}" ).format(sql.Identifier(app_role)))
        conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA tutor_state GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {}" ).format(sql.Identifier(app_role)))
        conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA exercise GRANT SELECT ON TABLES TO {}, {}" ).format(sql.Identifier(app_role), sql.Identifier(runner_role), sql.Identifier(evaluator_role)))
        conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA exercise_validation GRANT SELECT ON TABLES TO {}" ).format(sql.Identifier(app_role), sql.Identifier(evaluator_role)))
        conn.commit()


def main() -> int:
    try:
        settings = Settings.from_env(Path(".env"), require_admin=True)
    except ConfigurationError as exc:
        print(f"configuration unavailable: {exc}")
        return 2
    if not settings.llm_base_url or not settings.llm_model:
        print("adaptive smoke pending: LLM_MODEL and LLM_BASE_URL are required")
        return 2

    import psycopg
    from psycopg import sql

    database = f"sql_tutor_adaptive_{uuid.uuid4().hex[:10]}"
    admin_url = settings.database_admin_url
    if not admin_url:
        print("adaptive smoke pending: DATABASE_ADMIN_URL is required")
        return 2
    app_role = urlsplit(settings.database_app_url).username
    runner_role = urlsplit(settings.database_runner_url).username
    evaluator_role = urlsplit(settings.database_evaluator_url).username
    if not all((app_role, runner_role, evaluator_role)):
        print("adaptive smoke pending: restricted role names are missing from database URLs")
        return 2

    database_url = _database_url(admin_url, database)
    try:
        _bootstrap_database(admin_url, database, app_role, runner_role, evaluator_role)
        temp_settings = Settings(
            database_app_url=_database_url(settings.database_app_url, database),
            database_runner_url=_database_url(settings.database_runner_url, database),
            database_evaluator_url=_database_url(settings.database_evaluator_url, database),
            database_admin_url=database_url,
            llm_base_url=settings.llm_base_url,
            llm_model=settings.llm_model,
            llm_api_key=settings.llm_api_key,
            llm_timeout_seconds=min(settings.llm_timeout_seconds, 10),
            llm_max_attempts=1,
            sql_timeout_ms=settings.sql_timeout_ms,
            sql_lock_timeout_ms=settings.sql_lock_timeout_ms,
            sql_max_chars=settings.sql_max_chars,
            display_row_limit=settings.display_row_limit,
            evaluation_row_limit=settings.evaluation_row_limit,
            result_byte_limit=settings.result_byte_limit,
            streamlit_server_address=settings.streamlit_server_address,
        )
        app = TutorApplication(temp_settings)
        app.initialize("Learn SQL aggregation", "FOCUSED_LEARNING")
        old_run_id = app.run_id
        old_hash = contract_hash(app.contract)
        evaluation = app.submit_response("SELECT customer_id, SUM(amount) AS total_sales FROM sales GROUP BY customer_id")
        if evaluation[1].decision != "correct":
            raise RuntimeError(f"initial submission was not correct: {evaluation[1].decision}")
        app.next_exercise()
        new_hash = contract_hash(app.contract)
        if app.run_id == old_run_id or new_hash == old_hash:
            raise RuntimeError("adaptive transition did not create an independent next contract/run")
        print("adaptive smoke: PASSED")
        print(f"- initial exercise: {old_run_id}")
        print(f"- submission: correct")
        print(f"- next exercise: {app.contract.exercise_id}")
        print(f"- next evidence kind: {app.contract.task.evidence_kind.value}")
        return 0
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid <> pg_backend_pid()", (database,))
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}" ).format(sql.Identifier(database)))


if __name__ == "__main__":
    sys.exit(main())
