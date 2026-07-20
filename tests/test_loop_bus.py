from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.loop_bus import (
    parse_ledger,
    validate_bus,
    validate_event_chain,
    validate_task,
)
from agentharness.cli import main
from agentharness.yamlio import load_yaml


BUS_ROOT = ROOT / "examples" / "agent_bus"
TASK_PATH = BUS_ROOT / "tasks" / "T001-loop-smoke.yaml"
LEDGER_PATH = BUS_ROOT / "ledger.jsonl"
TOOL_GATE_BUS_ROOT = ROOT / "examples" / "agent_bus_tool_gate"
TOOL_GATE_TASK_PATH = TOOL_GATE_BUS_ROOT / "tasks" / "T005-tool-gate-audit.yaml"
TOOL_GATE_LEDGER_PATH = TOOL_GATE_BUS_ROOT / "ledger.jsonl"
APPROVAL_BUS_ROOT = ROOT / "examples" / "agent_bus_approval"
PREFLIGHT_BUS_ROOT = ROOT / "examples" / "agent_bus_preflight"
HANDOFF_BUS_ROOT = ROOT / "examples" / "agent_bus_handoff"


class LoopBusTests(unittest.TestCase):
    def setUp(self):
        self.task = load_yaml(TASK_PATH)
        self.events, report = parse_ledger(LEDGER_PATH)
        self.assertEqual([], report.errors)

    def test_valid_fixture_passes(self):
        report = validate_bus(BUS_ROOT)

        self.assertEqual([], report.errors)

    def test_tool_gate_fixture_passes(self):
        report = validate_bus(TOOL_GATE_BUS_ROOT)

        self.assertEqual([], report.errors)

    def test_approval_fixture_passes(self):
        report = validate_bus(APPROVAL_BUS_ROOT)

        self.assertEqual([], report.errors)

    def test_preflight_fixture_passes(self):
        report = validate_bus(PREFLIGHT_BUS_ROOT)

        self.assertEqual([], report.errors)

    def test_handoff_fixture_passes(self):
        report = validate_bus(HANDOFF_BUS_ROOT)

        self.assertEqual([], report.errors)

    def test_missing_bus_cli_sanitizes_absolute_path_and_keeps_relative_path(self):
        host_paths = (
            "/home/reviewer/private/missing-bus",
            "/tmp/reviewer/private/missing-bus",
            "/Users/reviewer/private/missing-bus",
            r"C:\Users\reviewer\private\missing-bus",
            r"\\server\share\reviewer\missing-bus",
        )
        for missing_bus in host_paths:
            with self.subTest(missing_bus=missing_bus):
                absolute_stdout = StringIO()
                with redirect_stdout(absolute_stdout):
                    absolute_code = main(["loop", "check", missing_bus])

                absolute_output = absolute_stdout.getvalue()
                self.assertEqual(1, absolute_code)
                self.assertNotIn(missing_bus, absolute_output)
                for marker in ("/home/", "/tmp/", "/Users/", "C:\\", r"\\server"):
                    self.assertNotIn(marker, absolute_output)

        relative_stdout = StringIO()
        with redirect_stdout(relative_stdout):
            relative_code = main(["loop", "check", "fixtures/missing-bus"])

        self.assertEqual(1, relative_code)
        self.assertIn("fixtures/missing-bus", relative_stdout.getvalue())

    def test_valid_fixture_passes_from_another_cwd(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                os.chdir(tmpdir)
                report = validate_bus(BUS_ROOT)
            finally:
                os.chdir(original_cwd)

        self.assertEqual([], report.errors)

    def test_required_task_fields_are_enforced(self):
        task = deepcopy(self.task)
        del task["objective"]

        report = validate_task(task)

        self.assertIn("objective: missing required field", report.errors)

    def test_event_ordering_rejects_skipped_state(self):
        events = deepcopy(self.events)
        del events[1]

        report = validate_event_chain(self.task, events)

        self.assertTrue(
            any("invalid transition from assigned to reviewing" in e for e in report.errors)
        )

    def test_invalid_jsonl_is_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            ledger_path.write_text("{not json}\n", encoding="utf-8")

            _, report = parse_ledger(ledger_path)

        self.assertTrue(any("invalid JSON" in e for e in report.errors))

    def test_missing_required_event_fields_are_reported(self):
        events = deepcopy(self.events)
        del events[1]["event_type"]

        report = validate_event_chain(self.task, events)

        self.assertIn("ledger[1].event_type: missing required field", report.errors)

    def test_event_order_preservation_rejects_reordered_ledger(self):
        events = deepcopy(self.events)
        events[1], events[2] = events[2], events[1]

        report = validate_event_chain(self.task, events)

        self.assertTrue(any("invalid event order" in e for e in report.errors))

    def test_unknown_event_type_is_rejected(self):
        events = deepcopy(self.events)
        events[1]["event_type"] = "executor_submitted"

        report = validate_event_chain(self.task, events)

        self.assertTrue(any("event_type" in e and "allowed" in e for e in report.errors))

    def test_executor_cannot_emit_task_completed(self):
        events = deepcopy(self.events)
        events[-1]["actor"] = "executor"

        report = validate_event_chain(self.task, events)

        self.assertTrue(any("not authorized for task_completed" in e for e in report.errors))

    def test_executor_cannot_emit_retry_requested(self):
        events = _retry_events("baseline_drift", attempt=1)
        events[-1]["actor"] = "executor"

        report = validate_event_chain(self.task, events)

        self.assertTrue(any("not authorized for retry_requested" in e for e in report.errors))

    def test_executor_cannot_emit_blocked_escalate(self):
        events = _blocked_events("baseline_drift", attempt=3)
        events[-1]["actor"] = "executor"

        report = validate_event_chain(self.task, events)

        self.assertTrue(any("not authorized for blocked_escalate" in e for e in report.errors))

    def test_designer_cannot_emit_executor_done(self):
        events = deepcopy(self.events)
        events[1]["actor"] = "designer"

        report = validate_event_chain(self.task, events)

        self.assertTrue(any("not authorized for executor_done" in e for e in report.errors))

    def test_retry_attempt_must_not_exceed_max_attempts(self):
        events = deepcopy(self.events)
        events[1]["attempt"] = 4

        report = validate_event_chain(self.task, events)

        self.assertTrue(any("exceeds retry_policy.max_attempts" in e for e in report.errors))

    def test_retry_requires_new_failure_hypothesis(self):
        events = [
            _event(
                "E001",
                "task_assigned",
                "assigned",
                actor="designer",
            ),
            _event(
                "E002",
                "executor_done",
                "executor_done",
                actor="executor",
                evidence_path="evidence/T001-attempt-1.md",
            ),
            _event("E003", "designer_review", "reviewing", actor="designer"),
            _event(
                "E004",
                "retry_requested",
                "retry_requested",
                actor="designer",
                failure_class="verification_failed",
                review_path="reviews/T001-review.md",
            ),
        ]

        report = validate_event_chain(self.task, events)

        self.assertTrue(any("failure_hypothesis" in e for e in report.errors))

    def test_failure_class_must_be_allowed(self):
        events = [
            _event("E001", "task_assigned", "assigned", actor="designer"),
            _event(
                "E002",
                "executor_done",
                "executor_done",
                actor="executor",
                evidence_path="evidence/T001-attempt-1.md",
            ),
            _event("E003", "designer_review", "reviewing", actor="designer"),
            _event(
                "E004",
                "retry_requested",
                "retry_requested",
                actor="designer",
                failure_class="not_allowed",
                failure_hypothesis="Evidence did not include baseline output.",
                review_path="reviews/T001-review.md",
            ),
        ]

        report = validate_event_chain(self.task, events)

        self.assertTrue(any("failure_class" in e for e in report.errors))

    def test_baseline_drift_escalates_only_after_retry_budget(self):
        retry_events = _retry_events("baseline_drift", attempt=1)

        retry_report = validate_event_chain(self.task, retry_events)

        self.assertFalse(any("failure_class" in e for e in retry_report.errors))

        early_escalation_events = _blocked_events("baseline_drift", attempt=1)

        early_report = validate_event_chain(self.task, early_escalation_events)

        self.assertTrue(any("automatic retry class cannot escalate" in e for e in early_report.errors))

        exhausted_escalation_events = _blocked_events("baseline_drift", attempt=3)

        exhausted_report = validate_event_chain(self.task, exhausted_escalation_events)

        self.assertFalse(any("failure_class" in e for e in exhausted_report.errors))

    def test_retry_cycle_must_increment_attempt_after_retry_requested(self):
        task = deepcopy(self.task)
        task["status"] = "executor_done"
        events = _retry_events("verification_failed", attempt=1)
        events.append(
            _event(
                "E005",
                "executor_done",
                "executor_done",
                actor="executor",
                attempt=1,
                evidence_path="evidence/T001-attempt-1.md",
            )
        )

        report = validate_event_chain(task, events)

        self.assertTrue(any("must increment to 2 after retry_requested" in e for e in report.errors))

    def test_retry_count_must_not_exceed_max_attempts_with_new_hypotheses(self):
        task = deepcopy(self.task)
        task["status"] = "executor_done"
        events = _attempt_chain_through_executor_done(4)

        report = validate_event_chain(task, events)

        self.assertTrue(any("retry count exceeds retry_policy.max_attempts" in e for e in report.errors))

    def test_review_verdict_must_be_whitelisted(self):
        with tempfile.TemporaryDirectory(dir=BUS_ROOT) as tmpdir:
            review_path = Path(tmpdir) / "review.md"
            review_path.write_text(
                "---\n"
                "task_id: T001-loop-smoke\n"
                "objective_ref: T001-loop-smoke#objective\n"
                "verdict: maybe\n"
                "---\n",
                encoding="utf-8",
            )
            events = deepcopy(self.events)
            events[-1]["review_path"] = str(review_path)

            report = validate_event_chain(self.task, events, bus_root=BUS_ROOT)

        self.assertTrue(any("review verdict is not allowed" in e for e in report.errors))

    def test_evidence_task_and_objective_reference_integrity(self):
        with tempfile.TemporaryDirectory(dir=BUS_ROOT) as tmpdir:
            evidence_path = Path(tmpdir) / "evidence.md"
            evidence_path.write_text(
                "---\n"
                "task_id: T001-loop-smoke\n"
                "objective_ref: T001-loop-smoke#other\n"
                "attempt: 1\n"
                "---\n",
                encoding="utf-8",
            )
            events = deepcopy(self.events)
            events[1]["evidence_path"] = str(evidence_path)

            report = validate_event_chain(self.task, events, bus_root=BUS_ROOT)

        self.assertTrue(any("objective_ref mismatch" in e for e in report.errors))

    def test_evidence_path_rejects_absolute_path_outside_bus_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_path = Path(tmpdir) / "evidence.md"
            evidence_path.write_text(
                "---\n"
                "task_id: T001-loop-smoke\n"
                "objective_ref: T001-loop-smoke#objective\n"
                "attempt: 1\n"
                "---\n",
                encoding="utf-8",
            )
            events = deepcopy(self.events)
            events[1]["evidence_path"] = str(evidence_path)

            report = validate_event_chain(self.task, events, bus_root=BUS_ROOT)

        self.assertTrue(any("referenced path must stay within bus_root" in e for e in report.errors))

    def test_review_path_rejects_parent_traversal_outside_bus_root(self):
        events = deepcopy(self.events)
        events[-1]["review_path"] = "../agent_policy.example.yaml"

        report = validate_event_chain(self.task, events, bus_root=BUS_ROOT)

        self.assertTrue(any("referenced path must stay within bus_root" in e for e in report.errors))

    def test_tool_gate_report_path_rejects_outside_bus_root(self):
        task = load_yaml(TOOL_GATE_TASK_PATH)
        events, parse_report = parse_ledger(TOOL_GATE_LEDGER_PATH)
        self.assertEqual([], parse_report.errors)
        events[1]["tool_gate_report_path"] = "../agent_policy.example.yaml"

        report = validate_event_chain(task, events, bus_root=TOOL_GATE_BUS_ROOT)

        self.assertTrue(any("referenced path must stay within bus_root" in e for e in report.errors))

    def test_tool_gate_report_rejects_context_mismatch(self):
        replacements = [
            ("task_id: T005-tool-gate-audit\n", "task_id: other-task\n", "task_id"),
            (
                "objective_ref: T005-tool-gate-audit#objective\n",
                "objective_ref: other-task#objective\n",
                "objective_ref",
            ),
            ("attempt: 1\n", "attempt: 2\n", "attempt"),
        ]
        for old, new, field_name in replacements:
            with self.subTest(field_name=field_name):
                with tempfile.TemporaryDirectory() as tmpdir:
                    bus_root = Path(tmpdir) / "agent_bus_tool_gate"
                    shutil.copytree(TOOL_GATE_BUS_ROOT, bus_root)
                    report_path = bus_root / "tool_gates" / "T005-attempt-1.yaml"
                    content = report_path.read_text(encoding="utf-8")
                    report_path.write_text(content.replace(old, new, 1), encoding="utf-8")

                    report = validate_bus(bus_root)

                self.assertTrue(any(field_name in e and "must match ledger event" in e for e in report.errors))

    def test_validate_bus_rejects_forged_tool_gate_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_tool_gate"
            shutil.copytree(TOOL_GATE_BUS_ROOT, bus_root)
            forged_report = load_yaml(bus_root / "tool_gates" / "T005-attempt-1.yaml")
            forged_entry = next(
                entry
                for entry in forged_report["decisions"]
                if entry["request_id"] == "TR-001"
            )
            forged_entry["decision"]["audit_required"] = False
            forged_path = bus_root / "tool_gates" / "T005-forged.yaml"
            forged_path.write_text(json.dumps(forged_report), encoding="utf-8")

            ledger_path = bus_root / "ledger.jsonl"
            lines = ledger_path.read_text(encoding="utf-8").splitlines()
            event = json.loads(lines[1])
            event["tool_gate_report_path"] = "tool_gates/T005-forged.yaml"
            lines[1] = json.dumps(event, separators=(",", ":"))
            ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            report = validate_bus(bus_root)

        self.assertTrue(any("decision.audit_required" in e for e in report.errors))

    def test_tool_gate_report_path_only_allowed_on_executor_done(self):
        task = load_yaml(TOOL_GATE_TASK_PATH)
        events, parse_report = parse_ledger(TOOL_GATE_LEDGER_PATH)
        self.assertEqual([], parse_report.errors)
        events[0]["tool_gate_report_path"] = "tool_gates/T005-attempt-1.yaml"

        report = validate_event_chain(task, events, bus_root=TOOL_GATE_BUS_ROOT)

        self.assertTrue(any("only allowed for executor_done" in e for e in report.errors))

    def test_approval_record_path_rejects_outside_bus_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_approval"
            shutil.copytree(APPROVAL_BUS_ROOT, bus_root)
            _replace_ledger_event(
                bus_root,
                2,
                lambda event: event.update(
                    {"approval_record_paths": ["../agent_policy.example.yaml"]}
                ),
            )

            report = validate_bus(bus_root)

        self.assertTrue(any("referenced path must stay within bus_root" in e for e in report.errors))

    def test_approval_record_path_only_allowed_on_designer_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_approval"
            shutil.copytree(APPROVAL_BUS_ROOT, bus_root)
            _replace_ledger_event(
                bus_root,
                0,
                lambda event: event.update(
                    {"approval_record_paths": ["approvals/T006-delete-file-approval.yaml"]}
                ),
            )

            report = validate_bus(bus_root)

        self.assertTrue(any("only allowed for designer_review" in e for e in report.errors))

    def test_approval_record_requires_same_attempt_tool_gate_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_approval"
            shutil.copytree(APPROVAL_BUS_ROOT, bus_root)
            _replace_ledger_event(
                bus_root,
                1,
                lambda event: event.pop("tool_gate_report_path"),
            )

            report = validate_bus(bus_root)

        self.assertTrue(any("same-attempt executor_done tool_gate_report_path is required" in e for e in report.errors))

    def test_approval_record_rejects_different_tool_gate_report_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_approval"
            shutil.copytree(APPROVAL_BUS_ROOT, bus_root)
            approval_path = bus_root / "approvals" / "T006-delete-file-approval.yaml"
            approval = load_yaml(approval_path)
            approval["subject"]["tool_gate_report_path"] = "tool_gates/other.yaml"
            approval_path.write_text(json.dumps(approval), encoding="utf-8")

            report = validate_bus(bus_root)

        self.assertTrue(any("subject.tool_gate_report_path" in e for e in report.errors))

    def test_approval_record_rejects_duplicate_request_approval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_approval"
            shutil.copytree(APPROVAL_BUS_ROOT, bus_root)
            _replace_ledger_event(
                bus_root,
                2,
                lambda event: event.update(
                    {
                        "approval_record_paths": [
                            "approvals/T006-delete-file-approval.yaml",
                            "approvals/T006-delete-file-approval.yaml",
                        ]
                    }
                ),
            )

            report = validate_bus(bus_root)

        self.assertTrue(any("duplicate approval for request_id" in e for e in report.errors))

    def test_validate_bus_rejects_forged_approval_record_digest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_approval"
            shutil.copytree(APPROVAL_BUS_ROOT, bus_root)
            approval_path = bus_root / "approvals" / "T006-delete-file-approval.yaml"
            approval = load_yaml(approval_path)
            approval["subject"]["decision_digest"] = "sha256:0"
            approval_path.write_text(json.dumps(approval), encoding="utf-8")

            report = validate_bus(bus_root)

        self.assertTrue(any("subject.decision_digest" in e for e in report.errors))

    def test_validate_bus_rejects_forged_preflight_denied_allow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_preflight"
            shutil.copytree(PREFLIGHT_BUS_ROOT, bus_root)
            preflight_path = bus_root / "preflight" / "T007-preflight-report.yaml"
            preflight = load_yaml(preflight_path)
            forged = next(
                decision
                for decision in preflight["decisions"]
                if decision["request_id"] == "TR-deny-unknown"
            )
            forged["decision"] = "ready_without_approval"
            forged["execution_allowed"] = True
            preflight["summary"]["execution_allowed"] += 1
            preflight["summary"]["blocked"] -= 1
            preflight_path.write_text(json.dumps(preflight), encoding="utf-8")

            report = validate_bus(bus_root)

        self.assertTrue(any("TR-deny-unknown" in e for e in report.errors))

    def test_validate_bus_rejects_forged_preflight_missing_approval_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_preflight"
            shutil.copytree(PREFLIGHT_BUS_ROOT, bus_root)
            preflight_path = bus_root / "preflight" / "T007-preflight-report.yaml"
            preflight = load_yaml(preflight_path)
            forged = next(
                decision
                for decision in preflight["decisions"]
                if decision["request_id"] == "TR-missing-approval-delete"
            )
            forged["decision"] = "ready_with_approval"
            forged["execution_allowed"] = True
            preflight["summary"]["execution_allowed"] += 1
            preflight["summary"]["blocked"] -= 1
            preflight_path.write_text(json.dumps(preflight), encoding="utf-8")

            report = validate_bus(bus_root)

        self.assertTrue(any("TR-missing-approval-delete" in e for e in report.errors))

    def test_preflight_report_path_rejects_outside_bus_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_preflight"
            shutil.copytree(PREFLIGHT_BUS_ROOT, bus_root)
            _replace_ledger_event(
                bus_root,
                2,
                lambda event: event.update(
                    {"preflight_report_path": "../agent_policy.example.yaml"}
                ),
            )

            report = validate_bus(bus_root)

        self.assertTrue(any("referenced path must stay within bus_root" in e for e in report.errors))

    def test_preflight_report_path_only_allowed_on_designer_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_preflight"
            shutil.copytree(PREFLIGHT_BUS_ROOT, bus_root)
            _replace_ledger_event(
                bus_root,
                0,
                lambda event: event.update(
                    {"preflight_report_path": "preflight/T007-preflight-report.yaml"}
                ),
            )

            report = validate_bus(bus_root)

        self.assertTrue(any("only allowed for designer_review" in e for e in report.errors))

    def test_handoff_report_path_rejects_outside_bus_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_handoff"
            shutil.copytree(HANDOFF_BUS_ROOT, bus_root)
            _replace_ledger_event(
                bus_root,
                2,
                lambda event: event.update(
                    {"execution_handoff_report_path": "../agent_policy.example.yaml"}
                ),
            )

            report = validate_bus(bus_root)

        self.assertTrue(any("referenced path must stay within bus_root" in e for e in report.errors))

    def test_handoff_report_path_only_allowed_on_designer_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_handoff"
            shutil.copytree(HANDOFF_BUS_ROOT, bus_root)
            _replace_ledger_event(
                bus_root,
                0,
                lambda event: event.update(
                    {"execution_handoff_report_path": "handoffs/T008-handoff-report.yaml"}
                ),
            )

            report = validate_bus(bus_root)

        self.assertTrue(any("only allowed for designer_review" in e for e in report.errors))

    def test_handoff_adapter_spec_path_rejects_outside_bus_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_handoff"
            shutil.copytree(HANDOFF_BUS_ROOT, bus_root)
            handoff_path = bus_root / "handoffs" / "T008-handoff-report.yaml"
            handoff = load_yaml(handoff_path)
            handoff["adapter_spec_path"] = "../agent_policy.example.yaml"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

            report = validate_bus(bus_root)

        self.assertTrue(any("adapter_spec_path" in e and "bus_root" in e for e in report.errors))

    def test_validate_bus_rejects_forged_handoff_preflight_digest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_handoff"
            shutil.copytree(HANDOFF_BUS_ROOT, bus_root)
            handoff_path = bus_root / "handoffs" / "T008-handoff-report.yaml"
            handoff = load_yaml(handoff_path)
            handoff["handoffs"][0]["subject"]["preflight_digest"] = "sha256:0"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

            report = validate_bus(bus_root)

        self.assertTrue(any("preflight_digest" in e or "subject" in e for e in report.errors))

    def test_validate_bus_rejects_handoff_unsupported_marked_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_handoff"
            shutil.copytree(HANDOFF_BUS_ROOT, bus_root)
            handoff_path = bus_root / "handoffs" / "T008-handoff-report.yaml"
            handoff = load_yaml(handoff_path)
            forged = next(
                item
                for item in handoff["handoffs"]
                if item["request_id"] == "TR-read-unsupported-intent"
            )
            forged["gate"]["handoff_ready"] = True
            forged["gate"]["unsupported_reason"] = None
            handoff["summary"]["handoff_ready"] += 1
            handoff["summary"]["unsupported"] -= 1
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

            report = validate_bus(bus_root)

        self.assertTrue(any("unsupported" in e or "gate" in e for e in report.errors))

    def test_validate_bus_rejects_handoff_blocked_marked_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bus_root = Path(tmpdir) / "agent_bus_handoff"
            shutil.copytree(HANDOFF_BUS_ROOT, bus_root)
            handoff_path = bus_root / "handoffs" / "T008-handoff-report.yaml"
            handoff = load_yaml(handoff_path)
            forged = next(
                item
                for item in handoff["handoffs"]
                if item["request_id"] == "TR-deny-unknown"
            )
            forged["gate"]["handoff_ready"] = True
            forged["gate"]["blocked_reason"] = None
            handoff["summary"]["handoff_ready"] += 1
            handoff["summary"]["blocked"] -= 1
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

            report = validate_bus(bus_root)

        self.assertTrue(any("blocked_by_policy" in e or "gate" in e for e in report.errors))

    def test_objective_reference_integrity(self):
        events = deepcopy(self.events)
        events[1]["objective_ref"] = "T001-loop-smoke#changed"

        report = validate_event_chain(self.task, events)

        self.assertTrue(any("objective_ref" in e for e in report.errors))


def _event(event_id, event_type, status, actor, **extra):
    event = {
        "event_id": event_id,
        "ts": "2026-06-15T00:00:00Z",
        "task_id": "T001-loop-smoke",
        "actor": actor,
        "event_type": event_type,
        "status": status,
        "attempt": 1,
        "objective_ref": "T001-loop-smoke#objective",
        "summary": event_type,
    }
    event.update(extra)
    return event


def _retry_events(failure_class, attempt):
    return [
        _event("E001", "task_assigned", "assigned", actor="designer", attempt=attempt),
        _event(
            "E002",
            "executor_done",
            "executor_done",
            actor="executor",
            attempt=attempt,
            evidence_path="evidence/T001-attempt-1.md",
        ),
        _event("E003", "designer_review", "reviewing", actor="designer", attempt=attempt),
        _event(
            "E004",
            "retry_requested",
            "retry_requested",
            actor="designer",
            attempt=attempt,
            failure_class=failure_class,
            failure_hypothesis="Baseline failed after file-bus retry.",
            review_path="reviews/T001-review.md",
        ),
    ]


def _blocked_events(failure_class, attempt):
    events = _attempt_chain_through_review(attempt)
    events.append(
        _event(
            f"E{len(events) + 1:03}",
            "blocked_escalate",
            "blocked_escalate",
            actor="designer",
            attempt=attempt,
            failure_class=failure_class,
            summary="Escalated after retry budget.",
        )
    )
    return events


def _attempt_chain_through_executor_done(final_attempt):
    events = [
        _event("E001", "task_assigned", "assigned", actor="designer", attempt=1)
    ]
    for attempt in range(1, final_attempt + 1):
        events.append(
            _event(
                f"E{len(events) + 1:03}",
                "executor_done",
                "executor_done",
                actor="executor",
                attempt=attempt,
                evidence_path="evidence/T001-attempt-1.md",
            )
        )
        if attempt == final_attempt:
            break
        events.append(
            _event(
                f"E{len(events) + 1:03}",
                "designer_review",
                "reviewing",
                actor="designer",
                attempt=attempt,
            )
        )
        events.append(
            _event(
                f"E{len(events) + 1:03}",
                "retry_requested",
                "retry_requested",
                actor="designer",
                attempt=attempt,
                failure_class="verification_failed",
                failure_hypothesis=f"New failure hypothesis {attempt}.",
                review_path="reviews/T001-review.md",
            )
        )
    return events


def _attempt_chain_through_review(final_attempt):
    events = _attempt_chain_through_executor_done(final_attempt)
    events.append(
        _event(
            f"E{len(events) + 1:03}",
            "designer_review",
            "reviewing",
            actor="designer",
            attempt=final_attempt,
        )
    )
    return events


def _forge_tool_gate_entry_as_allow(entry):
    entry["decision"]["risk_level"] = "low"
    entry["decision"]["decision"] = "allow"
    entry["decision"]["approval_required"] = False
    entry["decision"]["policy_source"] = {
        "tool_manifest": "forged",
        "governance_category": "forged",
    }
    entry["decision"]["audit_fields"]["policy_decision"] = "allow"
    entry["decision"]["audit_fields"]["approval_required"] = False
    entry["gate"] = {
        "execution_allowed_by_policy": True,
        "requires_approval": False,
        "blocked_by_policy": False,
        "result_status": "not_executed",
    }


def _replace_ledger_event(bus_root, index, mutate):
    ledger_path = Path(bus_root) / "ledger.jsonl"
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[index])
    mutate(event)
    lines[index] = json.dumps(event, separators=(",", ":"))
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
