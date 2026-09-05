from __future__ import annotations

from psycopg import sql

from .models import ExerciseContract


class ProvisionError(RuntimeError):
    pass


def provision(contract: ExerciseContract, app_url: str) -> None:
    """Compile only validated contract data into fixed schemas."""
    if contract.environment is None:
        return
    with __import__("psycopg").connect(app_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(2147483647)")
            declared_tables = {table.name for table in contract.environment.tables}
            for schema, dataset in (("exercise", contract.environment.visible_data), ("exercise_validation", contract.environment.hidden_data)):
                # A preparação é uma publicação de ambiente, não um merge. Remova
                # tabelas de um contrato anterior para que nenhum objeto antigo
                # permaneça observável durante a execução do novo exercício.
                cur.execute("SELECT tablename FROM pg_tables WHERE schemaname=%s", (schema,))
                for (old_table,) in cur.fetchall():
                    if old_table not in declared_tables:
                        cur.execute(sql.SQL("DROP TABLE IF EXISTS {}.{} CASCADE").format(sql.Identifier(schema), sql.Identifier(old_table)))
                for table in contract.environment.tables:
                    cur.execute(sql.SQL("DROP TABLE IF EXISTS {}.{} CASCADE").format(sql.Identifier(schema), sql.Identifier(table.name)))
                    cols = []
                    for column in table.columns:
                        typ = {"integer": "integer", "bigint": "bigint", "numeric": "numeric(18,2)", "text": "text", "boolean": "boolean", "date": "date"}[column.type]
                        cols.append(sql.SQL("{} {} {}").format(sql.Identifier(column.name), sql.SQL(typ), sql.SQL("" if column.nullable else "NOT NULL")))
                    if table.primary_key:
                        cols.append(sql.SQL("PRIMARY KEY ({})").format(sql.SQL(", ").join(map(sql.Identifier, table.primary_key))))
                    cur.execute(sql.SQL("CREATE TABLE {}.{} ({})").format(sql.Identifier(schema), sql.Identifier(table.name), sql.SQL(", ").join(cols)))
                    for index in table.indexes:
                        cur.execute(sql.SQL("CREATE INDEX {} ON {}.{} ({})").format(
                            sql.Identifier(index.name), sql.Identifier(schema),
                            sql.Identifier(table.name), sql.SQL(", ").join(map(sql.Identifier, index.columns))))
                    rows = dataset[table.name]
                    if rows:
                        placeholders = sql.SQL(",").join(sql.Placeholder() for _ in table.columns)
                        cur.executemany(sql.SQL("INSERT INTO {}.{} VALUES ({})").format(sql.Identifier(schema), sql.Identifier(table.name), placeholders), rows)
                    # Reapply grants after every table replacement; ownership alone must not
                    # be the mechanism that makes restricted execution work.
                    if schema == "exercise":
                        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA exercise TO tutor_runner, tutor_evaluator"))
                        cur.execute(sql.SQL("GRANT SELECT ON {}.{} TO tutor_runner, tutor_evaluator").format(sql.Identifier(schema), sql.Identifier(table.name)))
                    else:
                        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA exercise_validation TO tutor_evaluator"))
                        cur.execute(sql.SQL("GRANT SELECT ON {}.{} TO tutor_evaluator").format(sql.Identifier(schema), sql.Identifier(table.name)))
            # Validate the private reference before committing the replacement.  The
            # transaction is still open, so any failure rolls back and preserves the
            # previously published environment.
            if contract.validation.mode.value == "RESULT_EQUIVALENCE":
                from .evaluator import compare_rows
                from decimal import Decimal
                for schema, expected in (("exercise", contract.private.expected_visible_rows), ("exercise_validation", contract.private.expected_hidden_rows)):
                    cur.execute("SET LOCAL ROLE tutor_evaluator")
                    cur.execute(sql.SQL("SET LOCAL search_path = {}, pg_catalog").format(sql.Identifier(schema)))
                    cur.execute(contract.private.reference_sql)
                    columns = [description.name for description in (cur.description or [])]
                    expected_columns = [column.name for column in contract.validation.output_columns]
                    if columns != expected_columns:
                        raise ProvisionError("Reference SQL output columns do not match the declared contract")
                    actual = [list(row) for row in cur.fetchall()]
                    typed_expected = []
                    for row in expected:
                        typed_expected.append([Decimal(value) if value is not None and column.type == "numeric" and isinstance(value, str) else value for value, column in zip(row, contract.validation.output_columns)])
                    if not compare_rows(actual, typed_expected, contract.validation.order_sensitive):
                        raise ProvisionError(f"Reference SQL does not match expected {schema} rows")
                    cur.execute("RESET ROLE")
            conn.commit()
