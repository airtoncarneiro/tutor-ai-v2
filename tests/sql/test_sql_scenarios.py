"""Deterministic SQL contract and evaluation scenarios."""

import pytest

from sql_tutor.database import SQLBlocked, validate_constraints, validate_sql
from sql_tutor.evaluator import compare_rows, evaluate_sql
from sql_tutor.exercises import example_contract
from sql_tutor.models import ExecutionResult


def test_equivalent_grouped_queries_and_aliases_satisfy_the_contract():
    contract = example_contract()

    for query in (
        "SELECT customer_id, SUM(amount) AS total FROM sales GROUP BY customer_id",
        "SELECT s.customer_id, SUM(s.amount) FROM sales AS s GROUP BY s.customer_id",
    ):
        assert validate_constraints(query, contract) == {"grouped_sum": "pass"}


@pytest.mark.parametrize(
    "query",
    [
        "SELECT customer_id, AVG(amount) FROM sales GROUP BY customer_id",
        "SELECT customer_id, SUM(sale_id) FROM sales GROUP BY customer_id",
        "SELECT customer_id, SUM(amount) FROM sales GROUP BY customer_id, sale_id",
    ],
)
def test_structural_grouping_mismatches_are_reported(query):
    assert validate_constraints(query, example_contract()) == {"grouped_sum": "fail"}


def test_result_comparison_preserves_duplicates_and_nulls():
    assert compare_rows([[1], [1], [None]], [[1], [1], [None]], order_sensitive=False)
    assert not compare_rows([[1], [1]], [[1]], order_sensitive=False)
    assert not compare_rows([[1], [None]], [[None], [1]], order_sensitive=True)


def test_incomplete_results_are_inconclusive_not_incorrect():
    contract = example_contract()
    visible = ExecutionResult(status="ok", submitted_sql="SELECT 1", complete=False)
    hidden = ExecutionResult(status="ok", submitted_sql="SELECT 1", complete=True)

    result = evaluate_sql(contract, visible, hidden)

    assert result.decision == "inconclusive"
    assert result.score is None


@pytest.mark.parametrize(
    "query",
    [
        "WITH changed AS (DELETE FROM sales RETURNING sale_id) SELECT * FROM changed",
        "SELECT * INTO new_table FROM sales",
        "SELECT * FROM sales FOR UPDATE",
        "SELECT * FROM sales; DROP TABLE sales;",
        "SELECT pg_sleep(1)",
        "SELECT * FROM tutor_state.student_profiles",
    ],
)
def test_unsafe_sql_is_blocked_before_execution(query):
    with pytest.raises(SQLBlocked):
        validate_sql(query, example_contract())