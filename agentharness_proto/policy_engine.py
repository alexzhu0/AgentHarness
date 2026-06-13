"""
Simple policy engine prototype for AgentHarness.

This module loads a simplified tool governance policy from YAML and
decides whether a tool request should be allowed, require approval or
denied based on default risk levels. It is not a complete
implementation but demonstrates how runtime logic can be driven by
structured policy.
"""
from dataclasses import dataclass
from typing import Optional
import yaml


@dataclass
class ToolRequest:
    """Represents a request to use a tool.

    Attributes:
        tool_name: Name of the tool being invoked.
        intent: Optional description of what the tool is intended to do.
        category: Optional category of the tool (e.g. file_read, file_write).
    """
    tool_name: str
    intent: Optional[str] = None
    category: Optional[str] = None


@dataclass
class PolicyDecision:
    """Represents the outcome of a policy decision.

    Attributes:
        action: One of allow, allow_with_audit, require_explicit_approval, deny or deny_by_default.
        risk: Risk level determined for the tool (none, low, medium, high, critical, unknown).
        reason: Explanation of how the decision was reached.
    """
    action: str
    risk: str
    reason: str


class ToolGovernance:
    """A simplified policy engine that evaluates tool requests based on a YAML policy."""

    def __init__(self, policy_file: str) -> None:
        """Load a tool governance policy from the given YAML file."""
        with open(policy_file, "r", encoding="utf-8") as f:
            self.policy = yaml.safe_load(f)
        # Extract convenience mappings
        self.risk_levels = self.policy.get("risk_levels", {})
        self.tool_categories = self.policy.get("tool_categories", {})
        self.unknown_tool_decision = self.policy.get("unknowns", {}).get("unknown_tool", {}).get("decision", "deny")

    def _lookup_category(self, tool_name: str) -> Optional[str]:
        """Guess the tool category based on the tool name.

        This prototype uses a naive mapping: if a tool name matches a
        category key exactly, we treat it as belonging to that category.
        A full implementation would reference a manifest of known tools.
        """
        # Direct match on category name
        if tool_name in self.tool_categories:
            return tool_name
        # Attempt to match known prefixes (e.g. file_read, file_write)
        for category in self.tool_categories:
            if tool_name.startswith(category):
                return category
        return None

    def decide(self, request: ToolRequest) -> PolicyDecision:
        """Evaluate a tool request and return a PolicyDecision."""
        # Determine the category: use explicit category if provided, otherwise try to guess
        category = request.category or self._lookup_category(request.tool_name)
        if category is None:
            # Unknown tool: deny by default
            return PolicyDecision(
                action=self.unknown_tool_decision,
                risk="unknown",
                reason=f"Unknown tool '{request.tool_name}' with no discernible category"
            )

        # Fetch category-specific policy
        cat_policy = self.tool_categories.get(category, {})
        if not cat_policy:
            return PolicyDecision(
                action=self.unknown_tool_decision,
                risk="unknown",
                reason=f"Tool '{request.tool_name}' mapped to unknown category '{category}'"
            )

        # Determine default risk level
        default_risk: str = cat_policy.get("default_risk", "medium")

        # For the shell category, risk is variable; try to refine based on intent if provided
        if category == "shell":
            intent = (request.intent or "").lower().strip()
            # classify known safe intents
            safe_intents = set(cat_policy.get("allowed_auto_intents", []))
            approval_intents = set(cat_policy.get("require_approval_intents", []))
            denied_intents = set(cat_policy.get("denied_intents", []))
            if intent in safe_intents:
                risk = "low"
            elif intent in approval_intents:
                risk = "high"
            elif intent in denied_intents:
                risk = "critical"
            else:
                # unknown intents are treated as medium risk
                risk = default_risk
        else:
            risk = default_risk

        # Map risk to a decision via risk_levels table
        risk_policy = self.risk_levels.get(risk, {})
        action = risk_policy.get("decision", "deny")
        reason = (
            f"Tool '{request.tool_name}' (category '{category}') has risk level '{risk}'. "
            f"Default decision: {action}."
        )
        return PolicyDecision(action=action, risk=risk, reason=reason)


if __name__ == "__main__":
    # Demonstrate usage of the policy engine with example requests
    import pprint

    import os
    # Determine the path to the sample YAML relative to this script
    base_dir = os.path.dirname(__file__)
    sample_yaml = os.path.join(base_dir, "tool_governance_sample.yaml")
    engine = ToolGovernance(sample_yaml)
    examples = [
        ToolRequest(tool_name="search", intent="find code", category=None),
        ToolRequest(tool_name="file_read", intent="read README", category=None),
        ToolRequest(tool_name="file_write", intent="update docs", category=None),
        ToolRequest(tool_name="file_delete", intent="clean up", category=None),
        ToolRequest(tool_name="shell", intent="run_tests", category=None),
        ToolRequest(tool_name="shell", intent="rm", category=None),
        ToolRequest(tool_name="shell", intent="curl_pipe_shell", category=None),
        ToolRequest(tool_name="unknown_tool", intent="mystery", category=None),
    ]
    for req in examples:
        decision = engine.decide(req)
        print(f"Request: {req.tool_name} ({req.intent}) -> Decision: {decision.action}, Risk: {decision.risk}")
        print(f"  Reason: {decision.reason}\n")