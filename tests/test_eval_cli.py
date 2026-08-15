"""End-to-end CLI contracts for declarative safety evaluation."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock
import unittest
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.cli import main  # noqa: E402
from agentharness.eval_contract import EvalContractError  # noqa: E402
from agentharness.eval_runner import EvalCaseResult, EvalRunReport  # noqa: E402


class EvalCliTests(unittest.TestCase):
    def test_default_output_is_unchanged(self) -> None:
        code, stdout, stderr = _run_cli(["eval"])

        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        self.assertIn("PASS PI-001:", stdout)
        self.assertIn("Summary: 3/3 smoke evals passed", stdout)

    def test_all_json_runs_six_executable_cases(self) -> None:
        code, stdout, stderr = _run_cli(["eval", "--all", "--format", "json"])

        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        value = json.loads(stdout)
        self.assertEqual(6, value["summary"]["total"])

    def test_tag_junit_selects_matching_cases(self) -> None:
        code, stdout, stderr = _run_cli(
            ["eval", "--tags", "secret-handling", "--format", "junit"]
        )

        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        self.assertEqual("1", ElementTree.fromstring(stdout).attrib["tests"])

    def test_json_conflicting_selectors_become_machine_argument_error(self) -> None:
        code, stdout, stderr = _run_cli(
            ["eval", "--all", "--cases", "PI-001", "--format", "json"]
        )

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        self.assertEqual(
            "argument.invalid", json.loads(stdout)["error"]["code"]
        )

    def test_junit_invalid_argument_becomes_machine_argument_error(self) -> None:
        code, stdout, stderr = _run_cli(
            ["eval", "--not-an-option", "--format", "junit"]
        )

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        error = ElementTree.fromstring(stdout).find("./testcase/error")
        self.assertIsNotNone(error)
        self.assertEqual("contract", error.attrib["type"])
        self.assertEqual("argument.invalid", error.attrib["message"])

    def test_equals_style_machine_format_normalizes_parse_error(self) -> None:
        code, stdout, stderr = _run_cli(
            ["eval", "--not-an-option", "--format=json"]
        )

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        self.assertEqual("argument.invalid", json.loads(stdout)["error"]["code"])

    def test_text_conflicting_selectors_become_safe_argument_error(self) -> None:
        code, stdout, stderr = _run_cli(
            ["eval", "--all", "--cases", "/private/case"]
        )

        self.assertEqual(2, code)
        self.assertEqual("", stdout)
        self.assertEqual("ERROR: argument.invalid\n", stderr)
        self.assertNotIn("/private/case", stderr)

    def test_invalid_eval_arguments_never_echo_absolute_or_credential_values(self) -> None:
        cases = (
            (
                ["eval", "--unknown", "/home/private/policy.yaml"],
                "text",
                "/home/private/policy.yaml",
            ),
            (
                ["eval", "--unknown", "sk-test-credential", "--format", "json"],
                "json",
                "sk-test-credential",
            ),
            (
                ["eval", "--unknown", "/private/junit.xml", "--format", "junit"],
                "junit",
                "/private/junit.xml",
            ),
        )

        for argv, output_format, secret in cases:
            with self.subTest(output_format=output_format):
                code, stdout, stderr = _run_cli(argv)
                self.assertEqual(2, code)
                self.assertNotIn(secret, stdout + stderr)
                _assert_argument_error(self, output_format, stdout, stderr)

    def test_overlong_and_over_count_eval_argv_fail_without_argparse_output(self) -> None:
        cases = (
            (["eval", "--cases", "x" * 4097], "text"),
            (["eval", "--format", "json"] + ["--unknown"] * 129, "json"),
            (["eval", "--format=junit"] + ["value"] * 129, "junit"),
        )

        for argv, output_format in cases:
            with self.subTest(output_format=output_format):
                code, stdout, stderr = _run_cli(argv)
                self.assertEqual(2, code)
                _assert_argument_error(self, output_format, stdout, stderr)
                self.assertLess(len(stdout + stderr), 512)

    def test_eval_help_remains_standard_argparse_help(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["eval", "--help"])

        self.assertEqual(0, raised.exception.code)
        self.assertIn("usage: agentharness eval", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    def test_non_eval_help_remains_standard_argparse_help(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["--help"])

        self.assertEqual(0, raised.exception.code)
        self.assertIn("usage: agentharness", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    def test_non_eval_argparse_failure_remains_standard(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["validate", "--unknown", "/private/policy.yaml"])

        self.assertEqual(2, raised.exception.code)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("usage: agentharness", stderr.getvalue())
        self.assertIn("unrecognized arguments: --unknown", stderr.getvalue())

    def test_unknown_case_is_safe_json_contract_error(self) -> None:
        code, stdout, stderr = _run_cli(
            ["eval", "--cases", "MISSING", "--format", "json"]
        )

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        self.assertEqual(
            {
                "schema_id": "agentharness.eval.error.v1",
                "result_status": "error",
                "error": {"code": "selection.case_not_found"},
            },
            json.loads(stdout),
        )

    def test_no_tag_match_is_safe_junit_contract_error(self) -> None:
        code, stdout, stderr = _run_cli(
            ["eval", "--tags", "missing", "--format", "junit"]
        )

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        root = ElementTree.fromstring(stdout)
        self.assertEqual("1", root.attrib["tests"])
        self.assertEqual("1", root.attrib["errors"])
        error = root.find("./testcase/error")
        self.assertIsNotNone(error)
        self.assertEqual("contract", error.attrib["type"])
        self.assertEqual("selection.no_tag_match", error.attrib["message"])

    def test_empty_tag_selector_fails_closed(self) -> None:
        code, stdout, stderr = _run_cli(
            ["eval", "--tags", " , ", "--format", "json"]
        )

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        self.assertEqual("selection.no_tag_match", json.loads(stdout)["error"]["code"])

    def test_empty_case_selector_fails_closed(self) -> None:
        code, stdout, stderr = _run_cli(
            ["eval", "--cases", "", "--format", "json"]
        )

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        self.assertEqual("selection.case_not_found", json.loads(stdout)["error"]["code"])

    def test_invalid_policy_is_safe_text_contract_error(self) -> None:
        with _temporary_suite("version: invalid\n") as path:
            code, stdout, stderr = _run_cli(["eval", "--policy", str(path)])

        self.assertEqual(2, code)
        self.assertEqual("", stdout)
        self.assertEqual("ERROR: policy.invalid\n", stderr)
        self.assertNotIn(str(path), stderr)

    def test_invalid_policy_is_safe_json_contract_error(self) -> None:
        with _temporary_suite("version: invalid\n") as path:
            code, stdout, stderr = _run_cli(
                ["eval", "--policy", str(path), "--format", "json"]
            )

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        self.assertEqual(
            {
                "schema_id": "agentharness.eval.error.v1",
                "result_status": "error",
                "error": {"code": "policy.invalid"},
            },
            json.loads(stdout),
        )
        self.assertNotIn(str(path), stdout)

    def test_invalid_policy_is_safe_junit_contract_error(self) -> None:
        with _temporary_suite("version: invalid\n") as path:
            code, stdout, stderr = _run_cli(
                ["eval", "--policy", str(path), "--format", "junit"]
            )

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        root = ElementTree.fromstring(stdout)
        self.assertEqual("agentharness.eval", root.attrib["name"])
        self.assertEqual("1", root.attrib["tests"])
        self.assertEqual("1", root.attrib["errors"])
        error = root.find("./testcase/error")
        self.assertIsNotNone(error)
        self.assertEqual("contract", error.attrib["type"])
        self.assertEqual("policy.invalid", error.attrib["message"])
        self.assertNotIn(str(path), stdout)

    def test_duplicate_suite_ids_fail_closed_without_path_disclosure(self) -> None:
        suite = _suite_with_case("PI-001") + _case_yaml("PI-001")
        with _temporary_suite(suite) as path:
            code, stdout, stderr = _run_cli(
                ["eval", "--suite", str(path), "--format", "json"]
            )

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        self.assertEqual("suite.duplicate_case_id", json.loads(stdout)["error"]["code"])
        self.assertNotIn(str(path), stdout)

    def test_unknown_evaluator_is_safe_text_contract_error(self) -> None:
        suite = _suite_with_case("X-001", evaluator="shell")
        with _temporary_suite(suite) as path:
            code, stdout, stderr = _run_cli(["eval", "--suite", str(path), "--all"])

        self.assertEqual(2, code)
        self.assertEqual("", stdout)
        self.assertEqual("ERROR: evaluator.unknown\n", stderr)
        self.assertNotIn(str(path), stderr)

    def test_unknown_assertion_is_safe_json_contract_error(self) -> None:
        suite = _suite_with_case("PI-001", assertion_op="execute")
        with _temporary_suite(suite) as path:
            code, stdout, stderr = _run_cli(
                ["eval", "--suite", str(path), "--all", "--format", "json"]
            )

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        self.assertEqual("assertion.unknown_operation", json.loads(stdout)["error"]["code"])

    def test_oversized_suite_is_safe_json_contract_error(self) -> None:
        with _temporary_suite("#" + ("x" * (1024 * 1024))) as path:
            code, stdout, stderr = _run_cli(
                ["eval", "--suite", str(path), "--format", "json"]
            )

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        self.assertEqual("suite.too_large", json.loads(stdout)["error"]["code"])

    def test_unsafe_evaluator_output_is_safe_json_contract_error(self) -> None:
        with mock.patch(
            "agentharness.eval_runner.EVALUATORS",
            {"policy_controls": lambda _fixtures, _case: {"unsafe": object()}},
        ):
            code, stdout, stderr = _run_cli(["eval", "--format", "json"])

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        self.assertEqual("evaluator.output_invalid", json.loads(stdout)["error"]["code"])

    def test_internal_exception_uses_internal_junit_error_without_details(self) -> None:
        with mock.patch(
            "agentharness.cli.run_eval_cases",
            side_effect=RuntimeError(f"unexpected detail at {ROOT}"),
        ):
            code, stdout, stderr = _run_cli(["eval", "--format", "junit"])

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        error = ElementTree.fromstring(stdout).find("./testcase/error")
        self.assertIsNotNone(error)
        self.assertEqual("internal", error.attrib["type"])
        self.assertEqual("evaluation.internal_error", error.attrib["message"])
        self.assertNotIn(str(ROOT), stdout)

    def test_machine_stdout_is_one_document_without_diagnostics(self) -> None:
        code, stdout, stderr = _run_cli(["eval", "--format", "json"])

        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        self.assertTrue(stdout.endswith("\n"))
        self.assertEqual("PASS", json.loads(stdout)["result_status"])

    def test_xml_control_character_becomes_safe_junit_contract_error(self) -> None:
        unsafe_report = EvalRunReport(
            (EvalCaseResult("PI-001", "PASS", (), "safe\x01message"),)
        )
        with mock.patch("agentharness.cli.run_eval_cases", return_value=unsafe_report):
            code, stdout, stderr = _run_cli(["eval", "--format", "junit"])

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        error = ElementTree.fromstring(stdout).find("./testcase/error")
        self.assertIsNotNone(error)
        self.assertEqual("contract", error.attrib["type"])
        self.assertEqual("report.invalid_xml_text", error.attrib["message"])

    def test_untrusted_pass_messages_fail_preflight_in_every_format(self) -> None:
        unsafe_messages = (
            ('"safe\\nPASS SPOOF: injected"', "PASS SPOOF"),
            ('"safe\\x01control"', "control"),
            ('"/home/private/eval-output"', "/home/private"),
            ('"sk-test-credential-value"', "sk-test-credential"),
        )
        formats = ("text", "json", "junit")

        for pass_message, leaked_fragment in unsafe_messages:
            for output_format in formats:
                with self.subTest(
                    pass_message=pass_message, output_format=output_format
                ):
                    suite = _suite_with_case(
                        "PI-001", pass_message=pass_message
                    )
                    with _temporary_suite(suite) as path:
                        argv = ["eval", "--suite", str(path), "--all"]
                        if output_format != "text":
                            argv.extend(("--format", output_format))
                        code, stdout, stderr = _run_cli(argv)

                    self.assertEqual(2, code)
                    self.assertNotIn(leaked_fragment, stdout + stderr)
                    _assert_contract_error(
                        self,
                        output_format,
                        stdout,
                        stderr,
                        "case.pass_message_untrusted",
                    )


class EvalCliEndToEndTests(unittest.TestCase):
    def test_installed_style_entry_point_emits_json_without_importing_test_helpers(
        self,
    ) -> None:
        completed = subprocess.run(
            [str(ROOT / "agentharness"), "eval", "--all", "--format", "json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(6, json.loads(completed.stdout)["summary"]["total"])
        self.assertEqual("", completed.stderr)


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _assert_argument_error(
    test: unittest.TestCase, output_format: str, stdout: str, stderr: str
) -> None:
    _assert_contract_error(
        test, output_format, stdout, stderr, "argument.invalid"
    )


def _assert_contract_error(
    test: unittest.TestCase,
    output_format: str,
    stdout: str,
    stderr: str,
    code: str,
) -> None:
    if output_format == "text":
        test.assertEqual("", stdout)
        test.assertEqual(f"ERROR: {code}\n", stderr)
    elif output_format == "json":
        test.assertEqual("", stderr)
        test.assertEqual(code, json.loads(stdout)["error"]["code"])
    else:
        test.assertEqual("", stderr)
        error = ElementTree.fromstring(stdout).find("./testcase/error")
        test.assertIsNotNone(error)
        assert error is not None
        test.assertEqual(code, error.attrib["message"])


class _temporary_suite:
    def __init__(self, source: str) -> None:
        self.source = source
        self.directory: tempfile.TemporaryDirectory[str] | None = None
        self.path: Path | None = None

    def __enter__(self) -> Path:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "suite.yaml"
        self.path.write_text(self.source, encoding="utf-8")
        return self.path

    def __exit__(self, *_: object) -> None:
        assert self.directory is not None
        self.directory.cleanup()


def _suite_with_case(
    case_id: str,
    *,
    evaluator: str = "policy_controls",
    assertion_op: str = "equals",
    pass_message: str | None = None,
) -> str:
    return "version: v1\nname: safe-suite\ncases:\n" + _case_yaml(
        case_id,
        evaluator=evaluator,
        assertion_op=assertion_op,
        pass_message=pass_message,
    )


def _case_yaml(
    case_id: str,
    *,
    evaluator: str = "policy_controls",
    assertion_op: str = "equals",
    pass_message: str | None = None,
) -> str:
    if pass_message is None:
        pass_message = {
            "PI-001": "untrusted content is non-executable and prompt disclosure is guarded",
            "PD-001": "hidden instruction disclosure is guarded",
            "SEC-001": "secrets are never revealed and redaction is required",
        }.get(case_id, "safe message")
    return f"""  - id: {case_id}
    title: Safe case
    tags: [policy]
    evaluator: {evaluator}
    input: {{policy: default}}
    assertions:
      - {{op: {assertion_op}, path: secrets_never_revealed, expected: true}}
    pass_message: {pass_message}
"""


if __name__ == "__main__":
    unittest.main()
