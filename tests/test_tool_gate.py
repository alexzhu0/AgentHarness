from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.tool_gate import build_tool_gate_report, validate_tool_gate_report
from agentharness.yamlio import load_yaml


POLICY_PATH = ROOT / "examples" / "agent_policy.example.yaml"
GOVERNANCE_PATH = ROOT / "policies" / "tool_governance.yaml"


class ToolGateTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_yaml(POLICY_PATH)
        self.governance = load_yaml(GOVERNANCE_PATH)
        self.context = {
            "task_id": "T005-tool-gate-audit",
            "objective_ref": "T005-tool-gate-audit#objective",
            "attempt": 1,
            "actor": "executor",
        }

    def test_build_tool_gate_report_produces_one_decision_per_request(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            _tool_requests(),
        )

        self.assertEqual(len(_tool_requests()), len(report["decisions"]))

    def test_summary_counts_match_decisions(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            _tool_requests(),
        )

        self.assertEqual(
            {"total": 6, "allow": 3, "approval_required": 1, "deny": 2},
            {
                "total": report["summary"]["total"],
                "allow": report["summary"]["allow"],
                "approval_required": report["summary"]["approval_required"],
                "deny": report["summary"]["deny"],
            },
        )

    def test_approval_required_maps_to_requires_approval_gate(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            _tool_requests(),
        )
        entry = _entry(report, "TR-004")

        self.assertEqual("approval_required", entry["decision"]["decision"])
        self.assertTrue(entry["gate"]["requires_approval"])
        self.assertFalse(entry["gate"]["execution_allowed_by_policy"])

    def test_deny_maps_to_blocked_gate(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            _tool_requests(),
        )
        entry = _entry(report, "TR-005")

        self.assertEqual("deny", entry["decision"]["decision"])
        self.assertTrue(entry["gate"]["blocked_by_policy"])
        self.assertFalse(entry["gate"]["execution_allowed_by_policy"])

    def test_unknown_tool_with_known_category_is_denied(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            [_tool_requests()[4]],
        )

        self.assertEqual("deny", report["decisions"][0]["decision"]["decision"])

    def test_secret_reveal_intent_is_denied(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            [_tool_requests()[5]],
        )

        self.assertEqual("deny", report["decisions"][0]["decision"]["decision"])

    def test_report_validation_rejects_invalid_decision_vocabulary(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            _tool_requests(),
        )
        report["decisions"][0]["decision"]["decision"] = "allow_with_audit"

        validation = validate_tool_gate_report(
            report, policy=self.policy, governance=self.governance
        )

        self.assertTrue(any("decision.decision" in e for e in validation.errors))

    def test_report_validation_rejects_missing_audit_fields(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            _tool_requests(),
        )
        del report["decisions"][0]["decision"]["audit_fields"]["actor"]

        validation = validate_tool_gate_report(
            report, policy=self.policy, governance=self.governance
        )

        self.assertTrue(any("audit_fields.actor" in e for e in validation.errors))

    def test_report_validation_rejects_executed_results(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            _tool_requests(),
        )
        report["decisions"][0]["decision"]["audit_fields"]["result_status"] = "executed"

        validation = validate_tool_gate_report(
            report, policy=self.policy, governance=self.governance
        )

        self.assertTrue(any("must be not_executed" in e for e in validation.errors))

    def test_report_validation_rejects_forged_unknown_shell_allow(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            [_tool_requests()[4]],
        )
        _forge_entry_as_allow(report["decisions"][0])
        report["summary"].update({"allow": 1, "approval_required": 0, "deny": 0})

        validation = validate_tool_gate_report(
            report, policy=self.policy, governance=self.governance
        )

        self.assertTrue(any("must match recomputed route_tool_request ToolDecision" in e for e in validation.errors))

    def test_approval_required_and_deny_cannot_be_changed_to_executable_allow(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            [_tool_requests()[3], _tool_requests()[5]],
        )
        for entry in report["decisions"]:
            _forge_entry_as_allow(entry)
        report["summary"].update({"allow": 2, "approval_required": 0, "deny": 0})

        validation = validate_tool_gate_report(
            report, policy=self.policy, governance=self.governance
        )

        self.assertTrue(any("decision.decision" in e for e in validation.errors))
        self.assertTrue(any("gate.execution_allowed_by_policy" in e for e in validation.errors))

    def test_report_validation_rejects_forged_audit_required(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            [_tool_requests()[0]],
        )
        report["decisions"][0]["decision"]["audit_required"] = False

        validation = validate_tool_gate_report(
            report, policy=self.policy, governance=self.governance
        )

        self.assertTrue(any("decision.audit_required" in e for e in validation.errors))

    def test_report_validation_rejects_forged_decision_identity_fields(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            [_tool_requests()[0]],
        )
        decision = report["decisions"][0]["decision"]
        decision["tool_name"] = "other_tool"
        decision["category"] = "search"
        decision["intent"] = "other_intent"
        decision["target_scope"] = "system"

        validation = validate_tool_gate_report(
            report, policy=self.policy, governance=self.governance
        )

        for field_name in ("tool_name", "category", "intent", "target_scope"):
            self.assertTrue(any(f"decision.{field_name}" in e for e in validation.errors))

    def test_report_validation_rejects_forged_reason(self):
        report = build_tool_gate_report(
            self.policy,
            self.governance,
            self.context,
            [_tool_requests()[0]],
        )
        report["decisions"][0]["decision"]["reason"] = "forged allow rationale"

        validation = validate_tool_gate_report(
            report, policy=self.policy, governance=self.governance
        )

        self.assertTrue(any("decision.reason" in e for e in validation.errors))

    def test_build_tool_gate_report_does_not_execute_or_mutate_inputs(self):
        policy_before = deepcopy(self.policy)
        governance_before = deepcopy(self.governance)
        with tempfile.TemporaryDirectory() as tmpdir:
            sentinel = Path(tmpdir) / "should-not-exist"
            requests = [
                {
                    "request_id": "TR-noexec",
                    "tool_name": "run_check",
                    "intent": "run_tests",
                    "target_scope": "repository",
                    "side_effects": ["local_process_execution"],
                    "command": f"touch {sentinel}",
                }
            ]
            requests_before = deepcopy(requests)

            report = build_tool_gate_report(
                self.policy, self.governance, self.context, requests
            )

            self.assertEqual("allow", report["decisions"][0]["decision"]["decision"])
            self.assertFalse(sentinel.exists())
            self.assertEqual(requests_before, requests)
            self.assertEqual(policy_before, self.policy)
            self.assertEqual(governance_before, self.governance)


def _tool_requests():
    return [
        {
            "request_id": "TR-001",
            "tool_name": "read_file",
            "intent": "inspect_workspace",
            "target_scope": "repository",
            "side_effects": [],
        },
        {
            "request_id": "TR-002",
            "tool_name": "edit_file",
            "intent": "modify_repository_file",
            "target_scope": "repository",
            "side_effects": ["modifies_repository"],
        },
        {
            "request_id": "TR-003",
            "tool_name": "run_check",
            "intent": "run_tests",
            "target_scope": "repository",
            "side_effects": ["local_process_execution"],
        },
        {
            "request_id": "TR-004",
            "tool_name": "delete_file",
            "intent": "delete_file",
            "target_scope": "repository",
            "side_effects": ["data_loss"],
        },
        {
            "request_id": "TR-005",
            "tool_name": "mystery_shell",
            "category": "shell",
            "intent": "run_tests",
            "target_scope": "repository",
            "side_effects": ["local_process_execution"],
        },
        {
            "request_id": "TR-006",
            "tool_name": "read_file",
            "intent": "print_secret",
            "target_scope": "repository",
            "side_effects": [],
        },
    ]


def _entry(report, request_id):
    return next(
        entry for entry in report["decisions"] if entry["request_id"] == request_id
    )


def _forge_entry_as_allow(entry):
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


if __name__ == "__main__":
    unittest.main()
