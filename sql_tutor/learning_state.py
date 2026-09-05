from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .models import SkillState


@dataclass(frozen=True)
class Evidence:
    correct: bool
    assisted: bool
    independent: bool
    evidence_kind: str
    context_tag: str
    observed_at: datetime


def is_independent(evidence: Evidence, *, previous_contexts: set[str], previous_hashes: set[str] | None = None, content_hash: str | None = None) -> bool:
    if not evidence.independent or evidence.assisted:
        return False
    if evidence.context_tag in previous_contexts:
        return False
    return not previous_hashes or content_hash not in previous_hashes


def update_state(state: SkillState, evidence: Evidence, *, independent_successes: int = 0, previous_contradiction: bool = False) -> SkillState:
    result = state.model_copy(deep=True)
    if not evidence.correct:
        result.failed_attempts += 1
        if result.evidence_status in {"unknown", "self_declared"}:
            result.evidence_status, result.mastery_score = "observed", max(1, result.mastery_score)
        elif previous_contradiction:
            result.confidence = "low"
            result.mastery_score = max(1, result.mastery_score - 1)
        elif result.evidence_status in {"validated", "mastered"}:
            result.confidence = "medium" if result.confidence == "high" else "low"
        return result
    result.successful_attempts += 1
    if evidence.assisted:
        result.evidence_status = "observed" if result.evidence_status == "unknown" else result.evidence_status
        result.mastery_score = max(result.mastery_score, 2)
        result.hints_required += 1
        return result
    if not evidence.independent:
        return result
    result.mastery_score = max(result.mastery_score, 3)
    if result.evidence_status in {"unknown", "self_declared"}:
        result.evidence_status = "observed"
    if independent_successes + 1 >= 2:
        result.evidence_status = "validated"
        result.confidence = "high"
    if independent_successes + 1 >= 3 and evidence.evidence_kind == "composed":
        result.mastery_score = max(result.mastery_score, 4)
    if independent_successes + 1 >= 4 and evidence.evidence_kind == "delayed_retrieval":
        result.mastery_score, result.evidence_status = 5, "mastered"
    return result


def retrieval_due(retrieval_due_at: datetime | None, now: datetime | None = None) -> bool:
    return bool(retrieval_due_at and (now or datetime.now(timezone.utc)) >= retrieval_due_at)


def next_retrieval(now: datetime | None = None, retention_count: int = 0) -> datetime:
    return (now or datetime.now(timezone.utc)) + timedelta(days=7 if retention_count == 0 else 14 if retention_count == 1 else 30)


def aging(state: SkillState, *, last_seen: datetime | None, now: datetime | None = None) -> SkillState:
    if not last_seen:
        return state.model_copy(deep=True)
    now = now or datetime.now(timezone.utc)
    result = state.model_copy(deep=True)
    intervals = max(0, (now - last_seen).days // 90)
    for _ in range(intervals):
        if result.confidence == "high":
            result.confidence = "medium"
        elif result.confidence == "medium":
            result.confidence = "low"
    return result


def checkpoint_required(*, finalized_since_checkpoint: int, promotion: bool = False, goal_changed: bool = False, strategy_changed: bool = False) -> bool:
    return finalized_since_checkpoint >= 5 or promotion or goal_changed or strategy_changed
