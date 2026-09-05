from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import ExecutionResult, ExerciseContract


ALLOWED_FUNCTIONS = {"count", "sum", "avg", "min", "max", "coalesce", "nullif", "abs", "round", "lower", "upper", "length", "substring", "date_trunc", "extract", "row_number", "rank", "dense_rank", "lag", "lead", "first_value", "last_value", "nth_value"}


class SQLBlocked(ValueError):
    pass


def validate_sql(sql: str, contract: ExerciseContract) -> None:
    if not sql or len(sql) > 20000:
        raise SQLBlocked("SQL is empty or exceeds SQL_MAX_CHARS.")
    if sql.count(";") > 1 or (";" in sql and not sql.rstrip().endswith(";")):
        raise SQLBlocked("Only one read-only SELECT statement is allowed.")
    try:
        from sqlglot import exp, parse
        statements = [item for item in parse(sql, read="postgres") if item is not None]
        if len(statements) != 1:
            raise SQLBlocked("Only one read-only SELECT statement is allowed.")
        statement = statements[0]
    except Exception as exc:
        raise SQLBlocked("SQL could not be parsed as PostgreSQL SELECT syntax.") from exc
    if not isinstance(statement, exp.Select) and not (isinstance(statement, exp.With) and statement.find(exp.Select)):
        raise SQLBlocked("Only SELECT statements are supported.")
    forbidden_nodes = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command, exp.Copy, exp.Lock, exp.Into)
    if any(statement.find(node) for node in forbidden_nodes) or statement.args.get("into"):
        raise SQLBlocked("Only one read-only SELECT statement is allowed.")
    names = {table.name.lower() for table in (contract.environment.tables if contract.environment else [])}
    cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        if table.db or table.catalog or table.name.lower() not in names | {name.lower() for name in cte_names}:
            raise SQLBlocked("The query references a table outside the exercise environment.")
    for function in statement.find_all(exp.Anonymous):
        if function.name.lower() not in ALLOWED_FUNCTIONS:
            raise SQLBlocked("The query uses a function outside the exercise allowlist.")


def validate_constraints(sql: str, contract: ExerciseContract) -> dict[str, str]:
    from sqlglot import exp, parse_one
    statement = parse_one(sql, read="postgres")
    output_select = statement if isinstance(statement, exp.Select) else statement.this if isinstance(getattr(statement, "this", None), exp.Select) else statement.find(exp.Select)
    table_names = {table.name.lower() for table in statement.find_all(exp.Table)}
    results: dict[str, str] = {}
    for constraint in contract.validation.constraints:
        passed = True
        if constraint.type == "uses_table":
            passed = bool(constraint.table and constraint.table.lower() in table_names)
        elif constraint.type == "grouped_aggregate":
            selected = list(output_select.expressions) if output_select else []
            target = [expr for expr in selected if getattr(expr, "alias", "").lower() == (constraint.output_alias or "").lower()]
            aggregates = [node for expr in target for node in expr.walk() if isinstance(node, exp.AggFunc) and node.sql_name().lower() == (constraint.function or "").lower() and not node.find(exp.Window)]
            group = output_select.args.get("group") if output_select else None
            group_sql = {item.this.sql(dialect="postgres") for item in (group.expressions if group else [])}
            expected = {value.split(".")[-1] for value in (constraint.group_by or [])}
            passed = bool(aggregates) and expected.issubset({value.split(".")[-1] for value in group_sql})
        elif constraint.type == "window_function":
            selected = list(output_select.expressions) if output_select else []
            target = [expr for expr in selected if getattr(expr, "alias", "").lower() == (constraint.output_alias or "").lower()]
            passed = any(isinstance(node, exp.Window) and (not constraint.function or node.this.sql_name().lower() == constraint.function.lower()) for expr in target for node in expr.walk())
        elif constraint.type == "recursive_cte":
            with_clause = statement.args.get("with")
            passed = bool(with_clause and with_clause.args.get("recursive") and (not constraint.cte_name or any(cte.alias_or_name == constraint.cte_name for cte in with_clause.expressions)))
        results[constraint.id] = "pass" if passed else "fail"
    return results


def dataset_hash(contract: ExerciseContract, hidden: bool) -> str:
    rows = contract.environment.hidden_data if hidden else contract.environment.visible_data
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


class Database:
    def __init__(self, app_url: str, runner_url: str, evaluator_url: str, *, timeout_ms: int = 3000, lock_timeout_ms: int = 1000, max_chars: int = 20000, row_limit: int = 2000, byte_limit: int = 2097152):
        self.app_url, self.runner_url, self.evaluator_url = app_url, runner_url, evaluator_url
        self.timeout_ms, self.lock_timeout_ms, self.max_chars, self.row_limit, self.byte_limit = timeout_ms, lock_timeout_ms, max_chars, row_limit, byte_limit

    def execute(self, contract: ExerciseContract, sql: str, *, hidden: bool = False, preview_limit: int | None = None) -> ExecutionResult:
        if len(sql or "") > self.max_chars:
            return ExecutionResult(status="blocked", submitted_sql=sql, safe_error="SQL exceeds SQL_MAX_CHARS.", failure_kind="unsupported_capability")
        from .dialects import normalize_sql
        normalized = normalize_sql(sql, contract)
        try:
            validate_sql(normalized.executed_sql, contract)
        except SQLBlocked:
            raise
        try:
            import psycopg
        except ImportError as exc:
            return ExecutionResult(status="inconclusive", submitted_sql=sql, safe_error="PostgreSQL driver is not installed.", failure_kind="environment_error")
        url = self.evaluator_url if hidden else self.runner_url
        try:
            with psycopg.connect(url) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_xact_lock(2147483647)")
                    cur.execute("SET TRANSACTION READ ONLY")
                    cur.execute(f"SET LOCAL statement_timeout = {int(self.timeout_ms)}")
                    cur.execute(f"SET LOCAL lock_timeout = {int(self.lock_timeout_ms)}")
                    schema = "exercise_validation" if hidden else "exercise"
                    cur.execute(f"SET LOCAL search_path = {schema}, pg_catalog")
                    cur.execute(normalized.executed_sql)
                    columns = [{"name": d.name, "type": "unknown"} for d in cur.description or []]
                    rows = cur.fetchmany((preview_limit or self.row_limit) + 1)
                    if sum(len(repr(row).encode("utf-8")) for row in rows) > self.byte_limit:
                        return ExecutionResult(status="inconclusive", submitted_sql=sql, executed_sql=normalized.executed_sql, extension_ids=normalized.extension_ids, safe_error="Result byte limit exceeded.", failure_kind="limit_exceeded", dataset_hash=dataset_hash(contract, hidden))
                    truncated = len(rows) > (preview_limit or self.row_limit)
                    rows = rows[: preview_limit or self.row_limit]
                    return ExecutionResult(status="ok", submitted_sql=sql, executed_sql=normalized.executed_sql, extension_ids=normalized.extension_ids, columns=columns, preview_rows=[list(row) for row in rows], preview_truncated=truncated, total_row_count=None if truncated else len(rows), complete=not truncated, dataset_hash=dataset_hash(contract, hidden))
        except SQLBlocked:
            raise
        except Exception as exc:
            failure = "learner_sql_error"
            try:
                import psycopg
                if isinstance(exc, psycopg.OperationalError):
                    failure = "environment_error"
                elif isinstance(exc, psycopg.errors.QueryCanceled):
                    failure = "timeout"
                elif isinstance(exc, psycopg.errors.InsufficientPrivilege):
                    failure = "permission_error"
            except ImportError:
                failure = "environment_error"
            sqlstate = getattr(exc, "sqlstate", None)
            safe_error = "SQL execution failed." if failure != "learner_sql_error" else str(exc).splitlines()[0][:500]
            return ExecutionResult(status="error", submitted_sql=sql, sqlstate=sqlstate, safe_error=safe_error, failure_kind=failure)

    def explain(self, contract: ExerciseContract, sql: str, *, hidden: bool = False) -> ExecutionResult:
        from .dialects import normalize_sql
        normalized = normalize_sql(sql, contract)
        validate_sql(normalized.executed_sql, contract)
        import psycopg
        url = self.evaluator_url if hidden else self.runner_url
        try:
            with psycopg.connect(url) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_xact_lock(2147483647)")
                    cur.execute("SET TRANSACTION READ ONLY")
                    cur.execute("SET LOCAL statement_timeout = %s" % int(self.timeout_ms))
                    cur.execute("SET LOCAL search_path = %s, pg_catalog" % ("exercise_validation" if hidden else "exercise"))
                    cur.execute("EXPLAIN (FORMAT JSON) " + normalized.executed_sql)
                    row = cur.fetchone()
                    plan = row[0] if row else None
                    return ExecutionResult(status="ok", submitted_sql=sql, executed_sql=normalized.executed_sql, extension_ids=normalized.extension_ids, complete=True, plan_json=plan, dataset_hash=dataset_hash(contract, hidden))
        except Exception as exc:
            import psycopg
            failure = "environment_error" if isinstance(exc, psycopg.OperationalError) else "permission_error" if isinstance(exc, psycopg.errors.InsufficientPrivilege) else "timeout" if isinstance(exc, psycopg.errors.QueryCanceled) else "learner_sql_error"
            return ExecutionResult(status="error", submitted_sql=sql, sqlstate=getattr(exc, "sqlstate", None), safe_error=str(exc).splitlines()[0][:500], failure_kind=failure)
