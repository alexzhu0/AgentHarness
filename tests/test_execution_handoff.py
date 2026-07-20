from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.approval_record import build_approval_record
from agentharness.execution_handoff import (
    build_execution_handoff,
    build_execution_handoff_report,
    preflight_decision_digest,
    validate_execution_handoff,
    validate_execution_handoff_report,
    validate_runtime_adapter_spec,
)
from agentharness.execution_preflight import (
    build_execution_preflight_decision,
    build_execution_preflight_report,
)
from agentharness.tool_gate import build_tool_gate_report
from agentharness.yamlio import load_yaml


POLICY_PATH = ROOT / "examples" / "agent_policy.example.yaml"
GOVERNANCE_PATH = ROOT / "policies" / "tool_governance.yaml"


class ExecutionHandoffTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_yaml(POLICY_PATH)
        self.governance = load_yaml(GOVERNANCE_PATH)
        self.context = {
            "task_id": "T008-execution-boundary",
            "objective_ref": "T008-execution-boundary#objective",
            "attempt": 1,
            "tool_gate_report_path": "tool_gates/T008-attempt-1.yaml",
            "preflight_report_path": "preflight/T008-preflight-report.yaml",
            "adapter_spec_path": "adapters/pi-tool-call-v0.yaml",
            "policy_path": "../../examples/agent_policy.example.yaml",
            "governance_path": "../../policies/tool_governance.yaml",
        }
        self.tool_gate_report = build_tool_gate_report(
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
        self.approval = _approval_record(
            self.context,
            self.tool_gate_report,
            "TR-approve-delete",
        )
        self.approval_paths = {
            "TR-approve-delete": "approvals/T008-delete-file-approval.yaml"
        }
        self.preflight_report = build_execution_preflight_report(
            self.tool_gate_report,
            {"TR-approve-delete": self.approval},
            tool_gate_report_path=self.context["tool_gate_report_path"],
            expected_context=self.context,
        )
        self.adapter = _adapter_spec()

    def test_valid_adapter_spec_passes(self):
        report = validate_runtime_adapter_spec(self.adapter)

        self.assertEqual([], report.errors)

    def test_adapter_spec_missing_support_list_fails(self):
        adapter = deepcopy(self.adapter)
        del adapter["supports"]["target_scopes"]

        report = validate_runtime_adapter_spec(adapter)

        self.assertTrue(any("supports.target_scopes" in e for e in report.errors))

    def test_ready_without_approval_supported_adapter_is_handoff_ready(self):
        handoff = self._handoff("TR-read")

        self.assertTrue(handoff["gate"]["handoff_ready"])
        self.assertEqual("not_executed", handoff["result_status"])

    def test_ready_with_approval_supported_adapter_is_handoff_ready(self):
        handoff = self._handoff("TR-approve-delete", self.approval)

        self.assertTrue(handoff["gate"]["handoff_ready"])
        self.assertEqual(
            "ready_with_approval",
            handoff["subject"]["expected_preflight_decision"],
        )
        self.assertIsNotNone(handoff["subject"]["approval_digest"])

    def test_blocked_by_policy_cannot_be_handoff_ready(self):
        handoff = self._handoff("TR-deny-unknown")

        self.assertFalse(handoff["gate"]["handoff_ready"])
        self.assertEqual("blocked_by_policy", handoff["gate"]["blocked_reason"])

    def test_blocked_missing_approval_cannot_be_handoff_ready(self):
        handoff = self._handoff("TR-missing-approval-delete")

        self.assertFalse(handoff["gate"]["handoff_ready"])
        self.assertEqual("blocked_missing_approval", handoff["gate"]["blocked_reason"])

    def test_blocked_rejected_approval_cannot_be_handoff_ready(self):
        rejected = _approval_record(
            self.context,
            self.tool_gate_report,
            "TR-approve-delete",
            decision="rejected",
        )
        preflight = build_execution_preflight_decision(
            _entry(self.tool_gate_report, "TR-approve-delete"),
            rejected,
            self.context,
        )

        handoff = build_execution_handoff(
            _entry(self.tool_gate_report, "TR-approve-delete"),
            preflight,
            self.adapter,
            self._context("TR-approve-delete"),
            rejected,
        )

        self.assertFalse(handoff["gate"]["handoff_ready"])
        self.assertEqual("blocked_rejected_approval", handoff["gate"]["blocked_reason"])

    def test_invalid_subject_cannot_be_handoff_ready(self):
        preflight = deepcopy(_preflight(self.preflight_report, "TR-read"))
        preflight["decision"] = "invalid_subject"
        preflight["execution_allowed"] = False

        handoff = build_execution_handoff(
            _entry(self.tool_gate_report, "TR-read"),
            preflight,
            self.adapter,
            self._context("TR-read"),
        )

        self.assertFalse(handoff["gate"]["handoff_ready"])
        self.assertEqual("invalid_subject", handoff["gate"]["blocked_reason"])

    def test_partial_adapter_support_is_unsupported(self):
        adapter = deepcopy(self.adapter)
        adapter["supports"]["target_scopes"] = ["workspace"]

        handoff = build_execution_handoff(
            _entry(self.tool_gate_report, "TR-read"),
            _preflight(self.preflight_report, "TR-read"),
            adapter,
            self._context("TR-read"),
        )

        self.assertFalse(handoff["gate"]["handoff_ready"])
        self.assertEqual("unsupported_by_adapter", handoff["gate"]["unsupported_reason"])

    def test_missing_context_cannot_be_handoff_ready(self):
        for field_name in (
            "task_id",
            "objective_ref",
            "attempt",
            "tool_gate_report_path",
            "preflight_report_path",
        ):
            with self.subTest(field_name=field_name):
                context = self._context("TR-read")
                del context[field_name]

                handoff = build_execution_handoff(
                    _entry(self.tool_gate_report, "TR-read"),
                    _preflight(self.preflight_report, "TR-read"),
                    self.adapter,
                    context,
                )

                self.assertFalse(handoff["gate"]["handoff_ready"])
                self.assertEqual("invalid_context", handoff["gate"]["blocked_reason"])

    def test_forged_tool_gate_digest_is_rejected(self):
        handoff = self._handoff("TR-read")
        handoff["subject"]["tool_gate_digest"] = "sha256:0"

        report = self._validate_handoff(handoff, "TR-read")

        self.assertTrue(any("subject" in e for e in report.errors))

    def test_forged_preflight_digest_is_rejected(self):
        handoff = self._handoff("TR-read")
        handoff["subject"]["preflight_digest"] = "sha256:0"

        report = self._validate_handoff(handoff, "TR-read")

        self.assertTrue(any("subject" in e for e in report.errors))

    def test_forged_approval_digest_is_rejected(self):
        handoff = self._handoff("TR-approve-delete", self.approval)
        handoff["subject"]["approval_digest"] = "sha256:0"

        report = self._validate_handoff(handoff, "TR-approve-delete", self.approval)

        self.assertTrue(any("subject" in e for e in report.errors))

    def test_hand_authored_ready_flag_for_blocked_request_is_rejected(self):
        handoff = self._handoff("TR-deny-unknown")
        handoff["gate"]["handoff_ready"] = True
        handoff["gate"]["blocked_reason"] = None

        report = self._validate_handoff(handoff, "TR-deny-unknown")

        self.assertTrue(any("gate" in e for e in report.errors))

    def test_result_status_executed_is_rejected(self):
        handoff = self._handoff("TR-read")
        handoff["result_status"] = "executed"

        report = self._validate_handoff(handoff, "TR-read")

        self.assertTrue(any("result_status" in e for e in report.errors))

    def test_request_scope_expansion_is_rejected(self):
        handoff = self._handoff("TR-read")
        handoff["request"]["tool_name"] = "delete_file"
        handoff["request"]["category"] = "file_delete"
        handoff["request"]["intent"] = "delete_file"
        handoff["request"]["target_scope"] = "system"

        report = self._validate_handoff(handoff, "TR-read")

        self.assertTrue(any("request" in e for e in report.errors))

    def test_preflight_request_id_mismatch_is_rejected(self):
        handoff = build_execution_handoff(
            _entry(self.tool_gate_report, "TR-read"),
            _preflight(self.preflight_report, "TR-approve-delete"),
            self.adapter,
            self._context("TR-read"),
        )

        report = validate_execution_handoff(
            handoff,
            _entry(self.tool_gate_report, "TR-read"),
            _preflight(self.preflight_report, "TR-approve-delete"),
            self.adapter,
            self._context("TR-read"),
        )

        self.assertTrue(any("request_id" in e for e in report.errors))

    def test_valid_handoff_report_passes(self):
        handoff_report = self._handoff_report()

        report = self._validate_handoff_report(handoff_report)

        self.assertEqual([], report.errors)

    def test_duplicate_request_id_in_report_is_rejected(self):
        handoff_report = self._handoff_report()
        handoff_report["handoffs"].append(deepcopy(handoff_report["handoffs"][0]))
        handoff_report["summary"]["total"] += 1

        report = self._validate_handoff_report(handoff_report)

        self.assertTrue(any("request_id" in e and "unique" in e for e in report.errors))

    def test_unknown_request_id_in_report_is_rejected(self):
        handoff_report = self._handoff_report()
        unknown = deepcopy(handoff_report["handoffs"][0])
        unknown["handoff_id"] = "HOFF-unknown"
        unknown["request_id"] = "TR-unknown"
        handoff_report["handoffs"].append(unknown)
        handoff_report["summary"]["total"] += 1

        report = self._validate_handoff_report(handoff_report)

        self.assertTrue(any("must reference tool gate report" in e for e in report.errors))

    def test_report_summary_counts_included_handoffs_only(self):
        handoff_report = self._handoff_report(request_ids=["TR-read"])

        report = self._validate_handoff_report(handoff_report)

        self.assertEqual([], report.errors)
        self.assertEqual(1, handoff_report["summary"]["total"])

    def test_preflight_digest_helper_uses_full_decision_mapping(self):
        preflight = deepcopy(_preflight(self.preflight_report, "TR-read"))
        original = preflight_decision_digest(preflight)
        preflight["reason"] = "forged reason"

        self.assertNotEqual(original, preflight_decision_digest(preflight))

    def test_execution_handoff_module_has_no_runtime_side_effect_surface(self):
        source = (ROOT / "src" / "agentharness" / "execution_handoff.py").read_text(
            encoding="utf-8"
        )
        forbidden = (
            "subprocess",
            "os.system",
            "Popen",
            "socket",
            "requests",
            "httpx",
            "urllib",
            "open(",
            "write_text",
            "write_bytes",
        )

        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def _context(self, request_id):
        context = dict(self.context)
        context["handoff_id"] = f"HOFF-{request_id}"
        if request_id == "TR-approve-delete":
            context["approval_record_path"] = self.approval_paths[request_id]
        return context

    def _handoff(self, request_id, approval=None):
        return build_execution_handoff(
            _entry(self.tool_gate_report, request_id),
            _preflight(self.preflight_report, request_id),
            self.adapter,
            self._context(request_id),
            approval,
        )

    def _handoff_report(self, request_ids=None):
        return build_execution_handoff_report(
            self.tool_gate_report,
            self.preflight_report,
            self.adapter,
            self.context,
            {"TR-approve-delete": self.approval},
            self.approval_paths,
            request_ids=request_ids,
        )

    def _validate_handoff(self, handoff, request_id, approval=None):
        return validate_execution_handoff(
            handoff,
            _entry(self.tool_gate_report, request_id),
            _preflight(self.preflight_report, request_id),
            self.adapter,
            self._context(request_id),
            approval,
        )

    def _validate_handoff_report(self, handoff_report):
        return validate_execution_handoff_report(
            handoff_report,
            self.tool_gate_report,
            self.preflight_report,
            self.adapter,
            self.policy,
            self.governance,
            {"TR-approve-delete": self.approval},
            self.approval_paths,
            self.context,
        )


def _entry(report, request_id):
    return next(entry for entry in report["decisions"] if entry["request_id"] == request_id)


def _preflight(report, request_id):
    return next(
        decision for decision in report["decisions"] if decision["request_id"] == request_id
    )


def _approval_record(context, report, request_id, decision="approved"):
    approval_context = dict(context)
    approval_context["approval_id"] = f"APR-{request_id}"
    return build_approval_record(
        approval_context,
        report,
        request_id,
        {"actor": "user", "id": "local-user", "channel": "local_cli"},
        decision=decision,
    )


def _adapter_spec():
    return {
        "version": "0.1.0",
        "kind": "runtime_adapter_spec",
        "adapter_id": "pi-tool-call-v0",
        "adapter_kind": "tool_call_hook",
        "adapter_version": "0.1.0",
        "execution_plane": "external",
        "contract": {
            "input": "execution_handoff",
            "hook": "tool_call",
            "side_effect_owner": "adapter",
            "agentharness_role": "control_plane",
            "result_contract": "future_observation_artifact",
        },
        "supports": {
            "tool_names": ["read_file", "delete_file"],
            "categories": ["file_read", "file_delete"],
            "intents": ["inspect_workspace", "delete_file"],
            "target_scopes": ["repository"],
        },
        "requirements": {
            "require_handoff_ready": True,
            "require_not_executed": True,
            "require_digest_validation": True,
            "reject_unsupported": True,
        },
    }


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
            "request_id": "TR-missing-approval-delete",
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


if __name__ == "__main__":
    unittest.main()

