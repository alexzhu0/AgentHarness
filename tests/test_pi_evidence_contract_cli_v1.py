from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.cli import main
from agentharness.pi_evidence_contract_v1 import (
    MAX_JSON_DOCUMENT_BYTES,
    MAX_OBSERVATIONS,
    build_pi_observation_batch_v1,
    verify_pi_evidence_response_v1,
)


BUS_ROOT = ROOT / "examples" / "agent_bus_adapter_registry"


class PiEvidenceContractCliV1Tests(unittest.TestCase):
    def test_valid_request_is_deterministic_stdout_only_and_not_executed(self) -> None:
        request = _request("call-001")

        with patch("subprocess.run", side_effect=AssertionError("execution forbidden")):
            first_code, first_stdout, first_stderr = _run_cli(request, BUS_ROOT)
            second_code, second_stdout, second_stderr = _run_cli(request, BUS_ROOT)

        self.assertEqual(0, first_code)
        self.assertEqual(0, second_code)
        self.assertEqual("", first_stderr)
        self.assertEqual("", second_stderr)
        self.assertEqual(first_stdout, second_stdout)
        response = json.loads(first_stdout)
        self.assertEqual("not_executed", response["result_status"])
        self.assertEqual("complete", response["batch"]["evaluation_status"])
        self.assertTrue(verify_pi_evidence_response_v1(response, request)["valid"])
        self.assertNotIn(str(ROOT), first_stdout)

    def test_maximum_observation_request_emits_one_bounded_not_executed_document(self) -> None:
        request = build_pi_observation_batch_v1(
            [
                {
                    "tool_call_id": f"call-{index:02d}",
                    "tool_name": "read_workspace",
                    "arguments": {"path": f"docs/item-{index:02d}.md"},
                }
                for index in range(MAX_OBSERVATIONS)
            ]
        )

        with patch("subprocess.run", side_effect=AssertionError("execution forbidden")):
            code, stdout, stderr = _run_cli(request, BUS_ROOT)

        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        response = _one_bounded_json_document(stdout)
        self.assertEqual(MAX_OBSERVATIONS, len(response["batch"]["results"]))
        self.assertEqual([], _non_not_executed_status_paths(response))
        self.assertTrue(verify_pi_evidence_response_v1(response, request)["valid"])

    def test_missing_bus_returns_verified_rejected_response_without_path_leak(self) -> None:
        request = _request("call-missing-bus")
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "private" / "missing-bus"
            code, stdout, stderr = _run_cli(request, missing)

        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        response = json.loads(stdout)
        self.assertEqual("rejected", response["batch"]["evaluation_status"])
        self.assertEqual(["snapshot.bus_unreadable"], response["errors"])
        self.assertTrue(verify_pi_evidence_response_v1(response, request)["valid"])
        self.assertNotIn(str(missing), stdout)
        self.assertNotIn(tmpdir, stdout)

    def test_malformed_and_duplicate_stdin_fail_closed_as_json(self) -> None:
        malformed_documents = [
            "",
            "{",
            '{"kind":"first","kind":"second"}',
        ]
        for raw in malformed_documents:
            with self.subTest(size=len(raw)):
                code, stdout, stderr = _run_raw(raw, BUS_ROOT)
                self.assertEqual(2, code)
                self.assertEqual("", stderr)
                response = json.loads(stdout)
                self.assertEqual("not_executed", response["result_status"])
                self.assertEqual("rejected", response["batch"]["evaluation_status"])
                self.assertEqual(["request.invalid"], response["errors"])

        code, stdout, stderr = _run_bytes(b"\xff", BUS_ROOT)
        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        self.assertEqual(["request.invalid"], json.loads(stdout)["errors"])

    def test_oversized_stdin_emits_one_bounded_not_executed_rejection_document(self) -> None:
        code, stdout, stderr = _run_raw("x" * (MAX_JSON_DOCUMENT_BYTES + 1), BUS_ROOT)

        self.assertEqual(2, code)
        self.assertEqual("", stderr)
        response = _one_bounded_json_document(stdout)
        self.assertEqual("rejected", response["batch"]["evaluation_status"])
        self.assertEqual(["request.invalid"], response["errors"])
        self.assertEqual([], _non_not_executed_status_paths(response))

    def test_digest_only_current_call_cannot_prove_allow_candidate(self) -> None:
        # The Pi-side call would be:
        # tool_call_id="call-digest-only", tool_name="read_workspace",
        # arguments={"path":"README.md"}. Only its arguments digest crosses
        # the wire; that digest cannot independently prove repository scope.
        request = _request("call-digest-only")

        code, stdout, stderr = _run_cli(request, BUS_ROOT)

        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        response = _one_bounded_json_document(stdout)
        result = response["batch"]["results"][0]
        self.assertEqual("error", result["decision"])
        self.assertEqual("mapping_claim_not_independently_derivable", result["reason_code"])
        self.assertIsNone(result["evidence_binding"])
        self.assertNotEqual("allow_candidate", result["decision"])
        self.assertTrue(verify_pi_evidence_response_v1(response, request)["valid"])

    def test_unexpected_evaluator_error_is_bounded_json_without_exception_text(self) -> None:
        request = _request("call-internal-error")
        exception_text = "secret /home/alex/private token=sk-proj-secret12345678"
        with patch(
            "agentharness.cli.evaluate_pi_evidence_request_v1",
            side_effect=RuntimeError(exception_text),
        ):
            code, stdout, stderr = _run_cli(request, BUS_ROOT)

        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        response = _one_bounded_json_document(stdout)
        self.assertEqual("not_executed", response["result_status"])
        self.assertEqual("rejected", response["batch"]["evaluation_status"])
        self.assertEqual(["evaluation.internal_error"], response["errors"])
        self.assertTrue(verify_pi_evidence_response_v1(response, request)["valid"])
        self.assertNotIn(exception_text, stdout)
        self.assertNotIn("secret", stdout)
        self.assertNotIn("/home/alex", stdout)
        self.assertNotIn("sk-proj-secret12345678", stdout)

    def test_forbidden_output_or_execution_flags_are_rejected(self) -> None:
        for flag in ["--out", "--write", "--execute", "--run", "--allow"]:
            with self.subTest(flag=flag):
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        main(["pi", "evidence-evaluate-v1", str(BUS_ROOT), flag])
                self.assertEqual(2, raised.exception.code)
                self.assertEqual("", stdout.getvalue())

    def test_help_mentions_versioned_evaluator(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                main(["--help"])
        self.assertEqual(0, raised.exception.code)
        self.assertIn("pi evidence-evaluate-v1", stdout.getvalue())


def _request(call_id: str) -> dict:
    return build_pi_observation_batch_v1(
        [
            {
                "tool_call_id": call_id,
                "tool_name": "read_workspace",
                "arguments": {"path": "README.md"},
            }
        ]
    )


def _run_cli(request: dict, bus_root: Path) -> tuple[int, str, str]:
    return _run_raw(json.dumps(request, separators=(",", ":"), sort_keys=True), bus_root)


def _run_raw(raw: str, bus_root: Path) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with patch("sys.stdin", StringIO(raw)), redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(["pi", "evidence-evaluate-v1", str(bus_root)])
    return code, stdout.getvalue(), stderr.getvalue()


def _run_bytes(raw: bytes, bus_root: Path) -> tuple[int, str, str]:
    class BinaryStdin:
        buffer = BytesIO(raw)

    stdout = StringIO()
    stderr = StringIO()
    with patch("sys.stdin", BinaryStdin()), redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(["pi", "evidence-evaluate-v1", str(bus_root)])
    return code, stdout.getvalue(), stderr.getvalue()


def _one_bounded_json_document(stdout: str) -> dict:
    encoded = stdout.encode("utf-8")
    if len(encoded) > MAX_JSON_DOCUMENT_BYTES:
        raise AssertionError(f"stdout is unbounded: {len(encoded)} bytes")
    document, end = json.JSONDecoder().raw_decode(stdout)
    if stdout[end:].strip():
        raise AssertionError("stdout contains more than one JSON document")
    if not isinstance(document, dict):
        raise AssertionError("stdout JSON document is not an object")
    return document


def _non_not_executed_status_paths(value, path: str = "$") -> list[str]:
    invalid = []
    if isinstance(value, dict):
        if "result_status" in value and value["result_status"] != "not_executed":
            invalid.append(path)
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                invalid.extend(_non_not_executed_status_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, (dict, list)):
                invalid.extend(_non_not_executed_status_paths(child, f"{path}[{index}]"))
    return invalid


if __name__ == "__main__":
    unittest.main()
