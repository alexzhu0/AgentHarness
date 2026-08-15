"""Finite, non-executable assertions over bounded evaluator results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any, Callable

from .eval_contract import EvalAssertionSpec, EvalContractError, MAX_SCALAR_LENGTH


@dataclass(frozen=True)
class AssertionOutcome:
    """The public, safe result of evaluating one assertion."""

    ok: bool
    code: str


_OK = AssertionOutcome(True, "assertion.ok")
_VALUE_MISMATCH = AssertionOutcome(False, "assertion.value_mismatch")
_PATH_MISSING = AssertionOutcome(False, "assertion.path_missing")
_PATH_PRESENT = AssertionOutcome(False, "assertion.path_present")
_OPERAND_INVALID = AssertionOutcome(False, "assertion.operand_invalid")
_LIST_EMPTY = AssertionOutcome(False, "assertion.list_empty")


def resolve_eval_path(value: Any, path: str) -> tuple[bool, Any]:
    """Resolve a deliberately small dotted path without attribute access.

    Mapping segments are looked up by key. List segments are ASCII decimal
    indexes, with no leading zeroes except for the index ``0``. No operation
    in this resolver evaluates names, attributes, expressions, or methods.
    """

    if not isinstance(path, str) or not path or len(path) > MAX_SCALAR_LENGTH:
        return False, None
    segments = path.split(".")
    if any(not segment for segment in segments):
        return False, None

    current = value
    for segment in segments:
        if isinstance(current, Mapping) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and _is_list_index(segment):
            index = int(segment)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def evaluate_assertion(
    result: Any, assertion: EvalAssertionSpec
) -> AssertionOutcome:
    """Evaluate one assertion through the finite operation registry."""

    if not isinstance(assertion, EvalAssertionSpec):
        raise EvalContractError("assertion.invalid")
    operation = ASSERTION_OPERATIONS.get(assertion.op)
    if operation is None:
        raise EvalContractError("assertion.unknown_operation")
    return operation(result, assertion.path, assertion.expected)


def _is_list_index(segment: str) -> bool:
    return (
        segment.isascii()
        and segment.isdigit()
        and (segment == "0" or not segment.startswith("0"))
    )


def _resolve(result: Any, path: str) -> tuple[bool, Any]:
    return resolve_eval_path(result, path)


def _equals(result: Any, path: str, expected: Any) -> AssertionOutcome:
    found, actual = _resolve(result, path)
    if not found:
        return _PATH_MISSING
    if not _is_safe_json_value(actual) or not _is_safe_json_value(expected):
        return _OPERAND_INVALID
    return _OK if _safe_equal(actual, expected) else _VALUE_MISMATCH


def _contains(result: Any, path: str, expected: Any) -> AssertionOutcome:
    found, actual = _resolve(result, path)
    if not found:
        return _PATH_MISSING
    if type(actual) is not str or type(expected) is not str:
        return _OPERAND_INVALID
    return _OK if expected in actual else _VALUE_MISMATCH


def _not_contains(result: Any, path: str, expected: Any) -> AssertionOutcome:
    found, actual = _resolve(result, path)
    if not found:
        return _PATH_MISSING
    if type(actual) is not str or type(expected) is not str:
        return _OPERAND_INVALID
    return _OK if expected not in actual else _VALUE_MISMATCH


def _contains_all(result: Any, path: str, expected: Any) -> AssertionOutcome:
    found, actual = _resolve(result, path)
    if not found:
        return _PATH_MISSING
    if (
        type(actual) is not list
        or type(expected) is not list
        or not _is_safe_json_value(actual)
        or not _is_safe_json_value(expected)
    ):
        return _OPERAND_INVALID
    all_present = all(
        any(_safe_equal(item, wanted) for item in actual) for wanted in expected
    )
    return _OK if all_present else _VALUE_MISMATCH


def _path_exists(result: Any, path: str, expected: Any) -> AssertionOutcome:
    found, _ = _resolve(result, path)
    return _OK if found else _PATH_MISSING


def _path_absent(result: Any, path: str, expected: Any) -> AssertionOutcome:
    found, _ = _resolve(result, path)
    return _PATH_PRESENT if found else _OK


def _list_non_empty(result: Any, path: str, expected: Any) -> AssertionOutcome:
    found, actual = _resolve(result, path)
    if not found:
        return _PATH_MISSING
    if type(actual) is not list or not _is_safe_json_value(actual):
        return _OPERAND_INVALID
    return _OK if actual else _LIST_EMPTY


def _is_safe_json_value(value: Any) -> bool:
    """Check values before comparisons so arbitrary magic methods cannot run."""

    value_type = type(value)
    if value is None or value_type is bool or value_type is int:
        return True
    if value_type is float:
        return math.isfinite(value)
    if value_type is str:
        return len(value) <= MAX_SCALAR_LENGTH
    if value_type in (list, tuple):
        return all(_is_safe_json_value(item) for item in value)
    if value_type is dict:
        return all(
            type(key) is str
            and len(key) <= MAX_SCALAR_LENGTH
            and _is_safe_json_value(item)
            for key, item in value.items()
        )
    return False


def _safe_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        if left.keys() != right.keys():
            return False
        return all(_safe_equal(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(
            _safe_equal(item, other) for item, other in zip(left, right)
        )
    return left == right


ASSERTION_OPERATIONS: dict[
    str, Callable[[Any, str, Any], AssertionOutcome]
] = {
    "equals": _equals,
    "contains": _contains,
    "not_contains": _not_contains,
    "contains_all": _contains_all,
    "path_exists": _path_exists,
    "path_absent": _path_absent,
    "list_non_empty": _list_non_empty,
}
