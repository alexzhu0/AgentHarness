from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.approval_record import build_approval_record
from agentharness.execution_preflight import (
    build_execution_preflight_decision,
    build_execution_preflight_report,
    validate_execution_preflight_decision,
    validate_execution_preflight_report,
)
from agentharness.tool_gate import build_tool_gate_report
from agentharness.yamlio import load_yaml


POLICY_PATH = ROOT / "examples" / "agent_policy.example.yaml"
GOVERNANCE_PATH = ROOT / "policies" / "tool_governance.yaml"


class ExecutionPreflightTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_yaml(POLICY_PATH)
        self.governance = load_yaml(GOVERNANCE_PATH)
        self.context = {
            "approval_id": "APR-T007-001",
            "task_id": "T007-execution-preflight",
            "objective_ref": "T007-execution-preflight#objective",
            "attempt": 1,
            "tool_gate_report_path": "tool_gates/T007-attempt-1.yaml",
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

    def test_allow_entry_is_ready_without_approval(self):
        decision = build_execution_preflight_decision(_entry(self.report, "TR-read"))

        self.assertEqual("ready_without_approval", decision["decision"])
        self.assertTrue(decision["execution_allowed"])
        self.assertEqual("not_executed", decision["result_status"])

    def test_approval_required_without_approval_is_blocked(self):
        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-approve-delete")
        )

        self.assertEqual("blocked_missing_approval", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_approval_required_with_approved_record_is_ready(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")

        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-approve-delete"), approval, self.context
        )

        self.assertEqual("ready_with_approval", decision["decision"])
        self.assertTrue(decision["execution_allowed"])
        self.assertEqual("approved", decision["subject"]["approval_decision"])

    def test_wrong_task_id_approval_is_invalid_subject(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")
        approval["task_id"] = "other-task"

        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-approve-delete"), approval, self.context
        )

        self.assertEqual("invalid_subject", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_wrong_objective_ref_approval_is_invalid_subject(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")
        approval["objective_ref"] = "other-task#objective"

        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-approve-delete"), approval, self.context
        )

        self.assertEqual("invalid_subject", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_wrong_attempt_approval_is_invalid_subject(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")
        approval["attempt"] = 2

        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-approve-delete"), approval, self.context
        )

        self.assertEqual("invalid_subject", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_wrong_tool_gate_report_path_approval_is_invalid_subject(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")
        approval["subject"]["tool_gate_report_path"] = "tool_gates/other.yaml"

        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-approve-delete"), approval, self.context
        )

        self.assertEqual("invalid_subject", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_approved_record_without_expected_context_is_invalid_subject(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")

        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-approve-delete"), approval
        )

        self.assertEqual("invalid_subject", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_wrong_context_approval_without_expected_context_is_invalid_subject(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")
        approval["task_id"] = "other-task"
        approval["objective_ref"] = "other-task#objective"
        approval["attempt"] = 2
        approval["subject"]["tool_gate_report_path"] = "tool_gates/other.yaml"

        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-approve-delete"), approval
        )

        self.assertEqual("invalid_subject", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_approved_record_with_incomplete_expected_context_is_invalid_subject(self):
        required_fields = (
            "task_id",
            "objective_ref",
            "attempt",
            "tool_gate_report_path",
        )
        for field_name in required_fields:
            with self.subTest(field_name=field_name):
                approval = _approval_record(self.context, self.report, "TR-approve-delete")
                incomplete_context = dict(self.context)
                del incomplete_context[field_name]

                decision = build_execution_preflight_decision(
                    _entry(self.report, "TR-approve-delete"),
                    approval,
                    incomplete_context,
                )

                self.assertEqual("invalid_subject", decision["decision"])
                self.assertFalse(decision["execution_allowed"])

    def test_approval_required_with_rejected_record_is_blocked(self):
        approval = _approval_record(
            self.context,
            self.report,
            "TR-approve-delete",
            decision="rejected",
        )

        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-approve-delete"), approval, self.context
        )

        self.assertEqual("blocked_rejected_approval", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_deny_entry_is_blocked_by_policy(self):
        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-deny-unknown")
        )

        self.assertEqual("blocked_by_policy", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_deny_plus_approval_record_still_blocks(self):
        approval = _approval_record(self.context, self.report, "TR-deny-unknown")

        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-deny-unknown"), approval
        )

        self.assertEqual("blocked_by_policy", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_approval_for_wrong_request_is_invalid_subject(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")

        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-approve-delete-missing"), approval
        )

        self.assertEqual("invalid_subject", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_approval_with_mismatched_digest_is_invalid_subject(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")
        approval["subject"]["decision_digest"] = "sha256:0"

        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-approve-delete"), approval, self.context
        )

        self.assertEqual("invalid_subject", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_allow_with_approval_record_is_invalid_subject(self):
        approval = _approval_record(self.context, self.report, "TR-read")

        decision = build_execution_preflight_decision(
            _entry(self.report, "TR-read"), approval, self.context
        )

        self.assertEqual("invalid_subject", decision["decision"])
        self.assertFalse(decision["execution_allowed"])

    def test_scope_expansion_in_preflight_decision_is_rejected(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")
        entry = _entry(self.report, "TR-approve-delete")
        decision = build_execution_preflight_decision(entry, approval, self.context)
        decision["scope"]["tool_name"] = "run_check"
        decision["scope"]["category"] = "shell"
        decision["scope"]["intent"] = "run_tests"
        decision["scope"]["target_scope"] = "system"

        report = validate_execution_preflight_decision(
            decision,
            entry,
            approval,
            self.context,
        )

        self.assertTrue(any("scope" in error for error in report.errors))

    def test_direct_validator_rejects_wrong_context_approval_ready_decision(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")
        wrong_approval = deepcopy(approval)
        wrong_approval["attempt"] = 2
        entry = _entry(self.report, "TR-approve-delete")
        ready_decision = build_execution_preflight_decision(entry, approval, self.context)

        report = validate_execution_preflight_decision(
            ready_decision,
            entry,
            wrong_approval,
            self.context,
        )

        self.assertTrue(report.errors)

    def test_direct_validator_without_expected_context_rejects_ready_with_approval(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")
        entry = _entry(self.report, "TR-approve-delete")
        ready_decision = build_execution_preflight_decision(entry, approval, self.context)

        report = validate_execution_preflight_decision(
            ready_decision,
            entry,
            approval,
        )

        self.assertTrue(report.errors)

    def test_preflight_report_remains_not_executed(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")

        report = build_execution_preflight_report(
            self.report,
            {"TR-approve-delete": approval},
            tool_gate_report_path=self.context["tool_gate_report_path"],
        )

        self.assertEqual("not_executed", report["summary"]["result_status"])
        for decision in report["decisions"]:
            self.assertEqual("not_executed", decision["result_status"])

    def test_preflight_report_validator_rejects_forged_denied_allow(self):
        report = build_execution_preflight_report(
            self.report,
            {},
            tool_gate_report_path=self.context["tool_gate_report_path"],
        )
        denied = _preflight_entry(report, "TR-deny-unknown")
        denied["decision"] = "ready_without_approval"
        denied["execution_allowed"] = True
        report["summary"]["execution_allowed"] += 1
        report["summary"]["blocked"] -= 1

        validation = validate_execution_preflight_report(
            report,
            self.report,
            {},
            self.context,
        )

        self.assertTrue(any("TR-deny-unknown" in error for error in validation.errors))

    def test_preflight_report_validator_rejects_wrong_context_approval(self):
        approval = _approval_record(self.context, self.report, "TR-approve-delete")
        preflight_report = build_execution_preflight_report(
            self.report,
            {"TR-approve-delete": approval},
            tool_gate_report_path=self.context["tool_gate_report_path"],
            expected_context=self.context,
        )
        approval["task_id"] = "other-task"

        validation = validate_execution_preflight_report(
            preflight_report,
            self.report,
            {"TR-approve-delete": approval},
            self.context,
        )

        self.assertTrue(any("approval_records.TR-approve-delete.task_id" in error for error in validation.errors))


def _approval_record(context, report, request_id, decision="approved"):
    return build_approval_record(
        context,
        report,
        request_id,
        {"actor": "user", "id": "local-user", "channel": "local_review"},
        decision=decision,
        reason="User recorded a preflight approval decision.",
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
            "request_id": "TR-approve-delete-missing",
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


def _preflight_entry(report, request_id):
    return next(
        entry for entry in report["decisions"] if entry["request_id"] == request_id
    )


if __name__ == "__main__":
    unittest.main()
