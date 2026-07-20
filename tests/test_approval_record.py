from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.approval_record import (
    approval_subject_digest,
    build_approval_record,
    validate_approval_record,
)
from agentharness.tool_gate import build_tool_gate_report
from agentharness.yamlio import load_yaml


POLICY_PATH = ROOT / "examples" / "agent_policy.example.yaml"
GOVERNANCE_PATH = ROOT / "policies" / "tool_governance.yaml"


class ApprovalRecordTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_yaml(POLICY_PATH)
        self.governance = load_yaml(GOVERNANCE_PATH)
        self.context = {
            "approval_id": "APR-T006-001",
            "task_id": "T006-approval-record",
            "objective_ref": "T006-approval-record#objective",
            "attempt": 1,
            "tool_gate_report_path": "tool_gates/T006-attempt-1.yaml",
        }
        self.report = build_tool_gate_report(
            self.policy,
            self.governance,
            {
                "task_id": self.context["task_id"],
                "objective_ref": self.context["objective_ref"],
                "attempt": self.context["attempt"],
                "actor": "executor",
            },
            _tool_requests(),
        )

    def test_digest_is_stable_for_equivalent_mapping_order(self):
        entry = _entry(self.report, "TR-approve-delete")
        reordered = {
            "gate": deepcopy(entry["gate"]),
            "decision": deepcopy(entry["decision"]),
            "request": deepcopy(entry["request"]),
            "request_id": entry["request_id"],
        }

        self.assertEqual(approval_subject_digest(entry), approval_subject_digest(reordered))

    def test_digest_changes_when_request_changes(self):
        entry = deepcopy(_entry(self.report, "TR-approve-delete"))
        before = approval_subject_digest(entry)
        entry["request"]["target_scope"] = "system"

        self.assertNotEqual(before, approval_subject_digest(entry))

    def test_digest_changes_when_decision_changes(self):
        entry = deepcopy(_entry(self.report, "TR-approve-delete"))
        before = approval_subject_digest(entry)
        entry["decision"]["reason"] = "changed reason"

        self.assertNotEqual(before, approval_subject_digest(entry))

    def test_valid_approval_record_for_approval_required_entry_passes(self):
        record = _approval_record(self.context, self.report, "TR-approve-delete")

        report = validate_approval_record(record, self.report, self.context)

        self.assertEqual([], report.errors)

    def test_executor_approver_is_rejected(self):
        record = _approval_record(self.context, self.report, "TR-approve-delete")
        record["approver"]["actor"] = "executor"

        report = validate_approval_record(record, self.report, self.context)

        self.assertTrue(any("approver.actor" in error for error in report.errors))

    def test_approval_for_allow_entry_is_rejected(self):
        record = _approval_record(self.context, self.report, "TR-read")

        report = validate_approval_record(record, self.report, self.context)

        self.assertTrue(any("approval_required tool gate entries" in error for error in report.errors))

    def test_approval_for_deny_entry_is_rejected(self):
        record = _approval_record(self.context, self.report, "TR-deny-unknown")

        report = validate_approval_record(record, self.report, self.context)

        self.assertTrue(any("approval_required tool gate entries" in error for error in report.errors))

    def test_digest_mismatch_is_rejected(self):
        record = _approval_record(self.context, self.report, "TR-approve-delete")
        record["subject"]["decision_digest"] = "sha256:0"

        report = validate_approval_record(record, self.report, self.context)

        self.assertTrue(any("decision_digest" in error for error in report.errors))

    def test_context_mismatch_is_rejected(self):
        replacements = {
            "task_id": "other-task",
            "objective_ref": "other-task#objective",
            "attempt": 2,
        }
        for field_name, value in replacements.items():
            with self.subTest(field_name=field_name):
                record = _approval_record(self.context, self.report, "TR-approve-delete")
                record[field_name] = value

                report = validate_approval_record(record, self.report, self.context)

                self.assertTrue(any(field_name in error for error in report.errors))

    def test_executed_result_status_is_rejected(self):
        record = _approval_record(self.context, self.report, "TR-approve-delete")
        record["result_status"] = "executed"

        report = validate_approval_record(record, self.report, self.context)

        self.assertTrue(any("result_status" in error for error in report.errors))

    def test_scope_identity_cannot_be_expanded(self):
        record = _approval_record(self.context, self.report, "TR-approve-delete")
        record["scope"]["tool_name"] = "run_check"
        record["scope"]["category"] = "shell"
        record["scope"]["intent"] = "run_tests"
        record["scope"]["target_scope"] = "system"

        report = validate_approval_record(record, self.report, self.context)

        for field_name in ("tool_name", "category", "intent", "target_scope"):
            self.assertTrue(any(f"scope.{field_name}" in error for error in report.errors))


def _approval_record(context, report, request_id):
    return build_approval_record(
        context,
        report,
        request_id,
        {"actor": "user", "id": "local-user", "channel": "local_review"},
        reason="User approved the narrowly scoped request.",
    )


def _tool_requests():
    return [
        {
            "request_id": "TR-read",
            "tool_name": "read_file",
            "intent": "inspect_workspace",
            "target_scope": "repository",
            "side_effects": [],
        },
        {
            "request_id": "TR-approve-delete",
            "tool_name": "delete_file",
            "intent": "delete_file",
            "target_scope": "repository",
            "side_effects": ["data_loss"],
        },
        {
            "request_id": "TR-deny-unknown",
            "tool_name": "mystery_shell",
            "category": "shell",
            "intent": "run_tests",
            "target_scope": "repository",
            "side_effects": ["local_process_execution"],
        },
    ]


def _entry(report, request_id):
    return next(
        entry for entry in report["decisions"] if entry["request_id"] == request_id
    )


if __name__ == "__main__":
    unittest.main()
