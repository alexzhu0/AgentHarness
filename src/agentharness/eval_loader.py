"""Strict loading and deterministic selection for declarative eval suites."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .eval_contract import (
    EvalAssertionSpec,
    EvalCaseSpec,
    EvalContractError,
    MAX_ASSERTIONS_PER_CASE,
    MAX_CASES,
    MAX_IDENTIFIER_LENGTH,
    MAX_SCALAR_LENGTH,
    MAX_SUITE_BYTES,
    MAX_TAGS_PER_CASE,
    MAX_TITLE_LENGTH,
    is_bounded_json_value,
)
from .yamlio import YamlBoundedLoadError, load_yaml_bounded_strict


_SUITE_FIELDS = frozenset({"version", "name", "notes", "scoring", "cases"})
_NARRATIVE_CASE_FIELDS = frozenset(
    {
        "id",
        "category",
        "risk_level",
        "user_task",
        "context",
        "forbidden_tools",
        "expected_behavior",
        "pass_criteria",
    }
)
_DECLARATIVE_CASE_FIELDS = frozenset(
    {"title", "tags", "evaluator", "input", "assertions", "pass_message"}
)
_CASE_FIELDS = _NARRATIVE_CASE_FIELDS | _DECLARATIVE_CASE_FIELDS
_ASSERTION_FIELDS = frozenset({"op", "path", "expected"})
_SUITE_METADATA_FIELDS = frozenset({"name", "notes", "scoring"})
_YAML_ERROR_CODES = {
    "too_large": "suite.too_large",
    "duplicate_mapping_key": "suite.duplicate_mapping_key",
    "read_failed": "suite.read_failed",
    "invalid_utf8": "suite.invalid_utf8",
    "malformed": "suite.malformed_yaml",
}


def load_eval_suite(path: str | Path) -> tuple[EvalCaseSpec, ...]:
    """Load executable eval cases from one bounded, strict YAML suite."""

    try:
        suite = load_yaml_bounded_strict(path, max_bytes=MAX_SUITE_BYTES)
    except YamlBoundedLoadError as exc:
        raise EvalContractError(
            _YAML_ERROR_CODES.get(exc.code, "suite.malformed_yaml")
        ) from None

    if not isinstance(suite, Mapping):
        raise EvalContractError("suite.invalid_root")
    _reject_unknown_fields(suite, _SUITE_FIELDS, "suite.unknown_field")
    _require_bounded_string(suite.get("version"), "suite.version_invalid")
    _validate_suite_metadata(suite)
    raw_cases = suite.get("cases")
    if not isinstance(raw_cases, list):
        raise EvalContractError("suite.cases_invalid")
    if len(raw_cases) > MAX_CASES:
        raise EvalContractError("suite.too_many_cases")

    executable_cases: list[EvalCaseSpec] = []
    known_ids: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            raise EvalContractError("case.invalid")
        _reject_unknown_fields(raw_case, _CASE_FIELDS, "case.unknown_field")
        case_id = raw_case.get("id")
        _require_identifier(case_id, "case.id_invalid")
        if case_id in known_ids:
            raise EvalContractError("suite.duplicate_case_id")
        known_ids.add(case_id)

        present_declarative_fields = _DECLARATIVE_CASE_FIELDS.intersection(raw_case)
        if not present_declarative_fields:
            continue
        if present_declarative_fields != _DECLARATIVE_CASE_FIELDS:
            raise EvalContractError("case.incomplete_declarative_contract")
        executable_cases.append(_normalize_case(raw_case, case_id))

    return tuple(executable_cases)


def select_eval_cases(
    cases: Iterable[EvalCaseSpec],
    *,
    case_ids: Iterable[str] | None = None,
    tags: Iterable[str] | None = None,
    select_all: bool = False,
) -> tuple[EvalCaseSpec, ...]:
    """Select cases by one explicit mode, or leave caller-provided cases intact."""

    ordered_cases = tuple(cases)
    requested_ids = _normalize_selection_values(case_ids, "selection.case_not_found")
    requested_tags = _normalize_selection_values(tags, "selection.no_tag_match")
    active_modes = sum((bool(requested_ids), bool(requested_tags), bool(select_all)))
    if active_modes > 1:
        raise EvalContractError("selection.conflict")
    if select_all or active_modes == 0:
        return ordered_cases
    if requested_ids:
        by_id = {case.case_id: case for case in ordered_cases}
        selected: list[EvalCaseSpec] = []
        for case_id in requested_ids:
            case = by_id.get(case_id)
            if case is None:
                raise EvalContractError("selection.case_not_found")
            selected.append(case)
        return tuple(selected)

    requested_tag_set = frozenset(requested_tags)
    selected = tuple(
        case for case in ordered_cases if requested_tag_set.intersection(case.tags)
    )
    if not selected:
        raise EvalContractError("selection.no_tag_match")
    return selected


def _normalize_case(raw_case: Mapping[str, Any], case_id: str) -> EvalCaseSpec:
    title = raw_case["title"]
    if not isinstance(title, str) or not title or len(title) > MAX_TITLE_LENGTH:
        raise EvalContractError("case.title_invalid")
    tags = raw_case["tags"]
    if not isinstance(tags, list) or not tags or len(tags) > MAX_TAGS_PER_CASE:
        raise EvalContractError("case.tags_invalid")
    if any(
        not _is_safe_identifier(tag)
        for tag in tags
    ):
        raise EvalContractError("case.tags_invalid")
    if len(set(tags)) != len(tags):
        raise EvalContractError("case.tags_invalid")
    evaluator = raw_case["evaluator"]
    _require_identifier(evaluator, "case.evaluator_invalid")
    input_value = raw_case["input"]
    if not isinstance(input_value, Mapping) or not is_bounded_json_value(input_value):
        raise EvalContractError("case.input_invalid")
    assertions = raw_case["assertions"]
    if (
        not isinstance(assertions, list)
        or not assertions
        or len(assertions) > MAX_ASSERTIONS_PER_CASE
    ):
        raise EvalContractError("case.assertions_invalid")
    pass_message = raw_case["pass_message"]
    _require_bounded_string(pass_message, "case.pass_message_invalid")
    return EvalCaseSpec(
        case_id=case_id,
        title=title,
        tags=tuple(tags),
        evaluator=evaluator,
        input=dict(input_value),
        assertions=tuple(_normalize_assertion(assertion) for assertion in assertions),
        pass_message=pass_message,
    )


def _normalize_assertion(raw_assertion: Any) -> EvalAssertionSpec:
    if not isinstance(raw_assertion, Mapping):
        raise EvalContractError("assertion.invalid")
    _reject_unknown_fields(raw_assertion, _ASSERTION_FIELDS, "assertion.unknown_field")
    op = raw_assertion.get("op")
    path = raw_assertion.get("path")
    _require_identifier(op, "assertion.op_invalid")
    _require_bounded_string(path, "assertion.path_invalid")
    expected = raw_assertion.get("expected")
    if not is_bounded_json_value(expected):
        raise EvalContractError("assertion.expected_invalid")
    return EvalAssertionSpec(op=op, path=path, expected=expected)


def _normalize_selection_values(
    values: Iterable[str] | None, error_code: str
) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    try:
        normalized = tuple(values)
    except TypeError:
        raise EvalContractError(error_code) from None
    if any(
        not _is_safe_identifier(value)
        for value in normalized
    ):
        raise EvalContractError(error_code)
    return normalized


def _reject_unknown_fields(
    value: Mapping[Any, Any], allowed_fields: frozenset[str], error_code: str
) -> None:
    if any(not isinstance(key, str) or key not in allowed_fields for key in value):
        raise EvalContractError(error_code)


def _require_identifier(value: Any, error_code: str) -> None:
    if not _is_safe_identifier(value):
        raise EvalContractError(error_code)


def _require_bounded_string(value: Any, error_code: str) -> None:
    if not isinstance(value, str) or not value or len(value) > MAX_SCALAR_LENGTH:
        raise EvalContractError(error_code)


def _validate_suite_metadata(suite: Mapping[str, Any]) -> None:
    for field in _SUITE_METADATA_FIELDS:
        if field in suite and not is_bounded_json_value(suite[field]):
            raise EvalContractError("suite.metadata_invalid")


def _is_safe_identifier(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_IDENTIFIER_LENGTH
        or not value.isascii()
        or not value[0].isalnum()
    ):
        return False
    return all(character.isalnum() or character in "_-" for character in value)
