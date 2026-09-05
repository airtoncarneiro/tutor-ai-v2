from __future__ import annotations

import uuid

import streamlit as st

from sql_tutor.application import TutorApplication
from sql_tutor.config import ConfigurationError, Settings


st.set_page_config(page_title="Adaptive SQL Tutor", layout="wide")
st.title("Adaptive SQL Tutor")
st.caption("Local single-user learning lab · PostgreSQL-backed · Run SQL is separate from Submit Answer")

try:
    settings = Settings.from_env(".env")
    tutor = TutorApplication(settings)
    requested_goal = st.sidebar.text_input("Learning goal", value="Learn SQL aggregation")
    requested_mode = st.sidebar.selectbox("Mode", ["FOCUSED_LEARNING", "FOCUSED_ASSESSMENT", "GENERAL_ASSESSMENT"])
    requested_declaration = st.sidebar.text_area("Knowledge declaration (optional)", height=80)
    if settings.llm_base_url and settings.llm_model:
        st.sidebar.caption(f"Tutor model: remote ({settings.llm_model}) · local fallback enabled")
    else:
        st.sidebar.caption("Tutor model: local deterministic fallback")
    tutor.initialize(requested_goal.strip() or "Learn SQL aggregation", requested_mode, requested_declaration)
    st.sidebar.subheader("Progress")
    for state in tutor.skill_states:
        st.sidebar.progress(state.mastery_score / 5, text=f"{state.skill_key}: {state.mastery_score}/5")
    if tutor.skill_states:
        st.sidebar.caption("Mastery is based on evidence, not a single answer.")
    if tutor.evidence_events:
        with st.sidebar.expander("Recent evidence"):
            for event in tutor.evidence_events:
                assistance = "assisted" if event["assisted"] else "independent" if event["independent"] else "unclassified"
                st.write(f"{event['skill_key']} · {event['result']} · {assistance}")
except Exception as exc:
    st.error(f"Application is not ready: {exc}")
    st.stop()

if "sql" not in st.session_state:
    st.session_state.sql = tutor.run_snapshot.get("draft_sql") or ""
st.subheader(tutor.contract.task.title)
st.write(tutor.contract.task.statement)
mode = tutor.contract.task.response_mode.value
if mode in {"SQL_ONLY", "SQL_PLUS_REASONING"}:
    schema_lines = []
    if tutor.contract.environment:
        for table in tutor.contract.environment.tables:
            columns = ", ".join(f"{column.name} {column.type}" for column in table.columns)
            schema_lines.append(f"{table.name}({columns})")
    st.code("\n".join(schema_lines), language="text")
    st.session_state.sql = st.text_area("SQL Editor", st.session_state.sql, height=180)
    response_text = st.session_state.sql
else:
    response_text = st.text_area("Answer / explanation", key="answer_text", height=180)
reasoning = None
if mode == "SQL_PLUS_REASONING":
    reasoning = st.text_area("Reasoning (optional)", key="reasoning", height=100)
if "hint_level" not in st.session_state:
    st.session_state.hint_level = tutor.hint_level
if "failed_count" not in st.session_state:
    st.session_state.failed_count = tutor.failed_count
run_col, submit_col, hint_col = st.columns(3)
with run_col:
    if mode != "EXPLANATION_ONLY" and st.button("Run SQL", type="secondary", use_container_width=True):
        st.session_state.run_result = tutor.run_sql(st.session_state.sql, action_id=str(uuid.uuid4())).model_dump(mode="json")
with submit_col:
    if st.button("Submit Answer", type="primary", use_container_width=True):
        if mode == "SQL_PLUS_REASONING" and not (reasoning or "").strip():
            st.warning("SQL_PLUS_REASONING requires a technical rationale.")
            result, evaluation = None, None
        elif not response_text.strip():
            st.warning("Enter an answer before submitting.")
            result, evaluation = None, None
        else:
            result, evaluation = tutor.submit_response(response_text, reasoning, action_id=str(uuid.uuid4()))
        st.session_state.submit_result = result.model_dump(mode="json") if result else None
        st.session_state.evaluation = evaluation.model_dump(mode="json") if evaluation else None
        st.session_state.feedback = getattr(tutor, "last_feedback", None)
        if evaluation and evaluation.decision in {"incorrect", "partial", "learner_sql_error"}:
            st.session_state.failed_count += 1
with hint_col:
    if st.button("Hint", use_container_width=True):
        st.session_state.hint_level = min(st.session_state.hint_level + 1, tutor.contract.pedagogy.max_hint_level)
        st.session_state.hint = tutor.hint(st.session_state.hint_level - 1, action_id=str(uuid.uuid4()))

if st.session_state.get("hint"):
    st.info(st.session_state.hint["message"])

chat_text = st.text_input("Ask the tutor", key="chat_text")
if st.button("Send question") and chat_text:
    st.session_state.chat_response = tutor.chat(chat_text)
if st.session_state.get("chat_response"):
    st.info(st.session_state.chat_response.get("message", "The tutor could not answer right now."))

if st.button("Show Solution"):
    try:
        st.session_state.solution = tutor.show_solution(st.session_state.failed_count, st.session_state.hint_level, action_id=str(uuid.uuid4()))
    except ValueError as exc:
        st.warning(str(exc))
if st.session_state.get("solution"):
    st.warning("Solution revealed after explicit authorization.")
    if st.session_state.solution.get("reference_sql"):
        st.code(st.session_state.solution["reference_sql"], language="sql")
    elif st.session_state.solution.get("explanation"):
        st.write(st.session_state.solution["explanation"])

st.divider()
action_col, close_col = st.columns(2)
with action_col:
    new_goal = st.text_input("Learning goal", value="Learn SQL aggregation")
    if st.button("Change Goal", use_container_width=True) and new_goal.strip():
        tutor.change_goal(new_goal.strip())
        st.success("Learning goal saved for the active session.")
with close_col:
    if st.button("Close Session", use_container_width=True):
        tutor.close(action_id=str(uuid.uuid4()))
        st.success("Session closed. Reopen the application to start a new session.")

if st.button("Session Summary"):
    st.info(tutor.summarize()["message"])

nav_col, draft_col, skip_col = st.columns(3)
with nav_col:
    if st.button("Next Exercise", use_container_width=True):
        try:
            tutor.next_exercise()
            st.session_state.sql = ""
            st.session_state.hint_level = 0
            st.session_state.failed_count = 0
            st.session_state.evaluation = None
            st.session_state.pop("run_result", None)
            st.success("A new exercise is ready.")
        except ValueError as exc:
            st.warning(str(exc))
with draft_col:
    if st.button("Save Draft", use_container_width=True):
        tutor.save_draft(response_text, reasoning, action_id=str(uuid.uuid4()))
        st.success("Draft saved.")
with skip_col:
    if st.button("Skip", use_container_width=True):
        tutor.skip(action_id=str(uuid.uuid4()))
        st.info("Exercise skipped.")

if "run_result" in st.session_state:
    st.subheader("Query Result")
    result = st.session_state.run_result
    if result["status"] == "ok":
        st.dataframe(result["preview_rows"])
        if result["preview_truncated"]:
            st.warning("Preview limit reached; this run was not used as an assessment.")
    else:
        st.error(result.get("safe_error") or "SQL execution failed.")
if st.session_state.get("evaluation"):
    st.subheader("Tutor Feedback")
    evaluation = st.session_state.evaluation
    if evaluation["decision"] == "correct":
        st.success("Correct. Your query matched the expected result on both datasets.")
    else:
        st.warning("The submission did not receive a correct result.")
    for issue in evaluation.get("issues", []):
        st.write(issue)
if (st.session_state.get("submit_result") or {}).get("plan_json") is not None:
    st.subheader("Observed PostgreSQL Plan")
    st.json(st.session_state.submit_result["plan_json"])
if st.session_state.get("feedback"):
    st.subheader("Tutor Feedback")
    st.info(st.session_state.feedback["message"])
if (st.session_state.get("evaluation") or {}).get("decision") == "pending_review":
    if st.button("Retry Review"):
        try:
            reviewed = tutor.retry_review()
            st.session_state.evaluation = reviewed.model_dump(mode="json")
            st.success("Review completed.")
        except Exception as exc:
            st.warning(f"Review is still unavailable: {exc}")

if tutor.evidence_details:
    st.subheader("Evidence details")
    st.caption("Evidence is derived from submitted work, execution results, and the stored skill-state transition.")
    for event in tutor.evidence_details:
        timestamp = event["created_at"].replace("T", " ")[:19] if event.get("created_at") else "time unavailable"
        with st.expander(f"{event['skill_key']} · {event['result']} · {timestamp}"):
            left, right = st.columns(2)
            with left:
                st.write(f"**Exercise:** {event['exercise_id']}")
                st.write(f"**Context:** {event['context_tag']}")
                st.write(f"**Evidence kind:** {event['evidence_kind']}")
                st.write(f"**Source:** {event['source']}")
            with right:
                st.write(f"**Independent:** {'yes' if event['independent'] else 'no'}")
                st.write(f"**Assisted:** {'yes' if event['assisted'] else 'no'}")
                st.write(f"**Hints at submission:** {event['hint_level_at_submit']}")
                if event.get("error_kind"):
                    st.write(f"**Error kind:** {event['error_kind']}")
            if event.get("submitted_sql"):
                st.write("Submitted SQL")
                st.code(event["submitted_sql"], language="sql")
            if event.get("reasoning"):
                st.write("Submitted reasoning")
                st.write(event["reasoning"])
            st.write("Evaluation")
            st.json(event["evaluation"])
            before, after = st.columns(2)
            with before:
                st.write("Skill state before")
                st.json(event["before_state"])
            with after:
                st.write("Skill state after")
                st.json(event["after_state"])
