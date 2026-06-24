from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.tool_router import DECISIONS, route_tool_request
from agentharness.yamlio import load_yaml


POLICY_PATH = ROOT / "examples" / "agent_policy.example.yaml"
GOVERNANCE_PATH = ROOT / "policies" / "tool_governance.yaml"


class ToolRouterTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_yaml(POLICY_PATH)
        self.governance = load_yaml(GOVERNANCE_PATH)

    def test_known_search_request_is_allowed(self):
        decision = route_tool_request(
            self.policy,
            self.governance,
            {
                "tool_name": "search_code",
                "intent": "inspect_workspace",
                "target_scope": "repository",
                "side_effects": [],
            },
        )

        self.assertEqual("search", decision.category)
        self.assertEqual("allow", decision.decision)
        self.assertFalse(decision.approval_required)

    def test_file_write_with_declared_side_effect_is_allowed_with_audit(self):
        decision = route_tool_request(
            self.policy,
            self.governance,
            {
                "tool_name": "edit_file",
                "intent": "modify_repository_file",
                "target_scope": "repository",
                "side_effects": ["modifies_repository"],
            },
        )

        self.assertEqual("file_write", decision.category)
        self.assertEqual("medium", decision.risk_level)
        self.assertEqual("allow", decision.decision)
        self.assertTrue(decision.audit_required)

    def test_delete_file_requires_approval(self):
        decision = route_tool_request(
            self.policy,
            self.governance,
            {
                "tool_name": "delete_file",
                "intent": "delete_file",
                "target_scope": "repository",
                "side_effects": ["data_loss"],
            },
        )

        self.assertEqual("approval_required", decision.decision)
        self.assertTrue(decision.approval_required)

    def test_unknown_tool_is_denied(self):
        decision = route_tool_request(
            self.policy,
            self.governance,
            {
                "tool_name": "mystery_tool",
                "intent": "inspect_workspace",
                "target_scope": "repository",
                "side_effects": [],
            },
        )

        self.assertEqual("unknown", decision.category)
        self.assertEqual("deny", decision.decision)

    def test_unknown_shell_tool_cannot_bypass_unknown_policy_with_category(self):
        decision = route_tool_request(
            self.policy,
            self.governance,
            {
                "tool_name": "unmanifested_shell",
                "category": "shell",
                "intent": "run_tests",
                "target_scope": "repository",
                "side_effects": ["local_process_execution"],
            },
        )

        self.assertEqual("shell", decision.category)
        self.assertEqual("deny", decision.decision)
        self.assertEqual(
            "policies/tool_governance.yaml.unknowns.unknown_tool",
            decision.policy_source["governance_category"],
        )

    def test_unknown_file_read_tool_cannot_bypass_unknown_policy_with_category(self):
        decision = route_tool_request(
            self.policy,
            self.governance,
            {
                "tool_name": "unmanifested_reader",
                "category": "file_read",
                "intent": "inspect_workspace",
                "target_scope": "repository",
                "side_effects": [],
            },
        )

        self.assertEqual("file_read", decision.category)
        self.assertEqual("deny", decision.decision)

    def test_unknown_external_tool_cannot_bypass_unknown_policy_with_inferred_intent(self):
        decision = route_tool_request(
            self.policy,
            self.governance,
            {
                "tool_name": "unmanifested_mailer",
                "intent": "email_send",
                "target_scope": "external",
                "side_effects": ["external_message_send"],
            },
        )

        self.assertEqual("external_communication", decision.category)
        self.assertEqual("deny", decision.decision)

    def test_unknown_side_effect_requires_approval(self):
        decision = route_tool_request(
            self.policy,
            self.governance,
            {
                "tool_name": "read_file",
                "intent": "inspect_workspace",
                "target_scope": "repository",
                "side_effects": ["mystery_remote_mutation"],
            },
        )

        self.assertEqual("approval_required", decision.decision)
        self.assertIn("unknown side effect", decision.reason)

    def test_shell_run_tests_is_allowed(self):
        decision = route_tool_request(
            self.policy,
            self.governance,
            {
                "tool_name": "run_check",
                "intent": "run_tests",
                "target_scope": "repository",
                "side_effects": ["local_process_execution"],
            },
        )

        self.assertEqual("shell", decision.category)
        self.assertEqual("allow", decision.decision)

    def test_shell_system_package_change_requires_approval(self):
        decision = route_tool_request(
            self.policy,
            self.governance,
            {
                "tool_name": "run_check",
                "intent": "install_or_change_system_packages",
                "target_scope": "system",
                "side_effects": ["local_process_execution"],
            },
        )

        self.assertEqual("approval_required", decision.decision)

    def test_secret_reveal_intent_is_denied(self):
        decision = route_tool_request(
            self.policy,
            self.governance,
            {
                "tool_name": "read_file",
                "intent": "print_secret",
                "target_scope": "repository",
                "side_effects": [],
            },
        )

        self.assertEqual("critical", decision.risk_level)
        self.assertEqual("deny", decision.decision)

    def test_external_communication_send_requires_approval(self):
        policy = deepcopy(self.policy)
        policy["tools"]["manifests"].append(
            {
                "name": "email_send",
                "category": "external_communication",
                "default_risk": "high",
                "side_effects": ["external_message_send"],
                "approval_required": True,
            }
        )
        decision = route_tool_request(
            policy,
            self.governance,
            {
                "tool_name": "email_send",
                "category": "external_communication",
                "intent": "email_send",
                "target_scope": "external",
                "side_effects": ["external_message_send"],
            },
        )

        self.assertEqual("external_communication", decision.category)
        self.assertEqual("approval_required", decision.decision)

    def test_decision_contains_required_audit_fields(self):
        decision = route_tool_request(
            self.policy,
            self.governance,
            {
                "event_id": "E-tool-001",
                "timestamp": "2026-06-15T00:00:00Z",
                "actor": "executor",
                "user_request_id": "U-001",
                "tool_name": "read_file",
                "intent": "inspect_workspace",
                "target_scope": "repository",
                "side_effects": [],
            },
        )

        required_fields = self.governance["audit_schema"]["required_fields"]
        self.assertTrue(set(required_fields).issubset(decision.audit_fields))
        self.assertEqual("read_file", decision.audit_fields["tool_name"])
        self.assertEqual(decision.decision, decision.audit_fields["policy_decision"])
        self.assertIn(decision.decision, DECISIONS)

    def test_router_does_not_execute_or_mutate_inputs(self):
        policy_before = deepcopy(self.policy)
        governance_before = deepcopy(self.governance)
        with tempfile.TemporaryDirectory() as tmpdir:
            sentinel = Path(tmpdir) / "router-should-not-run"
            request = {
                "tool_name": "run_check",
                "intent": "run_tests",
                "target_scope": "repository",
                "side_effects": ["local_process_execution"],
                "command": f"touch {sentinel}",
            }
            request_before = deepcopy(request)

            decision = route_tool_request(self.policy, self.governance, request)

            self.assertEqual("allow", decision.decision)
            self.assertFalse(sentinel.exists())
            self.assertEqual(request_before, request)
            self.assertEqual(policy_before, self.policy)
            self.assertEqual(governance_before, self.governance)


if __name__ == "__main__":
    unittest.main()
