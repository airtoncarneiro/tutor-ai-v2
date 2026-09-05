from __future__ import annotations

import uuid
from typing import Any

from .models import ExerciseContract, LLMRequest, LLMResponse, TutorResponse


def make_request(operation: str, context: dict[str, Any]) -> LLMRequest:
    return LLMRequest(protocol_version="protocol-v2", request_id=str(uuid.uuid4()), operation=operation, prompt_version="tutor-v2", policy_version="evidence-v1", registry_version=1, context=context)


def validate_response(request: LLMRequest, payload: dict[str, Any]) -> LLMResponse:
    response = LLMResponse(protocol_version="protocol-v2", request_id=request.request_id, operation=request.operation, payload=payload)
    if request.operation in {"chat", "feedback", "summarize"}:
        TutorResponse.model_validate(payload)
    elif request.operation == "generate_exercise":
        ExerciseContract.model_validate(payload)
    return response


def validate_generation(payload: dict[str, Any], *, exercise_id: str | None = None, skill_key: str | None = None):
    contract = ExerciseContract.model_validate(payload)
    if exercise_id is not None and contract.exercise_id != exercise_id:
        raise ValueError("LLM changed the assigned exercise identity")
    if skill_key is not None and contract.task.primary_skill != skill_key:
        raise ValueError("LLM changed the requested primary skill")
    return contract
