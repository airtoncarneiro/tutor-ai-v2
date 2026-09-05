from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .models import ExerciseContract


class ContractError(ValueError):
    pass


def adapt_provider_contract(payload: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Adapt the known provider shorthand into v2 without relaxing validation."""
    if not isinstance(payload, dict) or not isinstance(payload.get("task"), (str, dict)):
        return payload
    task = payload["task"]
    if isinstance(task, dict) and {"title", "statement", "primary_skill"}.issubset(task):
        return payload
    environment = payload.get("environment") or {}
    private = payload.get("private") or {}
    validation = payload.get("validation") or {}
    pedagogy = payload.get("pedagogy") or {}
    description = task if isinstance(task, str) else task.get("description", "")
    skills = task.get("skills", []) if isinstance(task, dict) else []
    primary_skill = skills[0] if skills else pedagogy.get("target_skill") or request.get("target_skill")
    response_mode = (task.get("mode") if isinstance(task, dict) else None) or request.get("response_mode", "SQL_ONLY")
    evidence_kind = request.get("evidence_kind", "isolated")
    setup = environment.get("setup") or {}
    tables = setup.get("tables") if isinstance(setup, dict) else None
    tables = tables if tables is not None else environment.get("tables")
    if not isinstance(tables, list) or not tables:
        return payload
    normalized_tables = []
    for table in tables:
        if not isinstance(table, dict) or not table.get("name"):
            return payload
        columns = table.get("columns")
        if isinstance(columns, dict):
            columns = [{"name": name, "type": value} for name, value in columns.items()]
        if not isinstance(columns, list) or not columns:
            return payload
        normalized_columns = []
        for column in columns:
            if isinstance(column, str):
                name, _, type_name = column.partition(":")
                column = {"name": name.strip(), "type": type_name.strip() or "text"}
            if not isinstance(column, dict) or not column.get("name"):
                return payload
            type_name = str(column.get("type", "text")).lower()
            type_name = {"int": "integer", "float": "numeric", "decimal": "numeric", "string": "text"}.get(type_name, type_name)
            if type_name not in {"integer", "bigint", "numeric", "text", "boolean", "date"}:
                return payload
            normalized_columns.append({"name": column["name"], "type": type_name, "nullable": bool(column.get("nullable", True))})
        normalized_tables.append({"name": table["name"], "columns": normalized_columns, "primary_key": table.get("primary_key", []), "indexes": table.get("indexes", [])})

    def rows_for(source: Any, table_name: str):
        rows = source.get(table_name, []) if isinstance(source, dict) else source if isinstance(source, list) and len(normalized_tables) == 1 else None
        if not isinstance(rows, list):
            return None
        columns = [c["name"] for c in next(t for t in normalized_tables if t["name"] == table_name)["columns"]]
        result = []
        for row in rows:
            if isinstance(row, dict):
                result.append([row.get(column) for column in columns])
            elif isinstance(row, list):
                result.append(row)
            else:
                return None
        return result

    visible_data, hidden_data = {}, {}
    for table in normalized_tables:
        visible_rows = rows_for(environment.get("visible_data"), table["name"])
        hidden_rows = rows_for(environment.get("hidden_data"), table["name"])
        if visible_rows is None or hidden_rows is None:
            return payload
        visible_data[table["name"]], hidden_data[table["name"]] = visible_rows, hidden_rows
    expected_visible, expected_hidden = private.get("expected_visible_rows"), private.get("expected_hidden_rows")
    if not isinstance(expected_visible, list) or not isinstance(expected_hidden, list):
        return payload
    keys = []
    for row in [*expected_visible, *expected_hidden]:
        if isinstance(row, dict):
            keys.extend(key for key in row if key not in keys)
    if keys:
        expected_visible = [[row.get(key) for key in keys] if isinstance(row, dict) else row for row in expected_visible]
        expected_hidden = [[row.get(key) for key in keys] if isinstance(row, dict) else row for row in expected_hidden]
    if not keys and expected_visible:
        keys = [f"column_{i + 1}" for i in range(len(expected_visible[0]))]
    output_columns = []
    for index, name in enumerate(keys):
        values = [row[index] for row in [*expected_visible, *expected_hidden] if len(row) > index and row[index] is not None]
        type_name = "numeric" if any(isinstance(value, float) for value in values) else "integer" if values and all(isinstance(value, int) and not isinstance(value, bool) for value in values) else "text"
        output_columns.append({"name": name, "type": type_name})
    hints = private.get("hints", [])
    if not isinstance(hints, list) or len(hints) < 3:
        return payload
    return {
        "schema_version": 2, "exercise_id": payload.get("exercise_id") or f"{primary_skill.replace('.', '_')}_provider", "version": int(payload.get("version", 1)),
        "task": {"title": description[:200] or "SQL exercise", "statement": description or "Solve the SQL exercise.", "primary_skill": primary_skill, "secondary_skills": skills[1:6], "difficulty": int(pedagogy.get("difficulty", request.get("difficulty", 1))), "response_mode": response_mode, "context_tag": payload.get("exercise_id") or "provider_context", "evidence_kind": evidence_kind, "expected_evidence": [description or "Produce the requested result."], "hidden_variables": [{"name": "provider_hidden_data", "purpose": "Check generalization on hidden rows."}]},
        "environment": {"engine": "PostgreSQL", "mode": "AUTO_SETUP", "tables": normalized_tables, "visible_data": visible_data, "hidden_data": hidden_data},
        "validation": {"mode": "RESULT_EQUIVALENCE", "output_columns": output_columns, "order_sensitive": not bool(validation.get("options", {}).get("ignore_order", False)), "numeric_tolerance": 0, "constraints": [], "reasoning_rubric": []},
        "pedagogy": {"max_hint_level": 3, "allow_solution_reveal": True},
        "private": {"reference_sql": private.get("reference_sql"), "expected_visible_rows": expected_visible, "expected_hidden_rows": expected_hidden, "hints": hints[:3], "solution_explanation": private.get("solution_explanation", "The reference query satisfies the declared result contract.")},
    }


def validate_contract(payload: dict[str, Any]) -> ExerciseContract:
    contract = ExerciseContract.model_validate(payload)
    if contract.task.primary_skill not in SUPPORTED_SKILLS:
        raise ContractError(f"Unsupported skill: {contract.task.primary_skill}")
    if contract.validation.mode.value == "RESULT_EQUIVALENCE":
        if not contract.private.reference_sql or contract.private.expected_visible_rows is None or contract.private.expected_hidden_rows is None:
            raise ContractError("RESULT_EQUIVALENCE requires reference SQL and expected rows")
        if len(contract.private.expected_visible_rows) == 0 and len(contract.private.expected_hidden_rows) == 0:
            raise ContractError("RESULT_EQUIVALENCE requires a non-empty expected result in at least one dataset")
        for rows in (contract.private.expected_visible_rows, contract.private.expected_hidden_rows):
            if any(len(row) != len(contract.validation.output_columns) for row in rows):
                raise ContractError("Expected rows must match output_columns arity")
        from .database import validate_constraints, validate_sql
        validate_sql(contract.private.reference_sql, contract)
        constraint_results = validate_constraints(contract.private.reference_sql, contract)
        if "fail" in constraint_results.values():
            raise ContractError("Reference SQL does not satisfy the declared structural constraints")
    if contract.validation.mode.value in {"EXPLANATION", "PLAN_ANALYSIS"}:
        rubric = contract.validation.rubric or contract.validation.reasoning_rubric
        if not rubric or not any(item.required and item.skill_key == contract.task.primary_skill for item in rubric):
            raise ContractError("A rubric with a required primary-skill criterion is required")
    if contract.validation.mode.value == "PLAN_ANALYSIS" and contract.environment:
        if any(contract.environment.visible_data.values()) or any(contract.environment.hidden_data.values()):
            raise ContractError("PLAN_ANALYSIS environments must not contain seed rows")
    for constraint in contract.validation.constraints:
        if constraint.type == "uses_table" and constraint.table not in {t.name for t in (contract.environment.tables if contract.environment else [])}:
            raise ContractError(f"Constraint references unknown table: {constraint.table}")
        if constraint.type == "grouped_aggregate":
            tables = {t.name: {c.name for c in t.columns} for t in (contract.environment.tables if contract.environment else [])}
            references = [*(constraint.group_by or [])]
            if constraint.argument != "*":
                references.insert(0, constraint.argument)
            elif constraint.function != "count":
                raise ContractError(f"Constraint {constraint.id} allows * only for count")
            for reference in references:
                if not reference:
                    raise ContractError(f"Constraint {constraint.id} is missing a column reference")
                table_name, _, column_name = reference.partition(".")
                if table_name not in tables or (column_name != "*" and column_name not in tables[table_name]):
                    raise ContractError(f"Constraint {constraint.id} references an unknown column: {reference}")
            if not constraint.group_by or not constraint.output_alias:
                raise ContractError(f"Constraint {constraint.id} requires group_by and output_alias")
        if constraint.type == "window_function" and not constraint.output_alias:
            raise ContractError(f"Constraint {constraint.id} requires output_alias")
    return contract


def contract_hash(contract: ExerciseContract) -> str:
    canonical = json.dumps(contract.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def public_projection(contract: ExerciseContract) -> dict[str, Any]:
    data = contract.model_dump(mode="json")
    data["private"] = None
    if data.get("environment"):
        data["environment"]["hidden_data"] = None
    return data


SUPPORTED_SKILLS = {
    "aggregation.grouping.group_by",
    "aggregation.aggregate_functions.sum",
    "aggregation.aggregate_functions.count",
    "aggregation.grouping.grouping_granularity",
    "window_functions.row_number",
    "window_functions.rank",
    "window_functions.partition_by",
    "recursive_cte.recursive_structure.anchor_member",
    "query_performance.execution_plan_analysis.node_types",
}


def example_contract() -> ExerciseContract:
    return validate_contract({
        "schema_version": 2, "exercise_id": "sales_by_customer", "version": 1,
        "task": {"title": "Sales totals by customer", "statement": "Using GROUP BY and SUM, return customer_id and total_sales for each customer. Each row is a sale, and a customer may have multiple sales. Row order does not matter.", "primary_skill": "aggregation.grouping.group_by", "secondary_skills": ["aggregation.aggregate_functions.sum"], "difficulty": 1, "response_mode": "SQL_ONLY", "context_tag": "retail_sales_totals", "evidence_kind": "isolated", "expected_evidence": ["Group sale rows at customer granularity."], "hidden_variables": [{"name": "repeated_customer", "purpose": "Require grouping multiple sales per customer."}]},
        "environment": {"engine": "PostgreSQL", "mode": "AUTO_SETUP", "tables": [{"name": "sales", "columns": [{"name": "sale_id", "type": "integer", "nullable": False}, {"name": "customer_id", "type": "integer", "nullable": False}, {"name": "amount", "type": "numeric", "nullable": False}], "primary_key": ["sale_id"], "indexes": []}], "visible_data": {"sales": [[1, 101, "500.00"], [2, 101, "300.00"], [3, 205, "900.00"]]}, "hidden_data": {"sales": [[1, 7, "10.00"], [2, 7, "20.00"], [3, 8, "40.00"]]}},
        "validation": {"mode": "RESULT_EQUIVALENCE", "output_columns": [{"name": "customer_id", "type": "integer"}, {"name": "total_sales", "type": "numeric"}], "order_sensitive": False, "numeric_tolerance": 0, "constraints": [{"id": "grouped_sum", "type": "grouped_aggregate", "function": "sum", "argument": "sales.amount", "group_by": ["sales.customer_id"], "output_alias": "total_sales"}], "reasoning_rubric": []},
        "pedagogy": {"max_hint_level": 3, "allow_solution_reveal": True},
        "private": {"reference_sql": "SELECT customer_id, SUM(amount) AS total_sales FROM sales GROUP BY customer_id", "expected_visible_rows": [[101, "800.00"], [205, "900.00"]], "expected_hidden_rows": [[7, "30.00"], [8, "40.00"]], "hints": ["Think about which entity should occupy one output row.", "The grouping key identifies the customer; aggregate the amounts inside each group.", "Start with SELECT customer_id and add the aggregate expression before grouping."], "solution_explanation": "GROUP BY creates one group per customer; SUM combines the amounts in each group."}
    })


def explanation_contract() -> ExerciseContract:
    """Small deterministic contract used by the explanation-mode integration tests."""
    return validate_contract({
        "schema_version": 2, "exercise_id": "explain_grouping", "version": 1,
        "task": {"title": "Explain grouping granularity", "statement": "Explain why the grouping key determines the number of result rows.", "primary_skill": "aggregation.grouping.group_by", "secondary_skills": [], "difficulty": 1, "response_mode": "EXPLANATION_ONLY", "context_tag": "explanation_grouping", "evidence_kind": "isolated", "expected_evidence": ["Connect the grouping key to result granularity."], "hidden_variables": [{"name": "none", "purpose": "No hidden execution data is needed."}]},
        "environment": None,
        "validation": {"mode": "EXPLANATION", "rubric": [{"id": "granularity", "criterion": "Connects GROUP BY keys to one output group per key.", "required": True, "skill_key": "aggregation.grouping.group_by"}]},
        "pedagogy": {"max_hint_level": 3, "allow_solution_reveal": True},
        "private": {"hints": ["Name the entity represented by one row.", "Relate each group to one grouping-key value.", "Explain how multiple input rows become one group."], "reference_explanation": "GROUP BY creates one group for each distinct grouping-key value, so the output has one row per group.", "solution_explanation": "The grouping key defines result granularity."}
    })


def plan_contract() -> ExerciseContract:
    """Deterministic plan-analysis contract with no seeded learner data."""
    contract = example_contract().model_dump(mode="json")
    contract["exercise_id"] = "plan_grouping"
    contract["task"].update({"title": "Interpret a grouping plan", "statement": "Explain what the real PostgreSQL plan indicates about this grouping query.", "response_mode": "EXPLANATION_ONLY", "context_tag": "plan_grouping"})
    contract["environment"]["visible_data"] = {"sales": []}
    contract["environment"]["hidden_data"] = {"sales": []}
    contract["validation"] = {"mode": "PLAN_ANALYSIS", "supplied_query": "SELECT customer_id, SUM(amount) AS total_sales FROM sales GROUP BY customer_id", "rubric": [{"id": "aggregate_node", "criterion": "Identifies the aggregate and grouping evidence in the observed plan.", "required": True, "skill_key": "aggregation.grouping.group_by"}]}
    contract["private"].update({"reference_explanation": "The plan should contain an aggregate operation over customer groups."})
    return validate_contract(contract)
