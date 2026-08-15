"""Deterministic, bounded serializers for declarative evaluation reports."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from xml.etree import ElementTree

from .eval_contract import EvalContractError, MAX_CASES, MAX_IDENTIFIER_LENGTH, MAX_SCALAR_LENGTH
from .eval_runner import EvalCaseResult, EvalRunReport


SCHEMA_ID = "agentharness.eval.report.v1"
MAX_REPORT_BYTES = 1024 * 1024
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_XML_ALLOWED_CONTROL_RANGES = ((0x9, 0x9), (0xA, 0xA), (0xD, 0xD))


@dataclass(frozen=True)
class _NormalizedCase:
    case_id: str
    status: str
    reason_codes: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class _NormalizedReport:
    result_status: str
    cases: tuple[_NormalizedCase, ...]
    passed: int
    failed: int

    @property
    def total(self) -> int:
        return len(self.cases)


def format_eval_text(report: EvalRunReport) -> str:
    """Render the legacy human-readable report from the normalized report."""

    normalized = _normalize_report(report)
    lines = [
        f"{case.status} {case.case_id}: {case.message}"
        for case in normalized.cases
    ]
    lines.append(
        f"Summary: {normalized.passed}/{normalized.total} smoke evals passed"
    )
    output = "\n".join(lines) + "\n"
    _check_output_size(output)
    return output


def format_eval_json(report: EvalRunReport) -> str:
    """Render exactly one deterministic, machine-readable JSON document."""

    normalized = _normalize_report(report)
    payload: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "result_status": normalized.result_status,
        "summary": {
            "failed": normalized.failed,
            "passed": normalized.passed,
            "total": normalized.total,
        },
        "cases": [
            {
                "case_id": case.case_id,
                "status": case.status,
                "reason_codes": list(case.reason_codes),
                "message": case.message,
            }
            for case in normalized.cases
        ],
    }
    try:
        output = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise EvalContractError("report.invalid") from None
    _check_output_size(output)
    return output


def format_eval_junit(report: EvalRunReport) -> str:
    """Render one deterministic JUnit XML document without raw failure values."""

    normalized = _normalize_report(report)
    for case in normalized.cases:
        _reject_xml_controls(case.case_id)
        _reject_xml_controls(case.message)
        for reason_code in case.reason_codes:
            _reject_xml_controls(reason_code)

    root = ElementTree.Element(
        "testsuite",
        {
            "name": "agentharness.eval",
            "tests": str(normalized.total),
            "failures": str(normalized.failed),
        },
    )
    for case in normalized.cases:
        testcase = ElementTree.SubElement(
            root,
            "testcase",
            {"classname": "agentharness.eval", "name": case.case_id},
        )
        if case.status == "FAIL":
            ElementTree.SubElement(
                testcase,
                "failure",
                {
                    "type": "assertion",
                    "message": case.reason_codes[0],
                },
            )
    output = ElementTree.tostring(root, encoding="unicode", short_empty_elements=True) + "\n"
    _check_output_size(output)
    return output


def _normalize_report(report: EvalRunReport) -> _NormalizedReport:
    """Copy only bounded, report-owned fields into a format-neutral shape."""

    if type(report) is not EvalRunReport:
        raise EvalContractError("report.invalid")
    results = report.results
    if type(results) is not tuple or len(results) > MAX_CASES:
        raise EvalContractError("report.too_large")

    normalized: list[_NormalizedCase] = []
    for result in results:
        if type(result) is not EvalCaseResult:
            raise EvalContractError("report.invalid")
        case_id = _bounded_identifier(result.case_id, "report.invalid")
        status = result.status
        if status not in {"PASS", "FAIL"}:
            raise EvalContractError("report.invalid")
        if type(result.reason_codes) is not tuple or len(result.reason_codes) > MAX_CASES:
            raise EvalContractError("report.invalid")
        reason_codes = tuple(
            _bounded_identifier(code, "report.invalid") for code in result.reason_codes
        )
        message = _bounded_text(result.message, "report.invalid")
        if status == "FAIL":
            if not reason_codes:
                raise EvalContractError("report.invalid")
            # Failure details are intentionally never serialized: they may contain
            # assertion values, paths, or exception text. The stable reason code is
            # the only failure message exposed by any report format.
            message = reason_codes[0]
        elif reason_codes:
            raise EvalContractError("report.invalid")
        normalized.append(_NormalizedCase(case_id, status, reason_codes, message))

    passed = sum(case.status == "PASS" for case in normalized)
    failed = len(normalized) - passed
    return _NormalizedReport("PASS" if failed == 0 else "FAIL", tuple(normalized), passed, failed)


def _bounded_identifier(value: Any, error_code: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > MAX_IDENTIFIER_LENGTH
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise EvalContractError(error_code)
    return value


def _bounded_text(value: Any, error_code: str) -> str:
    if type(value) is not str or not value:
        raise EvalContractError(error_code)
    if len(value) > MAX_SCALAR_LENGTH:
        raise EvalContractError("report.too_large")
    try:
        if len(value.encode("utf-8")) > MAX_SCALAR_LENGTH:
            raise EvalContractError("report.too_large")
    except UnicodeError:
        raise EvalContractError(error_code) from None
    return value


def _reject_xml_controls(value: str) -> None:
    for character in value:
        codepoint = ord(character)
        if codepoint < 0x20 and not any(
            low <= codepoint <= high for low, high in _XML_ALLOWED_CONTROL_RANGES
        ):
            raise EvalContractError("report.invalid_xml_text")


def _check_output_size(output: str) -> None:
    try:
        size = len(output.encode("utf-8"))
    except UnicodeError:
        raise EvalContractError("report.invalid") from None
    if size > MAX_REPORT_BYTES:
        raise EvalContractError("report.too_large")


__all__ = ["format_eval_text", "format_eval_json", "format_eval_junit"]
