"""Bounded data contracts for declarative safety evaluation suites."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


MAX_SUITE_BYTES = 1024 * 1024
MAX_CASES = 1000
MAX_ASSERTIONS_PER_CASE = 32
MAX_IDENTIFIER_LENGTH = 128
MAX_TITLE_LENGTH = 512
MAX_TAGS_PER_CASE = 32
MAX_SCALAR_LENGTH = 4096
MAX_COLLECTION_LENGTH = 1000


class EvalContractError(ValueError):
    """A stable, public-safe reason that an evaluation contract was rejected."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class EvalAssertionSpec:
    """One finite assertion against a named evaluator result."""

    op: str
    path: str
    expected: Any = None


@dataclass(frozen=True)
class EvalCaseSpec:
    """One normalized, executable declarative evaluation case."""

    case_id: str
    title: str
    tags: tuple[str, ...]
    evaluator: str
    input: Mapping[str, Any]
    assertions: tuple[EvalAssertionSpec, ...]
    pass_message: str


def is_bounded_json_value(
    value: Any,
    *,
    max_depth: int = 16,
    max_nodes: int = 4096,
    max_collection_length: int = MAX_COLLECTION_LENGTH,
) -> bool:
    """Return whether a value is finite JSON-compatible data within local bounds."""

    seen: set[int] = set()
    nodes = 0

    def visit(current: Any, depth: int) -> bool:
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes or depth > max_depth:
            return False
        if current is None or isinstance(current, (bool, int)):
            return True
        if isinstance(current, float):
            return math.isfinite(current)
        if isinstance(current, str):
            return len(current) <= MAX_SCALAR_LENGTH
        if isinstance(current, Mapping):
            if len(current) > max_collection_length:
                return False
            marker = id(current)
            if marker in seen:
                return False
            seen.add(marker)
            try:
                return all(
                    isinstance(key, str)
                    and len(key) <= MAX_IDENTIFIER_LENGTH
                    and visit(item, depth + 1)
                    for key, item in current.items()
                )
            finally:
                seen.remove(marker)
        if isinstance(current, (list, tuple)):
            if len(current) > max_collection_length:
                return False
            marker = id(current)
            if marker in seen:
                return False
            seen.add(marker)
            try:
                return all(visit(item, depth + 1) for item in current)
            finally:
                seen.remove(marker)
        return False

    return visit(value, 0)
