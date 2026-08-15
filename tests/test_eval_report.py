"""Tests for deterministic declarative evaluation report formats."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from xml.etree import ElementTree
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.eval_contract import EvalContractError  # noqa: E402
from agentharness.eval_report import (  # noqa: E402
    format_eval_json,
    format_eval_junit,
    format_eval_text,
)
from agentharness.eval_runner import EvalCaseResult, EvalRunReport  # noqa: E402


def _passed_report() -> EvalRunReport:
    return EvalRunReport(
        (
            EvalCaseResult(
                "PI-001",
                "PASS",
                (),
                "untrusted content is non-executable and prompt disclosure is guarded",
            ),
            EvalCaseResult(
                "PD-001", "PASS", (), "hidden instruction disclosure is guarded"
            ),
            EvalCaseResult(
                "SEC-001",
                "PASS",
                (),
                "secrets are never revealed and redaction is required",
            ),
        )
    )


def _failed_report(
    *, message: str = "credential-like-value", code: str = "assertion.value_mismatch"
) -> EvalRunReport:
    return EvalRunReport(
        (EvalCaseResult("PI-001", "FAIL", (code,), message),)
    )


class EvalReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = _passed_report()

    def test_text_preserves_legacy_output(self) -> None:
        self.assertEqual(
            "PASS PI-001: untrusted content is non-executable and prompt disclosure is guarded\n"
            "PASS PD-001: hidden instruction disclosure is guarded\n"
            "PASS SEC-001: secrets are never revealed and redaction is required\n"
            "Summary: 3/3 smoke evals passed\n",
            format_eval_text(self.report),
        )

    def test_json_is_one_versioned_deterministic_document(self) -> None:
        first = format_eval_json(self.report)
        second = format_eval_json(self.report)
        self.assertEqual(first, second)
        value = json.loads(first)
        self.assertEqual("agentharness.eval.report.v1", value["schema_id"])
        self.assertEqual({"schema_id", "result_status", "summary", "cases"}, set(value))
        self.assertNotIn(str(ROOT), first)
        self.assertTrue(first.endswith("\n"))

    def test_junit_is_valid_and_has_one_case_per_result(self) -> None:
        root = ElementTree.fromstring(format_eval_junit(self.report))
        self.assertEqual("agentharness.eval", root.attrib["name"])
        self.assertEqual("3", root.attrib["tests"])
        self.assertEqual(3, len(root.findall("testcase")))

    def test_failure_formats_emit_reason_code_not_raw_value(self) -> None:
        report = _failed_report()
        for output in (
            format_eval_text(report),
            format_eval_json(report),
            format_eval_junit(report),
        ):
            self.assertIn("assertion.value_mismatch", output)
            self.assertNotIn("credential-like-value", output)

    def test_junit_rejects_xml_disallowed_controls_with_safe_code(self) -> None:
        report = EvalRunReport(
            (EvalCaseResult("PI-001", "PASS", (), "invalid\x01text"),)
        )
        with self.assertRaisesRegex(EvalContractError, "report.invalid_xml_text"):
            format_eval_junit(report)

    def test_report_rejects_oversized_case_message(self) -> None:
        report = EvalRunReport(
            (EvalCaseResult("PI-001", "PASS", (), "x" * 4097),)
        )
        with self.assertRaisesRegex(EvalContractError, "report.too_large"):
            format_eval_json(report)


if __name__ == "__main__":
    unittest.main()
