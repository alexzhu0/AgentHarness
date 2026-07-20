from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.cli import main
from agentharness.handoff_inspector import inspect_handoff_bus
from agentharness.yamlio import load_yaml


HANDOFF_BUS_ROOT = ROOT / "examples" / "agent_bus_handoff"
ADAPTER_REGISTRY_BUS_ROOT = ROOT / "examples" / "agent_bus_adapter_registry"
BASE_BUS_ROOT = ROOT / "examples" / "agent_bus"
HANDOFF_REPORT_PATH = Path("handoffs") / "T008-handoff-report.yaml"


class HandoffInspectorTests(unittest.TestCase):
    def test_inspector_summarizes_valid_handoff_fixture(self):
        inspection, report = inspect_handoff_bus(HANDOFF_BUS_ROOT)

        self.assertEqual([], report.errors)
        self.assertIsNotNone(inspection)
        self.assertEqual(
            {
                "reports": 1,
                "total": 5,
                "handoff_ready": 2,
                "blocked": 2,
                "unsupported": 1,
                "result_status": "not_executed",
            },
            inspection["summary"],
        )
        statuses = {
            handoff["request_id"]: handoff["status"]
            for handoff in inspection["reports"][0]["handoffs"]
        }
        self.assertEqual("handoff_ready", statuses["TR-read"])
        self.assertEqual("handoff_ready", statuses["TR-approve-delete"])
        self.assertEqual("unsupported", statuses["TR-read-unsupported-intent"])
        self.assertEqual("blocked", statuses["TR-missing-approval-delete"])
        self.assertEqual("blocked", statuses["TR-deny-unknown"])

    def test_handoff_inspect_cli_text_output(self):
        code, output = _run_cli(["handoff", "inspect", str(HANDOFF_BUS_ROOT)])

        self.assertEqual(0, code)
        self.assertTrue(output.startswith("PASS handoff inspection\n"))
        self.assertIn(
            "reports=1 total=5 handoff_ready=2 blocked=2 unsupported=1 "
            "result_status=not_executed",
            output,
        )
        self.assertIn("- TR-read: handoff_ready", output)
        self.assertIn("- TR-deny-unknown: blocked", output)

    def test_handoff_inspect_cli_json_output(self):
        code, output = _run_cli(
            ["handoff", "inspect", str(HANDOFF_BUS_ROOT), "--json"]
        )

        self.assertEqual(0, code)
        payload = json.loads(output)
        self.assertEqual(True, payload["ok"])
        self.assertNotIn("bus_root", payload)
        self.assertEqual({"ok", "reports", "summary", "warnings"}, set(payload))
        self.assertEqual(
            {
                "reports": 1,
                "total": 5,
                "handoff_ready": 2,
                "blocked": 2,
                "unsupported": 1,
                "result_status": "not_executed",
            },
            payload["summary"],
        )
        self.assertEqual(
            {
                "attempt",
                "handoffs",
                "objective_ref",
                "path",
                "result_status",
                "summary",
                "task_id",
            },
            set(payload["reports"][0]),
        )
        self.assertEqual(
            {
                "blocked_reason",
                "category",
                "execution_allowed_by_preflight",
                "expected_preflight_decision",
                "handoff_ready",
                "intent",
                "request_id",
                "result_status",
                "status",
                "target_scope",
                "tool_name",
                "unsupported_reason",
            },
            set(payload["reports"][0]["handoffs"][0]),
        )

    def test_success_text_output_contains_no_absolute_host_path(self):
        code, output = _run_cli(["handoff", "inspect", str(ADAPTER_REGISTRY_BUS_ROOT)])

        self.assertEqual(0, code)
        self.assertEqual("PASS handoff inspection", output.splitlines()[0])
        _assert_no_absolute_host_path(output, str(ADAPTER_REGISTRY_BUS_ROOT))

    def test_success_json_output_contains_no_absolute_host_path_or_bus_root(self):
        code, output = _run_cli(
            ["handoff", "inspect", str(ADAPTER_REGISTRY_BUS_ROOT), "--json"]
        )

        self.assertEqual(0, code)
        payload = json.loads(output)
        self.assertNotIn("bus_root", payload)
        _assert_no_absolute_host_path(payload, str(ADAPTER_REGISTRY_BUS_ROOT))

    def test_failure_text_for_temp_fixture_contains_no_raw_temp_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus"
            shutil.copytree(BASE_BUS_ROOT, bus_root)

            code, output = _run_cli(["handoff", "inspect", str(bus_root)])

            self.assertEqual(1, code)
            self.assertIn("FAIL handoff inspection", output)
            self.assertIn("no execution handoff report referenced", output)
            _assert_no_absolute_host_path(output, tmpdir, str(bus_root))

    def test_failure_json_for_temp_fixture_contains_no_raw_temp_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus"
            shutil.copytree(BASE_BUS_ROOT, bus_root)

            code, output = _run_cli(["handoff", "inspect", str(bus_root), "--json"])

            self.assertEqual(1, code)
            payload = json.loads(output)
            self.assertEqual(False, payload["ok"])
            self.assertIn(
                "no execution handoff report referenced", "\n".join(payload["errors"])
            )
            _assert_no_absolute_host_path(payload, tmpdir, str(bus_root))

    def test_malformed_handoff_yaml_failure_sanitizes_parser_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_handoff"
            shutil.copytree(HANDOFF_BUS_ROOT, bus_root)
            (bus_root / HANDOFF_REPORT_PATH).write_text(
                "handoffs: [\n", encoding="utf-8"
            )

            code, output = _run_cli(["handoff", "inspect", str(bus_root), "--json"])

            self.assertEqual(1, code)
            payload = json.loads(output)
            errors = "\n".join(payload["errors"])
            self.assertIn("could not parse execution handoff report", errors)
            self.assertIn("<bus_root>", errors)
            _assert_no_absolute_host_path(payload, tmpdir, str(bus_root))

    def test_handoff_inspect_fails_when_no_handoff_report_is_referenced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus"
            shutil.copytree(BASE_BUS_ROOT, bus_root)

            code, output = _run_cli(["handoff", "inspect", str(bus_root)])

        self.assertEqual(1, code)
        self.assertIn("FAIL handoff inspection", output)
        self.assertIn("no execution handoff report referenced", output)

    def test_handoff_inspect_rejects_forged_handoff_digest(self):
        code, output = _run_mutated_handoff_bus(
            lambda bus_root: _mutate_handoff(
                bus_root,
                "TR-read",
                lambda handoff: handoff["subject"].__setitem__(
                    "tool_gate_digest", "sha256:0"
                ),
            )
        )

        self.assertEqual(1, code)
        self.assertIn("FAIL handoff inspection", output)
        self.assertIn("subject", output)

    def test_handoff_inspect_rejects_blocked_marked_ready(self):
        code, output = _run_mutated_handoff_bus(
            lambda bus_root: _mutate_handoff(
                bus_root,
                "TR-deny-unknown",
                lambda handoff: _make_handoff_ready(handoff),
            )
        )

        self.assertEqual(1, code)
        self.assertIn("gate", output)

    def test_handoff_inspect_rejects_unsupported_marked_ready(self):
        code, output = _run_mutated_handoff_bus(
            lambda bus_root: _mutate_handoff(
                bus_root,
                "TR-read-unsupported-intent",
                lambda handoff: _make_handoff_ready(handoff),
            )
        )

        self.assertEqual(1, code)
        self.assertIn("gate", output)

    def test_handoff_inspect_rejects_executed_result_status(self):
        code, output = _run_mutated_handoff_bus(
            lambda bus_root: _mutate_report(
                bus_root,
                lambda report: report.__setitem__("result_status", "executed"),
            )
        )

        self.assertEqual(1, code)
        self.assertIn("result_status", output)

    def test_handoff_inspect_rejects_duplicate_request_id(self):
        def mutate(report):
            report["handoffs"][1]["request_id"] = report["handoffs"][0]["request_id"]

        code, output = _run_mutated_handoff_bus(
            lambda bus_root: _mutate_report(bus_root, mutate)
        )

        self.assertEqual(1, code)
        self.assertIn("request_id", output)
        self.assertIn("unique", output)

    def test_handoff_inspect_rejects_unknown_request_id(self):
        code, output = _run_mutated_handoff_bus(
            lambda bus_root: _mutate_handoff(
                bus_root,
                "TR-read",
                lambda handoff: handoff.__setitem__("request_id", "TR-unknown"),
            )
        )

        self.assertEqual(1, code)
        self.assertIn("request_id", output)
        self.assertIn("tool gate report", output)

    def test_handoff_inspect_rejects_handoff_report_path_traversal(self):
        def mutate(bus_root):
            _mutate_ledger_event(
                bus_root,
                "E003",
                lambda event: event.__setitem__(
                    "execution_handoff_report_path", "../T008-handoff-report.yaml"
                ),
            )

        code, output = _run_mutated_handoff_bus(mutate)

        self.assertEqual(1, code)
        self.assertIn("execution_handoff_report_path", output)
        self.assertIn("bus_root", output)

    def test_handoff_inspect_rejects_adapter_spec_path_traversal(self):
        code, output = _run_mutated_handoff_bus(
            lambda bus_root: _mutate_report(
                bus_root,
                lambda report: report.__setitem__("adapter_spec_path", "../adapter.yaml"),
            )
        )

        self.assertEqual(1, code)
        self.assertIn("adapter_spec_path", output)
        self.assertIn("bus_root", output)


def _run_mutated_handoff_bus(mutate):
    with tempfile.TemporaryDirectory() as tmpdir:
        bus_root = Path(tmpdir) / "agent_bus_handoff"
        shutil.copytree(HANDOFF_BUS_ROOT, bus_root)
        mutate(bus_root)
        return _run_cli(["handoff", "inspect", str(bus_root)])


def _run_cli(argv):
    stream = StringIO()
    with redirect_stdout(stream):
        code = main(argv)
    return code, stream.getvalue()


def _mutate_report(bus_root, mutate):
    path = bus_root / HANDOFF_REPORT_PATH
    report = load_yaml(path)
    mutate(report)
    _write_yaml(path, report)


def _mutate_handoff(bus_root, request_id, mutate):
    def mutate_report(report):
        for handoff in report["handoffs"]:
            if handoff.get("request_id") == request_id:
                mutate(handoff)
                return
        raise AssertionError(f"request not found: {request_id}")

    _mutate_report(bus_root, mutate_report)


def _make_handoff_ready(handoff):
    handoff["gate"]["handoff_ready"] = True
    handoff["gate"]["blocked_reason"] = None
    handoff["gate"]["unsupported_reason"] = None


def _mutate_ledger_event(bus_root, event_id, mutate):
    ledger_path = bus_root / "ledger.jsonl"
    events = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for event in events:
        if event.get("event_id") == event_id:
            mutate(event)
            break
    else:
        raise AssertionError(f"event not found: {event_id}")
    payload = "\n".join(
        json.dumps(event, separators=(",", ":"), sort_keys=True) for event in events
    )
    ledger_path.write_text(payload + "\n", encoding="utf-8")


def _write_yaml(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def _assert_no_absolute_host_path(value, *extra_forbidden):
    strings = list(_strings_in(value))
    forbidden = [str(ROOT), "/home/", "/tmp/", *extra_forbidden]
    for item in strings:
        for token in forbidden:
            if token:
                if token in item:
                    raise AssertionError(
                        f"found host path token {token!r} in {item!r}"
                    )


def _strings_in(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings_in(key)
            yield from _strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings_in(item)


if __name__ == "__main__":
    unittest.main()
