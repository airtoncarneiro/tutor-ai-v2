from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import uuid

import streamlit as st

from sql_tutor import ui_runtime


SKILL_LABELS = {
    "aggregation.grouping.group_by": "Grouping with GROUP BY",
    "aggregation.aggregate_functions.sum": "SUM aggregate",
    "aggregation.aggregate_functions.count": "COUNT aggregate",
    "window_functions.row_number": "ROW_NUMBER window function",
    "window_functions.partition_by": "Window partitions",
    "recursive_cte.recursive_structure.anchor_member": "Recursive CTE anchor",
    "query_performance.execution_plan_analysis.node_types": "Execution plan operators",
}


def skill_label(skill_key: str) -> str:
    return SKILL_LABELS.get(skill_key, skill_key.replace(".", " · ").replace("_", " "))


def relative_time(value: str | None) -> str:
    if not value:
        return "time unavailable"
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        seconds = max(0, int((datetime.now(timezone.utc) - moment).total_seconds()))
    except (TypeError, ValueError):
        return "time unavailable"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} hr ago"
    return f"{seconds // 86400} days ago"


st.set_page_config(page_title="Adaptive SQL Tutor", layout="wide")
st.title("Adaptive SQL Tutor")
st.caption("Write, run, receive feedback, and build confidence with SQL.")
if notice := st.session_state.pop("next_exercise_notice", None):
    st.success(notice)
if warning := st.session_state.pop("next_exercise_warning", None):
    st.warning(warning)

try:
    settings = ui_runtime.load_settings(".env")
    tutor = ui_runtime.create_tutor(settings)
    with st.sidebar.expander("Technical details"):
        if settings.llm_base_url and settings.llm_model:
            st.caption(f"Tutor model: remote ({settings.llm_model})")
        else:
            st.caption("Tutor model: local deterministic fallback")
        st.caption("PostgreSQL-backed · single-user local session")

    profile_id = tutor.repo.ensure_profile()
    active_session = tutor.repo.active_session(profile_id)
    if active_session is None:
        st.subheader("Start a learning session")
        st.write("Tell the tutor what you want to learn. Your first exercise will be generated for that goal.")
        requested_goal = st.text_input("What do you want to learn?", placeholder="e.g. SQL window functions")
        requested_mode = st.selectbox("Mode", ["FOCUSED_LEARNING", "FOCUSED_ASSESSMENT", "GENERAL_ASSESSMENT"])
        requested_declaration = st.text_area("What do you already know? (optional)", height=80)
        if not st.button("Start learning", type="primary"):
            st.info("Enter a learning goal to begin.")
            st.stop()
        goal = requested_goal.strip()
        if not goal:
            st.warning("Enter a learning goal before starting.")
            st.stop()
        with st.spinner("Generating your first exercise..."):
            tutor.initialize(goal, requested_mode, requested_declaration)
    else:
        resuming_without_run = not tutor.repo.current_run_exists(str(active_session[0]))
        if resuming_without_run:
            with st.spinner("Preparing your first exercise..."):
                tutor.initialize(active_session[1], active_session[2])
        else:
            tutor.initialize(active_session[1], active_session[2])
        st.sidebar.caption("Active session resumed from the last saved exercise.")
except Exception as exc:
    st.error(f"Application is not ready: {exc}")
    st.stop()


with st.sidebar:
    st.subheader("Progress")
    current_skill = tutor.contract.task.primary_skill
    current_state = next((state for state in tutor.skill_states if state.skill_key == current_skill), None)
    current_score = current_state.mastery_score if current_state else 0
    st.caption(f"Current skill: {skill_label(current_skill)}")
    st.progress(current_score / 5, text=f"Demonstrated: {current_score}/5")
    next_milestone = "independent evidence" if current_score < 3 else "consistent independent success"
    st.caption(f"Next milestone: {next_milestone}.")
    if tutor.skill_states:
        with st.expander("All skills"):
            for state in tutor.skill_states:
                st.progress(state.mastery_score / 5, text=f"{skill_label(state.skill_key)}: {state.mastery_score}/5")


if "sql" not in st.session_state:
    st.session_state.sql = tutor.run_snapshot.get("draft_sql") or ""
if "hint_level" not in st.session_state:
    st.session_state.hint_level = tutor.hint_level
if "failed_count" not in st.session_state:
    st.session_state.failed_count = tutor.failed_count
if "solution_stage" not in st.session_state:
    st.session_state.solution_stage = 0

st.subheader(tutor.contract.task.title)
st.markdown(f"**Objective**  \n{tutor.contract.task.statement}")
mode = tutor.contract.task.response_mode.value
if mode in {"SQL_ONLY", "SQL_PLUS_REASONING"}:
    schema_lines = []
    if tutor.contract.environment:
        for table in tutor.contract.environment.tables:
            columns = ", ".join(f"{column.name} {column.type}" for column in table.columns)
            schema_lines.append(f"{table.name}({columns})")
    with st.expander("Table schema", expanded=True):
        st.code("\n".join(schema_lines), language="text")
    st.session_state.sql = st.text_area("SQL Editor", st.session_state.sql, height=180)
    response_text = st.session_state.sql
else:
    response_text = st.text_area("Answer / explanation", key="answer_text", height=180)

reasoning = None
if mode == "SQL_PLUS_REASONING":
    reasoning = st.text_area("Reasoning (required)", key="reasoning", height=100)

run_col, submit_col, hint_col = st.columns([1, 1.25, 1])
with run_col:
    if mode != "EXPLANATION_ONLY" and st.button("Run SQL", type="secondary", use_container_width=True):
        result = tutor.run_sql(st.session_state.sql, action_id=str(uuid.uuid4()))
        st.session_state.run_result = result.model_dump(mode="json")
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


if st.session_state.get("run_result"):
    st.subheader("Execution feedback")
    result = st.session_state.run_result
    if result["status"] == "ok":
        st.success(f"Query executed successfully · {result['total_row_count']} row(s) returned.")
        st.caption("This execution is exploratory and has not been submitted for evaluation.")
        columns = [column.get("name") or f"column_{index + 1}" for index, column in enumerate(result.get("columns", []))]
        rows = result["preview_rows"]
        if columns and all(len(row) == len(columns) for row in rows):
            st.dataframe([dict(zip(columns, row)) for row in rows])
        else:
            st.dataframe(rows)
        if result["preview_truncated"]:
            st.warning("Preview limit reached; this run was not used as an assessment.")
    else:
        st.error(result.get("safe_error") or "SQL execution failed.")

if st.session_state.get("evaluation"):
    st.subheader("Answer feedback")
    evaluation = st.session_state.evaluation
    if evaluation["decision"] == "correct":
        st.success("Correct. Your query matched the expected result on both datasets.")
    elif evaluation["decision"] == "pending_review":
        st.warning("Your answer is awaiting a valid review.")
    else:
        st.warning("The submission did not receive a correct result.")
    for issue in evaluation.get("issues", []):
        st.write(issue)
if st.session_state.get("feedback"):
    st.info(st.session_state.feedback["message"])
if (st.session_state.get("submit_result") or {}).get("plan_json") is not None:
    st.subheader("Observed PostgreSQL Plan")
    st.json(st.session_state.submit_result["plan_json"])
if (st.session_state.get("evaluation") or {}).get("decision") == "pending_review":
    if st.button("Retry Review"):
        try:
            reviewed = tutor.retry_review()
            st.session_state.evaluation = reviewed.model_dump(mode="json")
            st.success("Review completed.")
        except Exception as exc:
            st.warning(f"Review is still unavailable: {exc}")


with st.expander("Learning support", expanded=True):
    chat_col, chat_button_col = st.columns([4, 1])
    with chat_col:
        chat_text = st.text_input(
            "Ask the tutor",
            key="chat_text",
            placeholder="e.g. Why do I need GROUP BY?",
        )
    with chat_button_col:
        st.write("")
        if st.button("Send question", use_container_width=True) and chat_text:
            st.session_state.chat_response = tutor.chat(chat_text)
    if st.session_state.get("hint"):
        st.info(st.session_state.hint["message"])
    if st.session_state.get("chat_response"):
        st.info(st.session_state.chat_response.get("message", "The tutor could not answer right now."))

    solution_stage = st.session_state.solution_stage
    authorized = (
        st.session_state.failed_count >= 3
        or st.session_state.hint_level >= 2
        or getattr(tutor, "hint_level", 0) >= 2
    )
    if solution_stage == 0 and authorized:
        solution_stage = 1
        st.session_state.solution_stage = solution_stage
    if solution_stage == 0:
        if st.button("Show Hint", use_container_width=True):
            st.session_state.hint_level = min(st.session_state.hint_level + 1, tutor.contract.pedagogy.max_hint_level)
            st.session_state.hint = tutor.hint(st.session_state.hint_level - 1, action_id=str(uuid.uuid4()))
            if (
                st.session_state.failed_count >= 3
                or st.session_state.hint_level >= 2
                or getattr(tutor, "hint_level", 0) >= 2
            ):
                st.session_state.solution_stage = 1
                st.rerun()
    elif solution_stage == 1:
        if st.button("Show Explanation", use_container_width=True):
            try:
                st.session_state.solution = tutor.show_solution(
                    st.session_state.failed_count,
                    st.session_state.hint_level,
                    action_id=str(uuid.uuid4()),
                )
                st.session_state.solution_stage = 2
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))
    elif solution_stage == 2:
        if st.button("Show Full Solution", use_container_width=True):
            st.session_state.solution_stage = 3
            st.rerun()

    if st.session_state.solution_stage >= 2 and st.session_state.get("solution"):
        st.info("Explanation revealed after explicit authorization.")
        if st.session_state.solution.get("explanation"):
            st.write(st.session_state.solution["explanation"])
    if st.session_state.solution_stage >= 3 and st.session_state.get("solution", {}).get("reference_sql"):
        st.warning("Full solution revealed after explicit authorization.")
        st.code(st.session_state.solution["reference_sql"], language="sql")


with st.sidebar.expander("Session controls"):
    new_goal = st.text_input("Learning goal", value="Learn SQL aggregation")
    if st.button("Change Goal", use_container_width=True) and new_goal.strip():
        tutor.change_goal(new_goal.strip())
        st.session_state.hint_level = 0
        st.session_state.failed_count = 0
        st.session_state.solution_stage = 0
        st.session_state.pop("hint", None)
        st.session_state.pop("solution", None)
        st.success("Learning goal saved for the active session.")
    if st.button("Session Summary", use_container_width=True):
        st.info(tutor.summarize()["message"])
    if st.button("Save Draft", use_container_width=True):
        tutor.save_draft(response_text, reasoning, action_id=str(uuid.uuid4()))
        st.success("Draft saved.")
    if st.button("Skip", use_container_width=True):
        tutor.skip(action_id=str(uuid.uuid4()))
        st.info("Exercise skipped.")
    if st.button("Next Exercise", use_container_width=True):
        try:
            tutor.next_exercise()
            st.session_state.sql = ""
            st.session_state.hint_level = 0
            st.session_state.failed_count = 0
            st.session_state.solution_stage = 0
            st.session_state.evaluation = None
            st.session_state.pop("run_result", None)
            st.session_state.pop("submit_result", None)
            st.session_state.pop("feedback", None)
            st.session_state.pop("hint", None)
            st.session_state.pop("chat_response", None)
            st.session_state.pop("solution", None)
            if hasattr(tutor, "last_feedback"):
                tutor.last_feedback = None
            st.session_state.next_exercise_notice = "A new exercise is ready."
            if getattr(tutor, "generation_warning", None):
                st.session_state.next_exercise_warning = tutor.generation_warning
            st.rerun()
        except ValueError as exc:
            st.warning(str(exc))
    if st.button("Close Session", use_container_width=True):
        tutor.close(action_id=str(uuid.uuid4()))
        st.success("Session closed. Reopen the application to start a new session.")


if tutor.evidence_details:
    with st.expander("Learning history"):
        counts = Counter(event["result"] for event in tutor.evidence_details)
        summary = " · ".join(
            f"{counts.get(result, 0)} {label}"
            for result, label in (("correct", "correct"), ("incorrect", "incorrect"), ("partial", "partial"))
            if counts.get(result, 0)
        ) or "No finalized results yet"
        st.write(summary)
        grouped = Counter(event["skill_key"] for event in tutor.evidence_details)
        st.caption("By skill: " + " · ".join(f"{skill_label(key)} ({count})" for key, count in grouped.items()))
        recent_events = tutor.evidence_details[:5]
        for event in recent_events:
            with st.container(border=True):
                st.markdown(
                    f"**{skill_label(event['skill_key'])}** · {event['result']} · {relative_time(event.get('created_at'))}"
                )
                left, right = st.columns(2)
                with left:
                    st.write(f"Exercise: {event['exercise_id']}")
                    st.write(f"Context: {event['context_tag']}")
                    st.write(f"Evidence kind: {event['evidence_kind']}")
                with right:
                    st.write(f"Independent: {'yes' if event['independent'] else 'no'}")
                    st.write(f"Assisted: {'yes' if event['assisted'] else 'no'}")
                    st.write(f"Hints at submission: {event['hint_level_at_submit']}")
                if event.get("submitted_sql"):
                    st.code(event["submitted_sql"], language="sql")
                if event.get("reasoning"):
                    st.write(event["reasoning"])
                st.json(event["evaluation"])
        if len(tutor.evidence_details) > len(recent_events):
            st.caption(f"Showing the 5 most recent events of {len(tutor.evidence_details)}.")
