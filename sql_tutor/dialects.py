from __future__ import annotations

from dataclasses import dataclass

from .models import ExerciseContract


@dataclass(frozen=True)
class NormalizedSQL:
    submitted_sql: str
    executed_sql: str
    extension_ids: list[str]
    note: str | None = None


def normalize_sql(sql: str, contract: ExerciseContract) -> NormalizedSQL:
    """Normalize only the two registered Redshift alias extensions.

    PostgreSQL-native SQL is returned byte-for-byte unchanged.  We only expand
    an unqualified alias when it is defined before use and no input column has
    the same name; this makes collisions conservative and auditable.
    """
    try:
        from sqlglot import exp, parse_one
        statement = parse_one(sql, read="postgres")
    except Exception:
        return NormalizedSQL(sql, sql, [])
    select = statement if isinstance(statement, exp.Select) else getattr(statement, "this", None)
    if not isinstance(select, exp.Select):
        return NormalizedSQL(sql, sql, [])
    input_columns = {column.name.lower() for table in (contract.environment.tables if contract.environment else []) for column in table.columns}
    aliases: dict[str, exp.Expression] = {}
    extension_ids: list[str] = []

    def expand(expression: exp.Expression, available: dict[str, exp.Expression]) -> exp.Expression:
        def replace(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Column) and not node.table and node.name.lower() in available and node.name.lower() not in input_columns:
                return available[node.name.lower()].copy()
            return node
        return expression.transform(replace, copy=True)

    expressions = list(select.expressions)
    rewritten = []
    for expression in expressions:
        alias = expression.alias.lower() if isinstance(expression, exp.Alias) and expression.alias else ""
        body = expression.this if isinstance(expression, exp.Alias) else expression
        updated = expand(body, aliases)
        if updated.sql(dialect="postgres") != body.sql(dialect="postgres"):
            extension_ids.append("redshift.lateral_alias_reference")
        if isinstance(expression, exp.Alias):
            rewritten.append(exp.alias_(updated, expression.alias, quoted=expression.args.get("quoted", False)))
        else:
            rewritten.append(updated)
        if alias:
            aliases[alias] = updated
    select.set("expressions", rewritten)
    having = select.args.get("having")
    if having and aliases:
        updated_having = expand(having, aliases)
        if updated_having.sql(dialect="postgres") != having.sql(dialect="postgres"):
            extension_ids.append("redshift.having_alias_reference")
            select.set("having", updated_having)
    if not extension_ids:
        return NormalizedSQL(sql, sql, [])
    # Preserve ordering and uniqueness of the audit identifiers.
    extension_ids = list(dict.fromkeys(extension_ids))
    return NormalizedSQL(sql, select.parent.sql(dialect="postgres") if select.parent else select.sql(dialect="postgres"), extension_ids, "Registered alias extension normalized to PostgreSQL.")
