from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import PolicyDecision, SkillState


def choose_policy(skill: SkillState, *, relevant: bool = True, blocking_prerequisite: str | None = None, retrieval_due: bool = False) -> PolicyDecision:
    if not relevant:
        return PolicyDecision(rule="A", action="exclude", skill_key=skill.skill_key, reason="Skill is outside the current goal.")
    if blocking_prerequisite:
        return PolicyDecision(rule="B", action="revalidate", skill_key=blocking_prerequisite, reason="A concrete prerequisite gap blocks the goal.")
    if skill.confidence == "low":
        return PolicyDecision(rule="C", action="revalidate", skill_key=skill.skill_key, reason="Low confidence requires revalidation before progression.")
    if skill.evidence_status in {"unknown", "self_declared"}:
        return PolicyDecision(rule="D1", action="diagnose", skill_key=skill.skill_key, reason="There is not enough independent evidence.")
    if skill.evidence_status == "observed":
        if skill.mastery_score >= 3:
            return PolicyDecision(rule="D2.1", action="diagnose", skill_key=skill.skill_key, reason="Seek independent evidence for an observed skill.")
        return PolicyDecision(rule="D2.2", action="guided_practice", skill_key=skill.skill_key, reason="Observed evidence is still insufficient for independent performance.")
    if skill.mastery_score <= 2:
        return PolicyDecision(rule="E1", action="teach_practice", skill_key=skill.skill_key, reason="Reliable evidence exists but mastery is developing.")
    if skill.mastery_score == 3:
        return PolicyDecision(rule="E2", action="advance_moderately", skill_key=skill.skill_key, reason="Seek consistency at a moderate difficulty increase.")
    if retrieval_due:
        return PolicyDecision(rule="F", action="retrieve", skill_key=skill.skill_key, reason="Delayed retrieval is due and no immediate intervention is pending.")
    return PolicyDecision(rule="E3", action="advance", skill_key=skill.skill_key, reason="Reliable evidence supports advancement and future retrieval.")


def choose_next_policy(skills: list[SkillState], *, eligible: set[str] | None = None, current_focus: str | None = None, due: set[str] | None = None) -> PolicyDecision | None:
    """Filter global intervention priority and return exactly one decision."""
    candidates = [skill for skill in skills if eligible is None or skill.skill_key in eligible]
    if not candidates:
        return None
    def tier(skill: SkillState) -> int:
        if skill.confidence == "low":
            return 0
        if skill.evidence_status in {"unknown", "self_declared"}:
            return 1
        if skill.evidence_status == "observed":
            return 2
        if skill.mastery_score <= 2:
            return 3
        if skill.mastery_score == 3:
            return 4
        if due and skill.skill_key in due:
            return 5
        return 6
    selected = sorted(candidates, key=lambda skill: (tier(skill), 0 if skill.skill_key == current_focus else 1, skill.skill_key))[0]
    return choose_policy(selected, retrieval_due=bool(due and selected.skill_key in due))


def apply_attempt(
    skill: SkillState,
    *,
    correct: bool,
    assisted: bool,
    independent: bool,
    delayed: bool = False,
    evidence_kind: str = "isolated",
) -> SkillState:
    """Apply the evidence-v1 MVP transition to a copy-like model."""
    state = skill.model_copy(deep=True)
    if independent or assisted:
        state.last_seen = datetime.now(timezone.utc)
    if correct:
        state.successful_attempts += 1
        state.failed_attempts = state.failed_attempts
        if assisted:
            state.mastery_score = max(state.mastery_score, 2)
            if state.evidence_status == "unknown":
                state.evidence_status = "observed"
        elif independent:
            state.mastery_score = max(state.mastery_score, 3)
            state.evidence_status = "mastered" if delayed and state.mastery_score >= 4 else state.evidence_status
            if state.evidence_status in {"unknown", "self_declared"}:
                state.evidence_status = "observed"
            state.confidence = "high" if state.successful_attempts >= 2 else max(state.confidence, "medium", key=["low", "medium", "high"].index)
            if state.successful_attempts >= 2:
                state.evidence_status = "validated"
            if evidence_kind == "composed" and state.successful_attempts >= 3:
                state.mastery_score = max(state.mastery_score, 4)
            if delayed and state.successful_attempts >= 3 and state.mastery_score >= 4:
                state.mastery_score = 5
                state.evidence_status = "mastered"
            if state.mastery_score >= 4 and state.evidence_status != "mastered" and state.retrieval_due_at is None:
                from .learning_state import next_retrieval
                state.retrieval_due_at = next_retrieval(state.last_seen)
        return state
    state.failed_attempts += 1
    if not independent:
        return state
    if state.evidence_status in {"unknown", "self_declared"}:
        state.evidence_status = "observed"
        state.mastery_score = max(state.mastery_score, 1)
    elif state.failed_attempts >= 2 and state.confidence != "low":
        state.confidence = "low"
        state.mastery_score = max(1, state.mastery_score - 1)
    elif state.evidence_status in {"validated", "mastered"}:
        state.confidence = "medium" if state.confidence == "high" else "low"
    return state


def retrieval_due(last_seen: datetime | None, now: datetime | None = None) -> bool:
    if not last_seen:
        return False
    now = now or datetime.now(timezone.utc)
    return now >= last_seen + timedelta(days=7)
