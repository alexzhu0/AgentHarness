"""Tests for the finite declarative assertion engine."""

from __future__ import annotations

import sys
import unittest
from collections.abc import Mapping
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.eval_assertions import (  # noqa: E402
    ASSERTION_OPERATIONS,
    AssertionOutcome,
    evaluate_assertion,
    resolve_eval_path,
)
from agentharness.eval_contract import EvalAssertionSpec, EvalContractError  # noqa: E402


class EvalAssertionTests(unittest.TestCase):
    """Assertions are finite, deterministic checks over evaluator data."""

    def test_registered_operations(self) -> None:
        result = {"flag": True, "words": ["a", "b"], "text": "safe text"}
        cases = [
            (EvalAssertionSpec("equals", "flag", True), True),
            (EvalAssertionSpec("contains", "text", "safe"), True),
            (EvalAssertionSpec("not_contains", "text", "secret"), True),
            (EvalAssertionSpec("contains_all", "words", ["a", "b"]), True),
            (EvalAssertionSpec("path_exists", "flag"), True),
            (EvalAssertionSpec("path_absent", "missing"), True),
            (EvalAssertionSpec("list_non_empty", "words"), True),
        ]
        for assertion, expected in cases:
            with self.subTest(op=assertion.op):
                self.assertEqual(expected, evaluate_assertion(result, assertion).ok)

    def test_registered_operations_fail_for_mismatches(self) -> None:
        result = {"flag": True, "words": ["a"], "text": "safe text"}
        result["empty"] = []
        cases = [
            (EvalAssertionSpec("equals", "flag", False), "assertion.value_mismatch"),
            (
                EvalAssertionSpec("contains", "text", "secret"),
                "assertion.value_mismatch",
            ),
            (
                EvalAssertionSpec("not_contains", "text", "safe"),
                "assertion.value_mismatch",
            ),
            (
                EvalAssertionSpec("contains_all", "words", ["a", "b"]),
                "assertion.value_mismatch",
            ),
            (EvalAssertionSpec("path_exists", "missing"), "assertion.path_missing"),
            (EvalAssertionSpec("path_absent", "flag"), "assertion.path_present"),
            (EvalAssertionSpec("list_non_empty", "empty"), "assertion.list_empty"),
        ]
        for assertion, expected_code in cases:
            with self.subTest(op=assertion.op):
                outcome = evaluate_assertion(result, assertion)
                self.assertFalse(outcome.ok)
                self.assertEqual(expected_code, outcome.code)

    def test_nested_mapping_and_list_paths(self) -> None:
        result = {"outer": {"items": [{"name": "first"}, {"name": "second"}]}}
        self.assertEqual((True, "second"), resolve_eval_path(result, "outer.items.1.name"))
        self.assertEqual((True, {"name": "first"}), resolve_eval_path(result, "outer.items.0"))

    def test_path_rejects_ambiguous_or_unbounded_segments(self) -> None:
        result = {"items": ["zero", "one"], "01": "mapping value"}
        invalid_paths = (
            "",
            ".items",
            "items.",
            "items..0",
            "items.01",
            "items.-1",
            "items.²",
        )
        for path in invalid_paths:
            with self.subTest(path=path):
                self.assertEqual((False, None), resolve_eval_path(result, path))
        self.assertEqual((True, "mapping value"), resolve_eval_path(result, "01"))
        self.assertEqual((False, None), resolve_eval_path(result, "items.2"))
        self.assertEqual(
            (False, None), resolve_eval_path(result, "items." + ("x" * 4097))
        )

    def test_path_never_invokes_attributes_or_magic_methods(self) -> None:
        class Trap:
            def __getattr__(self, name):
                raise AssertionError("attribute lookup executed")

        self.assertEqual(
            (False, None), resolve_eval_path({"trap": Trap()}, "trap.value")
        )

    def test_unknown_operation_fails_closed(self) -> None:
        with self.assertRaisesRegex(EvalContractError, "assertion.unknown_operation"):
            evaluate_assertion({}, EvalAssertionSpec("execute", "x", True))

    def test_unhashable_operation_fails_closed(self) -> None:
        with self.assertRaisesRegex(EvalContractError, "assertion.unknown_operation"):
            evaluate_assertion({}, EvalAssertionSpec([], "x", True))

    def test_registry_contains_exactly_the_reviewed_operations(self) -> None:
        self.assertEqual(
            {
                "equals",
                "contains",
                "not_contains",
                "contains_all",
                "path_exists",
                "path_absent",
                "list_non_empty",
            },
            set(ASSERTION_OPERATIONS),
        )

    def test_recursive_or_oversized_operands_fail_closed(self) -> None:
        cyclic = []
        cyclic.append(cyclic)
        deep = value = []
        for _ in range(17):
            nested = []
            value.append(nested)
            value = nested
        oversized = list(range(1001))

        cases = (
            {"value": cyclic},
            {"value": deep},
            {"value": oversized},
            {"value": 1},
            {"value": "safe"},
        )
        expected_values = ([], [], [], cyclic, "x" * 4097)
        for result, expected in zip(cases, expected_values):
            with self.subTest(result=result):
                outcome = evaluate_assertion(
                    result, EvalAssertionSpec("equals", "value", expected)
                )
                self.assertEqual(
                    AssertionOutcome(False, "assertion.operand_invalid"), outcome
                )

    def test_path_rejects_hostile_mapping_subclasses_without_hooks(self) -> None:
        class HostileMapping(Mapping):
            def __iter__(self):
                raise AssertionError("mapping iteration executed")

            def __len__(self):
                raise AssertionError("mapping length executed")

            def __getitem__(self, key):
                raise AssertionError("mapping lookup executed")

        class HostileDict(dict):
            def __contains__(self, key):
                raise AssertionError("dict membership executed")

            def __getitem__(self, key):
                raise AssertionError("dict lookup executed")

        for value in (HostileMapping(), HostileDict(value=True)):
            with self.subTest(value_type=type(value).__name__):
                self.assertEqual((False, None), resolve_eval_path(value, "value"))

    def test_operand_types_fail_closed(self) -> None:
        cases = [
            EvalAssertionSpec("contains", "value", "x"),
            EvalAssertionSpec("not_contains", "value", "x"),
            EvalAssertionSpec("contains_all", "value", ["x"]),
            EvalAssertionSpec("list_non_empty", "value"),
        ]
        for assertion in cases:
            with self.subTest(op=assertion.op):
                outcome = evaluate_assertion({"value": {"x": True}}, assertion)
                self.assertEqual(
                    AssertionOutcome(False, "assertion.operand_invalid"), outcome
                )

    def test_path_exists_distinguishes_missing_from_null(self) -> None:
        result = {"null_value": None}
        self.assertEqual(
            AssertionOutcome(True, "assertion.ok"),
            evaluate_assertion(result, EvalAssertionSpec("path_exists", "null_value")),
        )
        self.assertEqual(
            AssertionOutcome(False, "assertion.path_missing"),
            evaluate_assertion(result, EvalAssertionSpec("equals", "missing", None)),
        )


if __name__ == "__main__":
    unittest.main()
