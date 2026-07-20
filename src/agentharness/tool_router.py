"""Side-effect-free tool routing decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


DECISIONS = {"allow", "approval_required", "deny"}
SECRET_DENIED_INTENTS = {
    "reveal_secret",
    "reveal_secrets",
    "print_secret",
    "log_secret",
    "commit_secret",
    "send_secret_to_third_party",
    "exfiltrate_user_data",
}
KNOWN_SIDE_EFFECTS = {
    "local_process_execution",
    "modifies_repository",
    "data_loss",
    "possible_data_mutation",
    "database_mutation",
    "remote_git_mutation",
    "deployment",
    "external_message_send",
    "payment_or_purchase",
    "account_change",
    "secret_handling",
    "memory_write",
}


@dataclass(frozen=True)
class ToolDecision:
    """Deterministic policy decision for one proposed tool request."""

    tool_name: str
    category: str
    intent: str
    target_scope: str
    risk_level: str
    decision: str
    approval_required: bool
    audit_required: bool
    reason: str
    policy_source: dict[str, str]
    audit_fields: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable decision mapping."""

        return asdict(self)


def route_tool_request(
    policy: Mapping[str, Any],
    governance: Mapping[str, Any],
    request: Mapping[str, Any],
) -> ToolDecision:
    """Route one proposed tool request without executing it."""

    tool_name = _string(request.get("tool_name"), "unknown")
    intent = _normalize(_string(request.get("intent"), "unknown"))
    target_scope = _normalize(_string(request.get("target_scope"), "unknown"))
    side_effects = _string_list(request.get("side_effects", []))

    manifests = _manifest_by_name(policy)
    manifest = manifests.get(tool_name)
    category = _infer_category(tool_name, request, manifest, governance)
    policy_source = _policy_source(tool_name, category, manifest)

    if _is_denied_secret_intent(intent):
        outcome = _outcome(
            "critical",
            "deny",
            f"secret intent {intent} is denied by policy",
            audit_required=True,
        )
    elif manifest is None:
        outcome = _unknown_tool_outcome(policy, governance, tool_name)
    else:
        outcome = _route_known_category(
            category,
            manifest,
            governance,
            intent,
            target_scope,
            side_effects,
            request,
        )

    if outcome["decision"] == "allow":
        unknown_side_effect = _first_unknown_side_effect(side_effects, policy)
        if unknown_side_effect:
            unknown_policy = governance.get("unknowns", {}).get(
                "unknown_side_effect", {}
            )
            outcome = _outcome(
                _string(unknown_policy.get("risk"), "high"),
                _map_decision(_string(unknown_policy.get("decision"), "approval_required")),
                f"unknown side effect {unknown_side_effect} requires approval",
                audit_required=True,
            )

    decision = _string(outcome["decision"], "deny")
    approval_required = decision == "approval_required"
    audit_required = bool(outcome["audit_required"]) or approval_required or decision == "deny"
    audit_fields = _audit_fields(
        governance,
        request,
        tool_name,
        category,
        intent,
        target_scope,
        _string(outcome["risk_level"], "unknown"),
        decision,
        approval_required,
    )

    return ToolDecision(
        tool_name=tool_name,
        category=category,
        intent=intent,
        target_scope=target_scope,
        risk_level=_string(outcome["risk_level"], "unknown"),
        decision=decision,
        approval_required=approval_required,
        audit_required=audit_required,
        reason=_string(outcome["reason"], "policy decision"),
        policy_source=policy_source,
        audit_fields=audit_fields,
    )


def _route_known_category(
    category: str,
    manifest: Mapping[str, Any] | None,
    governance: Mapping[str, Any],
    intent: str,
    target_scope: str,
    side_effects: list[str],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    if category == "shell":
        return _route_shell(governance, intent)
    if category == "database":
        return _route_database(governance, intent, side_effects, request)
    if category == "git":
        return _route_git(governance, intent)
    if category == "browser":
        return _route_browser(governance, intent)
    if category == "deployment":
        return _route_deployment(governance, intent, target_scope)
    if category == "secrets":
        return _route_secrets(governance, intent)
    if category == "external_communication":
        return _route_external_communication(governance, intent)

    categories = governance.get("tool_categories", {})
    rules = _mapping(categories.get(category))
    risk = _string(
        (manifest or {}).get("default_risk") or rules.get("default_risk"),
        "high",
    )

    if bool((manifest or {}).get("approval_required")) or bool(
        rules.get("require_explicit_approval")
    ):
        return _outcome(risk, "approval_required", f"{category} requires approval")
    if risk == "critical":
        return _outcome(risk, "deny", f"{category} is denied by default")
    if risk == "high":
        return _outcome(risk, "approval_required", f"{category} is high risk")
    if bool(rules.get("allowed_auto")) or bool(rules.get("allowed_with_audit")):
        return _outcome(
            risk,
            "allow",
            f"{risk}-risk {category} is allowed with audit"
            if _audit_required_for_risk(governance, risk)
            else f"{risk}-risk {category} is allowed",
            audit_required=_audit_required_for_risk(governance, risk),
        )
    if risk in {"none", "low", "medium"}:
        return _outcome(
            risk,
            "allow",
            f"{risk}-risk {category} is allowed",
            audit_required=_audit_required_for_risk(governance, risk),
        )
    return _outcome(
        "high",
        "approval_required",
        f"variable-risk {category} requires an explicit allowed intent",
    )


def _route_shell(governance: Mapping[str, Any], intent: str) -> dict[str, Any]:
    rules = _category_rules(governance, "shell")
    if intent in _normalized_set(rules.get("denied_intents", [])):
        return _outcome("critical", "deny", f"shell intent {intent} is denied")
    if intent in _normalized_set(rules.get("require_approval_intents", [])):
        return _outcome("high", "approval_required", f"shell intent {intent} requires approval")
    if intent in _normalized_set(rules.get("allowed_auto_intents", [])):
        return _outcome("low", "allow", f"shell intent {intent} is allowed with audit")
    return _outcome("high", "approval_required", f"shell intent {intent} is not auto-allowed")


def _route_database(
    governance: Mapping[str, Any],
    intent: str,
    side_effects: list[str],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    rules = _category_rules(governance, "database")
    operation = _normalize(_string(request.get("operation"), intent))
    read_ops = _normalized_set(_mapping(rules.get("read")).get("operations", []))
    write_ops = _normalized_set(_mapping(rules.get("write")).get("operations", []))
    if operation in write_ops or "possible_data_mutation" in side_effects or "database_mutation" in side_effects:
        return _outcome("high", "approval_required", f"database operation {operation} requires approval")
    if operation in read_ops or intent in {"read", "query", "show_schema", "inspect_schema"}:
        return _outcome("low", "allow", f"database operation {operation} is read-only with audit")
    return _outcome("high", "approval_required", f"database operation {operation} is not proven read-only")


def _route_git(governance: Mapping[str, Any], intent: str) -> dict[str, Any]:
    rules = _category_rules(governance, "git")
    if intent in _normalized_set(rules.get("denied", [])):
        return _outcome("critical", "deny", f"git intent {intent} is denied")
    if intent in _normalized_set(rules.get("require_approval", [])):
        return _outcome("high", "approval_required", f"git intent {intent} requires approval")
    if intent in _normalized_set(rules.get("allowed_auto", [])):
        return _outcome("low", "allow", f"git intent {intent} is allowed with audit")
    return _outcome("high", "approval_required", f"git intent {intent} is not auto-allowed")


def _route_browser(governance: Mapping[str, Any], intent: str) -> dict[str, Any]:
    rules = _category_rules(governance, "browser")
    if intent in _normalized_set(rules.get("denied", [])):
        return _outcome("critical", "deny", f"browser intent {intent} is denied")
    if intent in _normalized_set(rules.get("require_user_takeover", [])):
        return _outcome("high", "approval_required", f"browser intent {intent} requires user takeover")
    if intent in _normalized_set(rules.get("allowed_auto", [])):
        return _outcome("low", "allow", f"browser intent {intent} is allowed with audit")
    return _outcome("high", "approval_required", f"browser intent {intent} is not auto-allowed")


def _route_deployment(
    governance: Mapping[str, Any], intent: str, target_scope: str
) -> dict[str, Any]:
    rules = _category_rules(governance, "deployment")
    if target_scope == "production" or intent in {"deploy_or_publish", "production", "production_deploy"}:
        risk = _string(_mapping(rules.get("production")).get("default_risk"), "high")
        return _outcome(risk, "approval_required", "production deployment requires approval")
    preview = _mapping(rules.get("preview"))
    risk = _string(preview.get("default_risk"), "medium")
    return _outcome(risk, "allow", "preview deployment is allowed with audit")


def _route_secrets(governance: Mapping[str, Any], intent: str) -> dict[str, Any]:
    rules = _category_rules(governance, "secrets")
    if intent in _normalized_set(rules.get("denied", [])) or _is_denied_secret_intent(intent):
        return _outcome("critical", "deny", f"secret intent {intent} is denied")
    if intent in _normalized_set(rules.get("allowed", [])):
        return _outcome(
            "critical",
            "approval_required",
            f"secret intent {intent} requires explicit handling approval",
        )
    return _outcome("critical", "deny", f"secret intent {intent} is denied by default")


def _route_external_communication(
    governance: Mapping[str, Any], intent: str
) -> dict[str, Any]:
    rules = _category_rules(governance, "external_communication")
    if intent in _normalized_set(rules.get("denied", [])):
        return _outcome("critical", "deny", f"external communication intent {intent} is denied")
    if intent in _normalized_set(rules.get("require_explicit_approval", [])) or intent in {
        "send",
        "send_message",
        "external_message_send",
        "email_send",
    }:
        return _outcome("high", "approval_required", f"external communication intent {intent} requires approval")
    if intent in _normalized_set(rules.get("allowed_auto", [])):
        return _outcome("low", "allow", f"external communication intent {intent} is allowed with audit")
    return _outcome("high", "approval_required", f"external communication intent {intent} is not auto-allowed")


def _infer_category(
    tool_name: str,
    request: Mapping[str, Any],
    manifest: Mapping[str, Any] | None,
    governance: Mapping[str, Any],
) -> str:
    request_category = request.get("category")
    categories = governance.get("tool_categories", {})
    if isinstance(request_category, str) and request_category in categories:
        return request_category
    manifest_category = (manifest or {}).get("category")
    if isinstance(manifest_category, str) and manifest_category in categories:
        return manifest_category
    if tool_name in categories:
        return tool_name
    inferred = _infer_category_from_intent(_string(request.get("intent"), ""))
    if inferred in categories:
        return inferred
    return "unknown"


def _infer_category_from_intent(intent: str) -> str:
    normalized = _normalize(intent)
    if normalized in {"email_send", "issue_comment", "pr_comment", "team_message", "send_message", "external_message_send"}:
        return "external_communication"
    if normalized in {"deploy_or_publish", "production_deploy", "preview_deploy"}:
        return "deployment"
    if normalized in {"status", "diff", "log", "commit", "push", "merge", "rebase", "tag"}:
        return "git"
    if normalized in {"select", "explain", "describe", "show_schema", "insert", "update", "delete", "alter", "drop", "truncate", "migration"}:
        return "database"
    if "secret" in normalized:
        return "secrets"
    return "unknown"


def _unknown_tool_outcome(
    policy: Mapping[str, Any], governance: Mapping[str, Any], tool_name: str
) -> dict[str, Any]:
    policy_decision = (
        policy.get("tools", {})
        .get("routing", {})
        .get("unknown_tool")
        or governance.get("unknowns", {}).get("unknown_tool", {}).get("decision")
        or "deny"
    )
    decision = _map_decision(_string(policy_decision, "deny"))
    risk = "high" if decision == "approval_required" else "critical"
    return _outcome(risk, decision, f"unknown tool {tool_name} follows unknown_tool policy")


def _manifest_by_name(policy: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    manifests = policy.get("tools", {}).get("manifests", [])
    if not isinstance(manifests, list):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for manifest in manifests:
        if isinstance(manifest, Mapping) and isinstance(manifest.get("name"), str):
            result[manifest["name"]] = manifest
    return result


def _policy_source(
    tool_name: str, category: str, manifest: Mapping[str, Any] | None
) -> dict[str, str]:
    if manifest is None:
        manifest_source = "none"
        category_source = "policies/tool_governance.yaml.unknowns.unknown_tool"
    else:
        manifest_source = f"agent_policy.tools.manifests[name={tool_name}]"
        category_source = (
            f"policies/tool_governance.yaml.tool_categories.{category}"
            if category != "unknown"
            else "policies/tool_governance.yaml.unknowns.unknown_tool"
        )
    return {
        "tool_manifest": manifest_source,
        "governance_category": category_source,
    }


def _audit_fields(
    governance: Mapping[str, Any],
    request: Mapping[str, Any],
    tool_name: str,
    category: str,
    intent: str,
    target_scope: str,
    risk_level: str,
    decision: str,
    approval_required: bool,
) -> dict[str, Any]:
    values = {
        "event_id": _string(request.get("event_id"), "pending"),
        "timestamp": _string(request.get("timestamp"), "pending"),
        "actor": _string(request.get("actor"), "unknown"),
        "user_request_id": _string(request.get("user_request_id"), "unknown"),
        "tool_name": tool_name,
        "category": category,
        "intent": intent,
        "target_scope": target_scope,
        "risk_level": risk_level,
        "policy_decision": decision,
        "approval_required": approval_required,
        "result_status": "not_executed",
    }
    for field_name in governance.get("audit_schema", {}).get("required_fields", []):
        values.setdefault(field_name, "unknown")
    return values


def _first_unknown_side_effect(
    side_effects: list[str], policy: Mapping[str, Any]
) -> str | None:
    known = set(KNOWN_SIDE_EFFECTS)
    for manifest in _manifest_by_name(policy).values():
        known.update(_string_list(manifest.get("side_effects", [])))
    for side_effect in side_effects:
        if side_effect not in known:
            return side_effect
    return None


def _outcome(
    risk_level: str,
    decision: str,
    reason: str,
    audit_required: bool | None = None,
) -> dict[str, Any]:
    normalized_decision = _map_decision(decision)
    return {
        "risk_level": risk_level,
        "decision": normalized_decision,
        "reason": reason,
        "audit_required": audit_required
        if audit_required is not None
        else normalized_decision != "allow" or risk_level in {"low", "medium", "high", "critical"},
    }


def _map_decision(decision: str) -> str:
    mapping = {
        "allow": "allow",
        "allow_with_audit": "allow",
        "allowed_with_audit": "allow",
        "require_explicit_approval": "approval_required",
        "ask_for_approval": "approval_required",
        "require_user_takeover": "approval_required",
        "approval_required": "approval_required",
        "deny": "deny",
        "deny_by_default": "deny",
    }
    return mapping.get(decision, "deny")


def _audit_required_for_risk(governance: Mapping[str, Any], risk: str) -> bool:
    audit = governance.get("risk_levels", {}).get(risk, {}).get("audit")
    return audit in {"lightweight", "required"} or risk in {"low", "medium", "high", "critical"}


def _category_rules(governance: Mapping[str, Any], category: str) -> Mapping[str, Any]:
    return _mapping(governance.get("tool_categories", {}).get(category))


def _normalized_set(values: Any) -> set[str]:
    return {_normalize(value) for value in _string_list(values)}


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [_normalize(value) for value in values if isinstance(value, str)]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _normalize(value: Any) -> str:
    if not isinstance(value, str):
        return "unknown"
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _is_denied_secret_intent(intent: str) -> bool:
    return intent in SECRET_DENIED_INTENTS or intent.startswith("reveal_secret")
