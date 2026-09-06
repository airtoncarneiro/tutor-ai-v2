"""Contract v2 validation scenarios for malformed provider output."""

import pytest
from pydantic import ValidationError

from sql_tutor.exercises import ContractError, validate_contract


def test_extra_fields_are_rejected(contract_factory):
    with pytest.raises(ValidationError, match="unexpected"):
        validate_contract(contract_factory(extra_fields=True))


def test_invalid_enum_is_rejected(contract_factory):
    with pytest.raises(ValidationError, match="response_mode"):
        validate_contract(contract_factory(enum_invalid=True))


def test_type_mismatch_is_rejected(contract_factory):
    with pytest.raises(ValidationError, match="exercise_id"):
        validate_contract(contract_factory(type_mismatch=True))


def test_unsupported_skill_is_rejected(contract_factory):
    with pytest.raises(ContractError, match="Unsupported skill"):
        validate_contract(contract_factory(unsupported_skill=True))


def test_incompatible_response_and_validation_modes_are_rejected(contract_factory):
    with pytest.raises(ValidationError, match="SQL_ONLY requires RESULT_EQUIVALENCE"):
        validate_contract(contract_factory(invalid_combo=True))


def test_grouped_aggregate_alias_is_optional(contract_factory):
    contract = validate_contract(contract_factory(alias_optional=True))

    assert contract.validation.constraints[0].output_alias is None