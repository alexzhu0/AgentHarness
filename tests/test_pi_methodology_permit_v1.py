from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.cli import main
from agentharness.pi_evidence_contract_v1 import (
    build_pi_observation_batch_v1,
)
from agentharness.pi_methodology_permit_v1 import (
    MAX_PERMIT_DOCUMENT_BYTES,
    PERMIT_POLICY_VERSION,
    PERMIT_QUESTION,
    PERMIT_RESPONSE_KIND,
    PERMIT_TOOL_NAME,
    build_methodology_permit_request_v1,
    evaluate_methodology_permit_request_v1,
    verify_methodology_permit_response_v1,
)


class PiMethodologyPermitV1Tests(unittest.TestCase):
    def test_exact_request_gets_deterministic_bound_permit_once(self) -> None:
        request = _request("permit-call-001")

        with patch("subprocess.run", side_effect=AssertionError("execution forbidden")):
            first = evaluate_methodology_permit_request_v1(request)
            second = evaluate_methodology_permit_request_v1(copy.deepcopy(request))

        self.assertEqual(first, second)
        self.assertEqual(PERMIT_RESPONSE_KIND, first["kind"])
        self.assertEqual("permit_once", first["decision"])
        self.assertEqual("permit.exact_methodology_lookup", first["reason_code"])
        self.assertEqual("not_executed", first["result_status"])
        self.assertEqual([], first["errors"])
        self.assertEqual("permit-call-001", first["call_binding"]["tool_call_id"])
        self.assertEqual(PERMIT_TOOL_NAME, first["call_binding"]["tool_name"])
        self.assertEqual(PERMIT_POLICY_VERSION, first["policy_binding"]["policy_version"])
        self.assertTrue(first["constraints"]["single_use"])
        self.assertEqual(
            "agent_session_current_tool_call",
            first["constraints"]["single_use_scope"],
        )
        self.assertFalse(first["constraints"]["network_allowed"])
        self.assertFalse(first["constraints"]["write_allowed"])
        self.assertFalse(first["constraints"]["subprocess_allowed"])
        self.assertFalse(first["constraints"]["follow_up_allowed"])
        self.assertTrue(verify_methodology_permit_response_v1(first, request)["valid"])
        serialized = json.dumps(first, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(PERMIT_QUESTION, serialized)
        self.assertNotIn(str(ROOT), serialized)
        self.assertNotIn("http://", serialized)
        self.assertNotIn("https://", serialized)

    def test_every_non_exact_request_is_denied_without_input_disclosure(self) -> None:
        cases = {
            "wrong tool": lambda request: _binding(request).__setitem__("tool_name", "win9_run"),
            "wrong call binding": lambda request: _binding(request).__setitem__("tool_call_id", "other-call"),
            "digest mismatch": lambda request: _binding(request).__setitem__("arguments_digest", f"sha256:{'f' * 64}"),
            "canonicalization mismatch": lambda request: _binding(request).__setitem__("arguments_canonicalization_id", "other"),
            "policy mismatch": lambda request: request.__setitem__("policy_version", "other"),
            "artifact commit mismatch": lambda request: request["artifact_binding"].__setitem__("pi_commit", "0" * 40),
            "artifact path mismatch": lambda request: request["artifact_binding"].__setitem__("logical_path", "../METHODOLOGY.md"),
            "artifact digest mismatch": lambda request: request["artifact_binding"].__setitem__("sha256", f"sha256:{'0' * 64}"),
            "missing question": lambda request: request.__setitem__("arguments", {}),
            "extra stage": lambda request: request.__setitem__("arguments", {"question": PERMIT_QUESTION, "stage": "L1"}),
            "extra level reordered": lambda request: request.__setitem__("arguments", {"level": "L1", "question": PERMIT_QUESTION}),
            "empty question": lambda request: request.__setitem__("arguments", {"question": ""}),
            "overlong question": lambda request: request.__setitem__("arguments", {"question": "x" * 10000}),
            "url question": lambda request: request.__setitem__("arguments", {"question": "https://example.invalid/secret"}),
            "path question": lambda request: request.__setitem__("arguments", {"question": "/home/private/METHODOLOGY.md"}),
            "credential question": lambda request: request.__setitem__(
                "arguments",
                {"question": "token=" + "sk-" + "proj-secret12345678"},
            ),
            "customer question": lambda request: request.__setitem__("arguments", {"question": "客户A的预算是多少？"}),
            "duplicate observations": _duplicate_observation,
        }

        for name, mutate in cases.items():
            with self.subTest(name=name):
                request = _request("permit-call-denied")
                mutate(request)
                response = evaluate_methodology_permit_request_v1(request)
                self.assertEqual("deny", response["decision"])
                self.assertEqual("not_executed", response["result_status"])
                self.assertNotEqual("permit_once", response["decision"])
                serialized = json.dumps(response, ensure_ascii=False, sort_keys=True)
                self.assertNotIn("example.invalid", serialized)
                self.assertNotIn("/home/private", serialized)
                self.assertNotIn("sk-" + "proj-secret12345678", serialized)
                self.assertNotIn("客户A", serialized)

    def test_cli_is_stdout_only_canonical_and_denies_policy_mismatch(self) -> None:
        request = _request("permit-call-cli")
        code, stdout, stderr = _run_cli(request)
        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        payload = json.loads(stdout)
        self.assertEqual("permit_once", payload["decision"])
        self.assertEqual(stdout.strip(), json.dumps(payload, separators=(",", ":"), sort_keys=True))

        request["policy_version"] = "stale"
        code, stdout, stderr = _run_cli(request)
        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        self.assertEqual("deny", json.loads(stdout)["decision"])

    def test_cli_malformed_duplicate_invalid_utf8_and_oversized_fail_closed(self) -> None:
        documents: list[str | bytes] = [
            "",
            "{",
            '{"kind":"first","kind":"second"}',
            b"\xff",
            "x" * (MAX_PERMIT_DOCUMENT_BYTES + 1),
        ]
        for raw in documents:
            with self.subTest(size=len(raw)):
                code, stdout, stderr = _run_raw(raw)
                self.assertEqual(2, code)
                self.assertEqual("", stderr)
                payload = json.loads(stdout)
                self.assertEqual("deny", payload["decision"])
                self.assertEqual("not_executed", payload["result_status"])

    def test_cli_internal_error_is_sanitized_deterministic_json(self) -> None:
        secret = (
            "secret /home/example-user/private token="
            + "sk-"
            + "proj-secret12345678"
        )
        with patch(
            "agentharness.cli.evaluate_methodology_permit_request_v1",
            side_effect=RuntimeError(secret),
        ):
            code, stdout, stderr = _run_cli(_request("permit-call-error"))
        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        payload = json.loads(stdout)
        self.assertEqual("deny", payload["decision"])
        self.assertNotIn(secret, stdout)
        self.assertNotIn("/home/example-user", stdout)
        self.assertNotIn("sk-proj", stdout)

    def test_cli_rejects_writer_execution_and_authority_flags(self) -> None:
        for flag in ["--out", "--write", "--execute", "--run", "--allow", "--permit"]:
            with self.subTest(flag=flag):
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        main(["pi", "methodology-permit-v1", flag])
                self.assertEqual(2, raised.exception.code)
                self.assertEqual("", stdout.getvalue())


def _request(call_id: str) -> dict:
    arguments = {"question": PERMIT_QUESTION}
    observations = build_pi_observation_batch_v1(
        [{"tool_call_id": call_id, "tool_name": PERMIT_TOOL_NAME, "arguments": arguments}]
    )
    return build_methodology_permit_request_v1(observations, arguments)


def _binding(request: dict) -> dict:
    return request["observation_batch"]["batch"]["observations"][0]["call_binding"]


def _duplicate_observation(request: dict) -> None:
    observations = request["observation_batch"]["batch"]["observations"]
    observations.append(copy.deepcopy(observations[0]))


def _run_cli(request: dict) -> tuple[int, str, str]:
    return _run_raw(json.dumps(request, separators=(",", ":"), sort_keys=True))


def _run_raw(raw: str | bytes) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    stdin = _BinaryStdin(raw) if isinstance(raw, bytes) else StringIO(raw)
    with patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(["pi", "methodology-permit-v1"])
    return code, stdout.getvalue(), stderr.getvalue()


class _BinaryStdin:
    def __init__(self, raw: bytes):
        self.buffer = BytesIO(raw)


if __name__ == "__main__":
    unittest.main()
