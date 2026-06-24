"""Validation for the conceptual AgentHarness policy schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationReport:
    """Validation result with stable error and warning lists."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, path: str, message: str) -> None:
        self.errors.append(f"{path}: {message}")

    def warn(self, path: str, message: str) -> None:
        self.warnings.append(f"{path}: {message}")


def validate_policy(policy: dict[str, Any], schema: dict[str, Any]) -> ValidationReport:
    """Validate a policy against the repository's conceptual schema."""

    report = ValidationReport()
    if not isinstance(policy, dict):
        report.error("$", "policy must be a mapping")
        return report
    if not isinstance(schema, dict):
        report.error("schema", "schema must be a mapping")
        return report

    _validate_top_level(policy, schema, report)
    _validate_section_required_fields(policy, schema, report)
    _validate_agent_profile(policy, schema, report)
    _validate_instruction_hierarchy(policy, schema, report)
    _validate_planning(policy, schema, report)
    _validate_tools(policy, schema, report)
    _validate_safety(policy, schema, report)
    _validate_verification(policy, schema, report)
    _validate_user_interaction(policy, schema, report)
    return report


def _validate_top_level(
    policy: dict[str, Any], schema: dict[str, Any], report: ValidationReport
) -> None:
    for field_name in schema.get("required_top_level_fields", []):
        if field_name not in policy:
            report.error(field_name, "missing required top-level field")


def _validate_section_required_fields(
    policy: dict[str, Any], schema: dict[str, Any], report: ValidationReport
) -> None:
    for section_name in schema.get("required_top_level_fields", []):
        section_schema = schema.get(section_name, {})
        section = policy.get(section_name)
        if section is None:
            continue
        if not isinstance(section, dict):
            report.error(section_name, "must be a mapping")
            continue
        for field_name in section_schema.get("required", []):
            if field_name not in section:
                report.error(f"{section_name}.{field_name}", "missing required field")


def _validate_agent_profile(
    policy: dict[str, Any], schema: dict[str, Any], report: ValidationReport
) -> None:
    profile = _mapping(policy.get("agent_profile"), "agent_profile", report)
    if not profile:
        return

    if not isinstance(profile.get("domains"), list):
        report.error("agent_profile.domains", "must be a list")

    communication = profile.get("communication")
    if communication is not None:
        communication = _mapping(communication, "agent_profile.communication", report)
        if communication:
            allowed_language = _enum_values(
                schema, ["agent_profile", "fields", "communication", "fields", "language"]
            )
            _check_enum(
                communication.get("language"),
                allowed_language,
                "agent_profile.communication.language",
                report,
            )
            allowed_updates = _enum_values(
                schema,
                [
                    "agent_profile",
                    "fields",
                    "communication",
                    "fields",
                    "progress_updates",
                ],
            )
            _check_enum(
                communication.get("progress_updates"),
                allowed_updates,
                "agent_profile.communication.progress_updates",
                report,
            )


def _validate_instruction_hierarchy(
    policy: dict[str, Any], schema: dict[str, Any], report: ValidationReport
) -> None:
    hierarchy = _mapping(policy.get("instruction_hierarchy"), "instruction_hierarchy", report)
    if not hierarchy:
        return

    priority = hierarchy.get("priority")
    if not isinstance(priority, list) or not all(isinstance(item, str) for item in priority):
        report.error("instruction_hierarchy.priority", "must be a list of strings")

    trust_domains = _mapping(
        hierarchy.get("trust_domains"), "instruction_hierarchy.trust_domains", report
    )
    required_domains = schema.get("instruction_hierarchy", {}).get("fields", {}).get(
        "trust_domains", {}
    ).get("required_domains", [])
    if trust_domains:
        for domain in required_domains:
            if domain not in trust_domains:
                report.error(
                    f"instruction_hierarchy.trust_domains.{domain}",
                    "missing required trust domain",
                )
        untrusted = trust_domains.get("untrusted_content")
        if isinstance(untrusted, dict) and untrusted.get("executable_as_instruction") is not False:
            report.error(
                "instruction_hierarchy.trust_domains.untrusted_content.executable_as_instruction",
                "must be false",
            )


def _validate_planning(
    policy: dict[str, Any], schema: dict[str, Any], report: ValidationReport
) -> None:
    planning = _mapping(policy.get("planning"), "planning", report)
    if not planning:
        return

    _check_enum(
        planning.get("strategy"),
        _enum_values(schema, ["planning", "fields", "strategy"]),
        "planning.strategy",
        report,
    )
    if "require_plan_when" in planning and not isinstance(planning["require_plan_when"], list):
        report.error("planning.require_plan_when", "must be a list")
    for field_name in ("max_iterations", "max_repair_iterations"):
        if field_name in planning and not isinstance(planning[field_name], int):
            report.error(f"planning.{field_name}", "must be an integer")
    if not isinstance(planning.get("stop_conditions"), list):
        report.error("planning.stop_conditions", "must be a list")


def _validate_tools(
    policy: dict[str, Any], schema: dict[str, Any], report: ValidationReport
) -> None:
    tools = _mapping(policy.get("tools"), "tools", report)
    if not tools:
        return

    routing = _mapping(tools.get("routing"), "tools.routing", report)
    if routing:
        _check_enum(
            routing.get("unknown_tool"),
            _enum_values(schema, ["tools", "fields", "routing", "fields", "unknown_tool"]),
            "tools.routing.unknown_tool",
            report,
        )
        if not isinstance(routing.get("tool_preference_order"), list):
            report.error("tools.routing.tool_preference_order", "must be a list")

    manifests = tools.get("manifests")
    if not isinstance(manifests, list):
        report.error("tools.manifests", "must be a list")
        return

    required = schema.get("tool_manifest", {}).get("required", [])
    allowed_categories = _enum_values(schema, ["tool_manifest", "fields", "category"])
    allowed_risks = _enum_values(schema, ["tool_manifest", "fields", "default_risk"])
    for index, manifest in enumerate(manifests):
        path = f"tools.manifests[{index}]"
        if not isinstance(manifest, dict):
            report.error(path, "must be a mapping")
            continue
        for field_name in required:
            if field_name not in manifest:
                report.error(f"{path}.{field_name}", "missing required field")
        _check_enum(manifest.get("category"), allowed_categories, f"{path}.category", report)
        _check_enum(manifest.get("default_risk"), allowed_risks, f"{path}.default_risk", report)
        if "side_effects" in manifest and not isinstance(manifest["side_effects"], list):
            report.error(f"{path}.side_effects", "must be a list")
        if "approval_required" in manifest and not isinstance(
            manifest["approval_required"], bool
        ):
            report.error(f"{path}.approval_required", "must be a boolean")
        if manifest.get("default_risk") == "high" and manifest.get("approval_required") is not True:
            report.error(f"{path}.approval_required", "high-risk tools require approval")
        if manifest.get("default_risk") == "critical":
            report.warn(
                f"{path}.default_risk",
                "critical tools should be denied by runtime policy unless explicitly excepted",
            )


def _validate_safety(
    policy: dict[str, Any], schema: dict[str, Any], report: ValidationReport
) -> None:
    safety = _mapping(policy.get("safety"), "safety", report)
    if not safety:
        return

    prompt_disclosure = _mapping(
        safety.get("prompt_disclosure"), "safety.prompt_disclosure", report
    )
    if prompt_disclosure:
        _check_enum(
            prompt_disclosure.get("action"),
            _enum_values(schema, ["safety", "fields", "prompt_disclosure", "fields", "action"]),
            "safety.prompt_disclosure.action",
            report,
        )

    secrets = _mapping(safety.get("secrets"), "safety.secrets", report)
    if secrets:
        _check_enum(
            secrets.get("reveal"),
            _enum_values(schema, ["safety", "fields", "secrets", "fields", "reveal"]),
            "safety.secrets.reveal",
            report,
        )
        _check_enum(
            secrets.get("redaction"),
            _enum_values(schema, ["safety", "fields", "secrets", "fields", "redaction"]),
            "safety.secrets.redaction",
            report,
        )

    destructive_ops = _mapping(safety.get("destructive_ops"), "safety.destructive_ops", report)
    if destructive_ops:
        _check_enum(
            destructive_ops.get("default_action"),
            _enum_values(
                schema, ["safety", "fields", "destructive_ops", "fields", "default_action"]
            ),
            "safety.destructive_ops.default_action",
            report,
        )

    external = _mapping(
        safety.get("external_communication"), "safety.external_communication", report
    )
    if external:
        _check_enum(
            external.get("default_action"),
            _enum_values(
                schema,
                ["safety", "fields", "external_communication", "fields", "default_action"],
            ),
            "safety.external_communication.default_action",
            report,
        )

    untrusted = _mapping(safety.get("untrusted_content"), "safety.untrusted_content", report)
    if untrusted:
        if untrusted.get("executable_as_instruction") is not False:
            report.error("safety.untrusted_content.executable_as_instruction", "must be false")
        if not isinstance(untrusted.get("allowed_operations"), list):
            report.error("safety.untrusted_content.allowed_operations", "must be a list")


def _validate_verification(
    policy: dict[str, Any], _schema: dict[str, Any], report: ValidationReport
) -> None:
    verification = _mapping(policy.get("verification"), "verification", report)
    if not verification:
        return

    for section_name in ("coding", "research"):
        section = _mapping(
            verification.get(section_name), f"verification.{section_name}", report
        )
        if not section:
            continue
        for field_name, value in section.items():
            if not isinstance(value, bool):
                report.error(f"verification.{section_name}.{field_name}", "must be a boolean")


def _validate_user_interaction(
    policy: dict[str, Any], _schema: dict[str, Any], report: ValidationReport
) -> None:
    interaction = _mapping(policy.get("user_interaction"), "user_interaction", report)
    if not interaction:
        return

    for field_name in ("ask_user_when", "avoid_asking_when"):
        if not isinstance(interaction.get(field_name), list):
            report.error(f"user_interaction.{field_name}", "must be a list")


def _mapping(value: Any, path: str, report: ValidationReport) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        report.error(path, "must be a mapping")
        return None
    return value


def _enum_values(schema: dict[str, Any], path: list[str]) -> set[Any]:
    value: Any = schema
    for part in path:
        if not isinstance(value, dict):
            return set()
        value = value.get(part)
    if not isinstance(value, dict):
        return set()
    values = value.get("values", [])
    return set(values if isinstance(values, list) else [])


def _check_enum(
    value: Any, allowed: set[Any], path: str, report: ValidationReport
) -> None:
    if value is None:
        report.error(path, "missing enum value")
        return
    if allowed and value not in allowed:
        formatted = ", ".join(str(item) for item in sorted(allowed))
        report.error(path, f"must be one of: {formatted}")
