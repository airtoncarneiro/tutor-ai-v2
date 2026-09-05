from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class ResponseMode(StrEnum):
    SQL_ONLY = "SQL_ONLY"
    SQL_PLUS_REASONING = "SQL_PLUS_REASONING"
    EXPLANATION_ONLY = "EXPLANATION_ONLY"


class ValidationMode(StrEnum):
    RESULT_EQUIVALENCE = "RESULT_EQUIVALENCE"
    EXPLANATION = "EXPLANATION"
    PLAN_ANALYSIS = "PLAN_ANALYSIS"


class EvidenceKind(StrEnum):
    ISOLATED = "isolated"
    TRANSFER = "transfer"
    COMPOSED = "composed"
    DELAYED_RETRIEVAL = "delayed_retrieval"


class Column(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    type: Literal["integer", "bigint", "numeric", "text", "boolean", "date"]
    nullable: bool


class Index(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    columns: list[str] = Field(min_length=1, max_length=5)


class Table(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    columns: list[Column] = Field(min_length=1, max_length=20)
    primary_key: list[str] = Field(default_factory=list)
    indexes: list[Index] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def valid_columns(self) -> "Table":
        names = [c.name for c in self.columns]
        if len(names) != len(set(names)) or any(key not in names for key in self.primary_key):
            raise ValueError("table columns and primary_key must be consistent")
        if any(next(c for c in self.columns if c.name == key).nullable for key in self.primary_key):
            raise ValueError("primary key columns must be NOT NULL")
        if len({index.name for index in self.indexes}) != len(self.indexes):
            raise ValueError("index names must be unique")
        if any(column not in names for index in self.indexes for column in index.columns):
            raise ValueError("index columns must exist in the table")
        return self


class Environment(StrictModel):
    engine: Literal["PostgreSQL"]
    mode: Literal["AUTO_SETUP"]
    tables: list[Table] = Field(min_length=1, max_length=5)
    visible_data: dict[str, list[list[Any]]]
    hidden_data: dict[str, list[list[Any]]]

    @model_validator(mode="after")
    def validate_data(self) -> "Environment":
        names = [t.name for t in self.tables]
        if len(names) != len(set(names)) or set(self.visible_data) != set(names) or set(self.hidden_data) != set(names):
            raise ValueError("datasets must exactly match declared tables")
        for table in self.tables:
            width = len(table.columns)
            for dataset in (self.visible_data, self.hidden_data):
                if any(len(row) != width for row in dataset[table.name]):
                    raise ValueError(f"rows for {table.name} have invalid arity")
        return self


class Constraint(StrictModel):
    id: str
    type: Literal["uses_table", "grouped_aggregate", "window_function", "recursive_cte"]
    table: str | None = None
    function: str | None = None
    argument: str | None = None
    group_by: list[str] | None = None
    output_alias: str | None = None
    cte_name: str | None = None


class OutputColumn(StrictModel):
    name: str
    type: Literal["integer", "bigint", "numeric", "text", "boolean", "date"]


class RubricCriterion(StrictModel):
    id: str
    criterion: str
    required: bool
    skill_key: str


class Validation(StrictModel):
    mode: ValidationMode
    output_columns: list[OutputColumn] = Field(default_factory=list)
    order_sensitive: bool = False
    numeric_tolerance: Literal[0] = 0
    constraints: list[Constraint] = Field(default_factory=list)
    reasoning_rubric: list[RubricCriterion] = Field(default_factory=list)
    rubric: list[RubricCriterion] = Field(default_factory=list)
    supplied_query: str | None = None


class Task(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=6000)
    primary_skill: str
    secondary_skills: list[str] = Field(default_factory=list, max_length=5)
    difficulty: int = Field(ge=1, le=5)
    response_mode: ResponseMode
    context_tag: str
    evidence_kind: EvidenceKind
    expected_evidence: list[str] = Field(min_length=1)
    hidden_variables: list[dict[str, str]]


class Pedagogy(StrictModel):
    max_hint_level: int = Field(ge=0, le=3)
    allow_solution_reveal: bool


class Private(StrictModel):
    reference_sql: str | None = None
    expected_visible_rows: list[list[Any]] | None = None
    expected_hidden_rows: list[list[Any]] | None = None
    hints: list[str] = Field(min_length=3, max_length=3)
    solution_explanation: str
    rubric_notes: str = ""
    reference_explanation: str | None = None


class ExerciseContract(StrictModel):
    schema_version: Literal[2]
    exercise_id: str
    version: int = Field(ge=1)
    task: Task
    environment: Environment | None
    validation: Validation
    pedagogy: Pedagogy
    private: Private

    @model_validator(mode="after")
    def coherent(self) -> "ExerciseContract":
        mode = self.task.response_mode
        validation = self.validation.mode
        if mode == ResponseMode.SQL_ONLY and validation != ValidationMode.RESULT_EQUIVALENCE:
            raise ValueError("SQL_ONLY requires RESULT_EQUIVALENCE")
        if mode == ResponseMode.SQL_PLUS_REASONING and validation not in {ValidationMode.RESULT_EQUIVALENCE, ValidationMode.PLAN_ANALYSIS}:
            raise ValueError("SQL_PLUS_REASONING has an unsupported validation mode")
        if mode == ResponseMode.EXPLANATION_ONLY and validation == ValidationMode.RESULT_EQUIVALENCE:
            raise ValueError("EXPLANATION_ONLY cannot use RESULT_EQUIVALENCE")
        if validation == ValidationMode.RESULT_EQUIVALENCE and self.environment is None:
            raise ValueError("RESULT_EQUIVALENCE requires an environment")
        if validation == ValidationMode.EXPLANATION and self.environment is not None:
            raise ValueError("EXPLANATION requires no environment")
        if validation == ValidationMode.PLAN_ANALYSIS and self.environment is None:
            raise ValueError("PLAN_ANALYSIS requires an environment")
        return self


class SkillState(StrictModel):
    skill_key: str
    mastery_score: int = Field(default=0, ge=0, le=5)
    evidence_status: Literal["unknown", "self_declared", "observed", "validated", "mastered"] = "unknown"
    confidence: Literal["low", "medium", "high"] = "medium"
    successful_attempts: int = 0
    failed_attempts: int = 0
    hints_required: int = 0
    last_seen: Any | None = None
    retrieval_due_at: Any | None = None
    declared_level: int | None = Field(default=None, ge=0, le=5)
    recurring_errors: list[str] = Field(default_factory=list, max_length=20)
    policy_version: Literal["evidence-v1"] = "evidence-v1"


class PolicyDecision(StrictModel):
    rule: Literal["A", "B", "C", "D1", "D2.1", "D2.2", "E1", "E2", "E3", "F"]
    action: str
    skill_key: str
    reason: str


class ExecutionResult(StrictModel):
    status: Literal["ok", "error", "blocked", "inconclusive"]
    submitted_sql: str
    executed_sql: str | None = None
    extension_ids: list[str] = Field(default_factory=list)
    columns: list[dict[str, str]] = Field(default_factory=list)
    preview_rows: list[list[Any]] = Field(default_factory=list)
    preview_truncated: bool = False
    total_row_count: int | None = None
    complete: bool = False
    sqlstate: str | None = None
    safe_error: str | None = None
    failure_kind: str | None = None
    dataset_hash: str | None = None
    plan_json: Any | None = None


class EvaluationResult(StrictModel):
    decision: Literal["correct", "partial", "incorrect", "learner_sql_error", "blocked", "inconclusive", "pending_review"]
    score: float | None
    execution_status: str
    issues: list[str] = Field(default_factory=list)
    primary_skill_affected: bool = False
    constraint_results: dict[str, str] = Field(default_factory=dict)
    dataset_results: dict[str, str] = Field(default_factory=dict)


class TutorResponse(StrictModel):
    message: str = Field(min_length=1, max_length=2500)
    pedagogical_move: Literal["acknowledge_progress", "ask_guiding_question", "give_concept_hint", "explain_error", "suggest_revision", "provide_partial_scaffold", "recommend_next_exercise", "request_clarification"]
    hint_level: int = Field(ge=0, le=3)
    next_action: Literal["retry", "next_exercise", "wait_for_review", "request_clarification", "switch_to_learning", "session_summary"]
    concepts: list[str] = Field(default_factory=list, max_length=6)
    evidence_ids: list[str] = Field(default_factory=list)


class LLMRequest(StrictModel):
    protocol_version: Literal["protocol-v2"]
    request_id: str
    operation: Literal["decompose_goal", "select_next", "generate_exercise", "review_exercise", "assess_response", "feedback", "chat", "reveal_solution", "summarize"]
    prompt_version: Literal["tutor-v2"]
    policy_version: Literal["evidence-v1"]
    registry_version: int = 1
    context: dict[str, Any]


class LLMResponse(StrictModel):
    protocol_version: Literal["protocol-v2"]
    request_id: str
    operation: LLMRequest.__annotations__["operation"]
    payload: dict[str, Any]


class RubricItem(StrictModel):
    id: str
    result: Literal["met", "partial", "not_met", "not_assessable"]
    evidence_quote: str = Field(default="", max_length=300)
    explanation: str = Field(default="", max_length=500)


class RubricAssessment(StrictModel):
    criteria: list[RubricItem]
    error_kind: Literal["conceptual", "semantic", "syntactic", "modeling", "performance", "edge_case"] | None = None
    primary_skill_affected: bool = False
