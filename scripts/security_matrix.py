"""Run the PostgreSQL security boundary checks for the local MVP."""

from __future__ import annotations

import sys
from pathlib import Path

from sql_tutor.config import ConfigurationError, Settings
from sql_tutor.database import Database, SQLBlocked, validate_sql
from sql_tutor.exercises import example_contract


def _query(url: str, sql: str) -> bool:
    import psycopg

    try:
        with psycopg.connect(url) as conn:
            conn.execute(sql).fetchone()
        return True
    except Exception:
        return False


def _check_role(name: str, url: str, allowed: list[str], denied: list[str]) -> list[str]:
    failures = []
    for sql in allowed:
        if not _query(url, sql):
            failures.append(f"{name} should allow: {sql}")
    for sql in denied:
        if _query(url, sql):
            failures.append(f"{name} should deny: {sql}")
    return failures


def main() -> int:
    try:
        settings = Settings.from_env(Path(".env"), require_admin=False)
    except ConfigurationError as exc:
        print(f"configuration unavailable: {exc}")
        return 2

    failures: list[str] = []
    failures += _check_role(
        "app",
        settings.database_app_url,
        [
            "SELECT 1 FROM tutor_state.student_profiles LIMIT 1",
            "SELECT 1 FROM exercise.sales LIMIT 1",
            "SELECT 1 FROM exercise_validation.sales LIMIT 1",
        ],
        [],
    )
    failures += _check_role(
        "runner",
        settings.database_runner_url,
        ["SELECT 1 FROM exercise.sales LIMIT 1"],
        ["SELECT 1 FROM tutor_state.student_profiles LIMIT 1", "SELECT 1 FROM exercise_validation.sales LIMIT 1"],
    )
    failures += _check_role(
        "evaluator",
        settings.database_evaluator_url,
        ["SELECT 1 FROM exercise.sales LIMIT 1", "SELECT 1 FROM exercise_validation.sales LIMIT 1"],
        ["SELECT 1 FROM tutor_state.student_profiles LIMIT 1"],
    )

    contract = example_contract()
    for query in (
        "SELECT * FROM tutor_state.student_profiles",
        "SELECT pg_sleep(1)",
        "WITH changed AS (DELETE FROM sales RETURNING sale_id) SELECT * FROM changed",
        "SELECT * INTO copied_sales FROM sales",
        "SELECT 1; SELECT 2",
    ):
        try:
            validate_sql(query, contract)
        except SQLBlocked:
            continue
        failures.append(f"AST should block: {query}")

    database = Database(
        settings.database_app_url,
        settings.database_runner_url,
        settings.database_evaluator_url,
        timeout_ms=settings.sql_timeout_ms,
        lock_timeout_ms=settings.sql_lock_timeout_ms,
        max_chars=settings.sql_max_chars,
        row_limit=settings.evaluation_row_limit,
        byte_limit=settings.result_byte_limit,
    )
    visible = database.execute(contract, "SELECT customer_id, SUM(amount) AS total_sales FROM sales GROUP BY customer_id")
    hidden = database.execute(contract, "SELECT customer_id, SUM(amount) AS total_sales FROM sales GROUP BY customer_id", hidden=True)
    if visible.status != "ok" or not visible.complete:
        failures.append(f"visible runner execution failed: {visible.failure_kind or visible.status}")
    if hidden.status != "ok" or not hidden.complete:
        failures.append(f"hidden evaluator execution failed: {hidden.failure_kind or hidden.status}")

    if failures:
        print("security matrix: FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("security matrix: PASSED")
    print("- app provisioning ownership and restricted role grants/denials: ok")
    print("- AST mutation/schema/function/multi-statement blocks: ok")
    print("- visible runner and hidden evaluator execution: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
