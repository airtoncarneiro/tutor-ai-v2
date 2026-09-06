"""Deterministic Streamlit AppTest coverage with no database or paid LLM."""

import pytest

from sql_tutor.exercises import example_contract, explanation_contract
from sql_tutor.models import ResponseMode


pytestmark = pytest.mark.apptest


def _element(elements, label):
    return next(element for element in elements if element.label == label)


def _button(app, label):
    return _element(app.button, label)


def _text_area(app, label):
    return _element(app.text_area, label)


def _text_input(app, label):
    return _element(app.text_input, label)


def _messages(elements):
    return [element.value for element in elements]


def test_sql_only_run_and_submit_are_separate(app_test_factory):
    app, tutor = app_test_factory()
    app.run()

    sql = "SELECT customer_id, SUM(amount) FROM sales GROUP BY customer_id"
    _text_area(app, "SQL Editor").input(sql)
    _button(app, "Run SQL").click().run()

    assert len(app.dataframe) == 1
    assert any(call[0] == "run_sql" for call in tutor.calls)
    assert not any(call[0] == "submit_response" for call in tutor.calls)

    _button(app, "Submit Answer").click().run()

    assert any(call[0] == "submit_response" for call in tutor.calls)
    assert "Correct. Your query matched the expected result on both datasets." in _messages(app.success)
    assert "Deterministic tutor feedback." in _messages(app.info)


def test_sql_plus_reasoning_requires_and_submits_reasoning(app_test_factory):
    contract = example_contract().model_copy(deep=True)
    contract.task.response_mode = ResponseMode.SQL_PLUS_REASONING
    app, tutor = app_test_factory(contract)
    app.run()

    _text_area(app, "SQL Editor").input("SELECT customer_id, SUM(amount) FROM sales GROUP BY customer_id")
    _button(app, "Submit Answer").click().run()
    assert "SQL_PLUS_REASONING requires a technical rationale." in _messages(app.warning)
    assert not any(call[0] == "submit_response" for call in tutor.calls)

    _text_area(app, "Reasoning (required)").input("I grouped rows by customer.")
    _button(app, "Submit Answer").click().run()

    submitted = [call for call in tutor.calls if call[0] == "submit_response"]
    assert submitted[-1][2] == "I grouped rows by customer."


def test_explanation_only_has_no_run_button_and_can_submit(app_test_factory):
    app, tutor = app_test_factory(explanation_contract())
    app.run()

    assert not any(button.label == "Run SQL" for button in app.button)
    _text_area(app, "Answer / explanation").input("GROUP BY creates one result group per key.")
    _button(app, "Submit Answer").click().run()

    assert any(call[0] == "submit_response" for call in tutor.calls)
    assert "Correct. Your query matched the expected result on both datasets." in _messages(app.success)


def test_ui_commands_are_wired_to_distinct_application_methods(app_test_factory):
    app, tutor = app_test_factory()
    app.run()
    _text_area(app, "SQL Editor").input("SELECT 1")

    _button(app, "Hint").click().run()
    assert "Deterministic hint." in _messages(app.info)

    _text_input(app, "Ask the tutor").input("Why GROUP BY?")
    _button(app, "Send question").click().run()
    assert "Deterministic chat response." in _messages(app.info)

    _button(app, "Show Solution").click().run()
    assert "Solution revealed after explicit authorization." in _messages(app.warning)

    _button(app, "Save Draft").click().run()
    _button(app, "Session Summary").click().run()
    _button(app, "Next Exercise").click().run()
    _button(app, "Skip").click().run()

    _text_input(app, "Learning goal").input("Learn window functions")
    _button(app, "Change Goal").click().run()
    _button(app, "Close Session").click().run()

    called = {call[0] for call in tutor.calls}
    assert {"hint", "chat", "show_solution", "save_draft", "summarize", "next_exercise", "skip", "change_goal", "close"} <= called


def test_pending_review_can_be_retried_without_real_llm(app_test_factory):
    app, tutor = app_test_factory(explanation_contract(), submit_decision="pending_review")
    app.run()
    _text_area(app, "Answer / explanation").input("One row is produced for each grouping key.")
    _button(app, "Submit Answer").click().run()

    _button(app, "Retry Review").click().run()

    assert any(call[0] == "retry_review" for call in tutor.calls)
    assert "Review completed." in _messages(app.success)
