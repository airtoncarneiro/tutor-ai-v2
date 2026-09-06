"""Pure learning-state transition scenarios."""

from sql_tutor.models import SkillState
from sql_tutor.policy import apply_attempt, choose_next_policy, choose_policy


def test_low_confidence_has_priority_over_retrieval_and_mastery():
    decision = choose_next_policy(
        [SkillState(skill_key="retrieval", mastery_score=5, evidence_status="mastered"), SkillState(skill_key="gap", mastery_score=5, evidence_status="validated", confidence="low")],
        due={"retrieval", "gap"},
    )

    assert decision.skill_key == "gap"
    assert decision.rule == "C"


def test_repeated_run_failure_does_not_regress_twice_without_independent_evidence():
    state = SkillState(skill_key="x", mastery_score=4, evidence_status="validated", confidence="high")
    first = apply_attempt(state, correct=False, assisted=False, independent=True)
    second = apply_attempt(first, correct=False, assisted=False, independent=False)

    assert first.confidence == "medium"
    assert second.confidence == first.confidence
    assert second.mastery_score == first.mastery_score


def test_chat_or_infrastructure_like_no_evidence_does_not_change_skill_state():
    state = SkillState(skill_key="x")
    assert choose_policy(state).rule == "D1"
    assert apply_attempt(state, correct=False, assisted=False, independent=False) == state.model_copy(update={"failed_attempts": 1})


def test_composed_success_promotes_validated_skill_to_consistent_mastery():
    state = SkillState(
        skill_key="x",
        mastery_score=3,
        evidence_status="validated",
        confidence="high",
        successful_attempts=2,
    )

    updated = apply_attempt(
        state,
        correct=True,
        assisted=False,
        independent=True,
        evidence_kind="composed",
    )

    assert updated.mastery_score == 4
    assert updated.evidence_status == "validated"
    assert updated.retrieval_due_at is not None


def test_delayed_retrieval_promotes_consistent_skill_to_mastered():
    state = SkillState(
        skill_key="x",
        mastery_score=4,
        evidence_status="validated",
        confidence="high",
        successful_attempts=3,
    )

    updated = apply_attempt(
        state,
        correct=True,
        assisted=False,
        independent=True,
        delayed=True,
        evidence_kind="delayed_retrieval",
    )

    assert updated.mastery_score == 5
    assert updated.evidence_status == "mastered"
