from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import copy
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.audit_contract import NOT_EXECUTED
from agentharness.cli import main


OBSERVATIONS_PATH = ROOT / "examples" / "pi_tool_call_mapping" / "pi_tool_call_observations.json"
EXPECTATIONS_PATH = ROOT / "examples" / "pi_tool_call_mapping" / "expected_mapping.json"
REGISTRY_BUS_ROOT = ROOT / "examples" / "agent_bus_adapter_registry"
DIRECT_HANDOFF_BUS_ROOT = ROOT / "examples" / "agent_bus_handoff"
BASE_COMMAND = [
    "pi",
    "contract-check",
    str(OBSERVATIONS_PATH),
    str(EXPECTATIONS_PATH),
    str(REGISTRY_BUS_ROOT),
]


class PiToolCallMappingCliTests(unittest.TestCase):
    def test_contract_check_cli_outputs_json_and_exits_zero(self) -> None:
        code, stdout, stderr = _run_cli(BASE_COMMAND)

        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        payload = json.loads(stdout)
        self.assertEqual("pi_tool_call_mapping_validation_report", payload["kind"])
        self.assertEqual("build_pi_tool_call_mapping_report", payload["source"])
        self.assertEqual(NOT_EXECUTED, payload["result_status"])
        self.assertIs(payload["ok"], True)
        self.assertEqual([], payload["errors"])
        self.assertEqual(
            [
                ("pi-obs-001-read-workspace", "allow_candidate"),
                ("pi-obs-002-read-unsupported-intent", "unsupported"),
                ("pi-obs-003-edit-write-like", "unsupported"),
                ("pi-obs-004-bash-shell", "block"),
                ("pi-obs-005-malformed-missing-tool", "error"),
                ("pi-obs-006-read-outside-scope", "unsupported"),
            ],
            [(item["observation_id"], item["decision"]) for item in payload["decisions"]],
        )
        self.assertEqual([], _raw_host_path_matches(payload))

    def test_contract_check_cli_output_is_deterministic(self) -> None:
        first_code, first_stdout, first_stderr = _run_cli(BASE_COMMAND)
        second_code, second_stdout, second_stderr = _run_cli(BASE_COMMAND)

        self.assertEqual(0, first_code)
        self.assertEqual(0, second_code)
        self.assertEqual("", first_stderr)
        self.assertEqual("", second_stderr)
        self.assertEqual(json.loads(first_stdout), json.loads(second_stdout))
        self.assertEqual(_canonical_json(json.loads(first_stdout)), _canonical_json(json.loads(second_stdout)))

    def test_missing_files_return_json_failure_and_exit_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_obs = Path(tmp) / "missing-observations.json"
            missing_exp = Path(tmp) / "missing-expectations.json"
            cases = [
                [str(missing_obs), str(EXPECTATIONS_PATH), str(REGISTRY_BUS_ROOT)],
                [str(OBSERVATIONS_PATH), str(missing_exp), str(REGISTRY_BUS_ROOT)],
            ]
            for args in cases:
                with self.subTest(args=args):
                    code, stdout, stderr = _run_cli(["pi", "contract-check", *args])
                    payload = json.loads(stdout)

                    self.assertEqual(1, code)
                    self.assertEqual("", stderr)
                    self.assertIs(payload["ok"], False)
                    self.assertTrue(payload["errors"])
                    self.assertEqual([], _raw_host_path_matches(payload))

    def test_legacy_non_registry_bus_returns_json_failure(self) -> None:
        code, stdout, stderr = _run_cli(
            [
                "pi",
                "contract-check",
                str(OBSERVATIONS_PATH),
                str(EXPECTATIONS_PATH),
                str(DIRECT_HANDOFF_BUS_ROOT),
            ]
        )
        payload = json.loads(stdout)

        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        self.assertIs(payload["ok"], False)
        self.assertTrue(payload["errors"])

    def test_tampered_expectation_returns_json_failure(self) -> None:
        with _temporary_payloads() as paths:
            expectations = _load_json(paths["expectations"])
            expectations["mapping_expectations"][0]["expected_decision"] = "block"
            _write_json(paths["expectations"], expectations)

            code, stdout, stderr = _run_cli(
                [
                    "pi",
                    "contract-check",
                    str(paths["observations"]),
                    str(paths["expectations"]),
                    str(REGISTRY_BUS_ROOT),
                ]
            )

        payload = json.loads(stdout)
        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        self.assertIs(payload["ok"], False)
        self.assertEqual("allow_candidate", payload["decisions"][0]["decision"])
        self.assertNotIn('"allow"', _canonical_json(payload["decisions"][0]))

    def test_wrong_ready_request_semantic_mismatch_returns_json_failure(self) -> None:
        with _temporary_payloads() as paths:
            observations = _load_json(paths["observations"])
            observations["observations"][0]["agentharness_refs_if_available"][
                "request_id_candidate"
            ] = "TR-approve-delete"
            _write_json(paths["observations"], observations)

            code, stdout, stderr = _run_cli(
                [
                    "pi",
                    "contract-check",
                    str(paths["observations"]),
                    str(paths["expectations"]),
                    str(REGISTRY_BUS_ROOT),
                ]
            )

        payload = json.loads(stdout)
        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        self.assertIs(payload["ok"], False)
        self.assertEqual("error", payload["decisions"][0]["decision"])
        self.assertTrue(
            any("request_semantic_mismatch" in error for error in payload["errors"]),
            payload["errors"],
        )

    def test_path_like_observation_value_is_sanitized_in_cli_json(self) -> None:
        with _temporary_payloads() as paths:
            observations = _load_json(paths["observations"])
            observations["observations"][0]["tool_name"] = "/tmp/leaky_tool"
            _write_json(paths["observations"], observations)

            code, stdout, stderr = _run_cli(
                [
                    "pi",
                    "contract-check",
                    str(paths["observations"]),
                    str(paths["expectations"]),
                    str(REGISTRY_BUS_ROOT),
                ]
            )

        payload = json.loads(stdout)
        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        self.assertIs(payload["ok"], False)
        self.assertNotIn("/tmp/leaky_tool", stdout)
        self.assertEqual([], _raw_host_path_matches(payload))
        self.assertEqual(
            "<path>",
            payload["decisions"][0]["evidence_binding"]["observation_request"]["tool_name"],
        )

    def test_invalid_vocabulary_containing_allow_fails(self) -> None:
        with _temporary_payloads() as paths:
            expectations = _load_json(paths["expectations"])
            expectations["decision_vocabulary"] = [
                "allow_candidate",
                "allow",
                "block",
                "unsupported",
                "error",
            ]
            _write_json(paths["expectations"], expectations)

            code, stdout, stderr = _run_cli(
                [
                    "pi",
                    "contract-check",
                    str(paths["observations"]),
                    str(paths["expectations"]),
                    str(REGISTRY_BUS_ROOT),
                ]
            )

        payload = json.loads(stdout)
        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        self.assertIs(payload["ok"], False)
        self.assertTrue(
            any("decision_vocabulary" in error for error in payload["errors"]),
            payload["errors"],
        )

    def test_forbidden_file_output_and_action_flags_are_rejected(self) -> None:
        rejected_flags = [
            ["--out", "contract.json"],
            ["--write"],
            ["--save"],
            ["--execute"],
            ["--dispatch"],
            ["--submit"],
            ["--run"],
            ["--mutate"],
            ["--sign"],
            ["--timestamp"],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "contract.json"
            for flag_args in rejected_flags:
                args = list(flag_args)
                if args[0] == "--out":
                    args[1] = str(out_path)
                with self.subTest(flag_args=args):
                    stdout = StringIO()
                    stderr = StringIO()
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as raised:
                            main([*BASE_COMMAND, *args])
                    self.assertEqual(2, raised.exception.code)
                    self.assertEqual("", stdout.getvalue())
                    self.assertIn("unrecognized arguments", stderr.getvalue())
                    self.assertFalse(out_path.exists())

    def test_help_mentions_pi_contract_check(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                main(["--help"])

        self.assertEqual(0, raised.exception.code)
        self.assertIn("pi contract-check", stdout.getvalue())


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return copy.deepcopy(value)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        encoding="utf-8",
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _raw_host_path_matches(value: Mapping[str, Any]) -> list[str]:
    payload = _canonical_json(value)
    needles = [
        str(ROOT),
        str(REGISTRY_BUS_ROOT),
        "/home/",
        "/tmp/",
        "/tmp/leaky_tool",
        "\\\\server",
        "C:\\\\Users",
    ]
    return [needle for needle in needles if needle in payload]


def _temporary_payloads():
    class _Payloads:
        def __enter__(self) -> dict[str, Path]:
            self._temp = tempfile.TemporaryDirectory()
            root = Path(self._temp.name)
            self.paths = {
                "observations": root / "pi_tool_call_observations.json",
                "expectations": root / "expected_mapping.json",
            }
            self.paths["observations"].write_text(
                OBSERVATIONS_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            self.paths["expectations"].write_text(
                EXPECTATIONS_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            return self.paths

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            self._temp.cleanup()

    return _Payloads()


if __name__ == "__main__":
    unittest.main()
