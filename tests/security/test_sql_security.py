"""Negative security scenarios for the SQL AST allowlist."""

import pytest

from sql_tutor.database import SQLBlocked, validate_sql
from sql_tutor.exercises import example_contract


@pytest.mark.parametrize("query", ["COPY sales TO STDOUT", "LOCK TABLE sales", "SELECT 1; SELECT 2"])
def test_commands_outside_single_read_only_select_are_rejected(query):
    with pytest.raises(SQLBlocked):
        validate_sql(query, example_contract())


def test_schema_qualification_cannot_bypass_the_exercise_tables():
    with pytest.raises(SQLBlocked):
        validate_sql("SELECT * FROM public.sales", example_contract())