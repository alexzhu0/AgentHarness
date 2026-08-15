"""Finite, non-executable assertions over bounded evaluator results."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable

from .eval_contract import (
    EvalAssertionSpec,
    EvalContractError,
    MAX_COLLECTION_LENGTH,
    MAX_IDENTIFIER_LENGTH,
    MAX_SCALAR_LENGTH,
)


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
        if type(current) is dict and segment in current:
            current = current[segment]
        elif type(current) is list and _is_list_index(segment):
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
    if type(assertion.op) is not str:
        raise EvalContractError("assertion.unknown_operation")
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
    if (
        type(actual) is not str
        or type(expected) is not str
        or not _is_safe_json_value(actual)
        or not _is_safe_json_value(expected)
    ):
        return _OPERAND_INVALID
    return _OK if expected in actual else _VALUE_MISMATCH


def _not_contains(result: Any, path: str, expected: Any) -> AssertionOutcome:
    found, actual = _resolve(result, path)
    if not found:
        return _PATH_MISSING
    if (
        type(actual) is not str
        or type(expected) is not str
        or not _is_safe_json_value(actual)
        or not _is_safe_json_value(expected)
    ):
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
    """Check bounded inert JSON values without recursion or user hooks."""

    # Use an explicit stack so hostile depth/cycles cannot exhaust Python's
    # call stack. Exact built-in containers exclude overridden protocol hooks.
    stack: list[tuple[Any, int, bool]] = [(value, 0, False)]
    active: set[int] = set()
    nodes = 0
    while stack:
        current, depth, exiting = stack.pop()
        if exiting:
            active.remove(id(current))
            continue

        nodes += 1
        if nodes > 4096 or depth > 16:
            return False
        value_type = type(current)
        if current is None or value_type is bool or value_type is int:
            continue
        if value_type is float:
            if not math.isfinite(current):
                return False
            continue
        if value_type is str:
            if len(current) > MAX_SCALAR_LENGTH:
                return False
            continue
        if value_type not in (dict, list, tuple):
            return False
        if len(current) > MAX_COLLECTION_LENGTH:
            return False

        marker = id(current)
        if marker in active:
            return False
        active.add(marker)
        stack.append((current, depth, True))
        if value_type is dict:
            items = tuple(current.items())
            for key, item in reversed(items):
                if (
                    type(key) is not str
                    or len(key) > MAX_IDENTIFIER_LENGTH
                ):
                    return False
                stack.append((item, depth + 1, False))
        else:
            for item in reversed(current):
                stack.append((item, depth + 1, False))
    return True


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
