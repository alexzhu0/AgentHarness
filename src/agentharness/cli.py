"""Command line interface for AgentHarness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .enterprise_audit_checklist import build_enterprise_audit_checklist
from .enterprise_audit_report import (
    build_enterprise_audit_report,
    enterprise_audit_error_payload,
    verify_enterprise_audit_report,
)
from .eval_runner import run_smoke_eval
from .handoff_exporter import build_handoff_export_package
from .handoff_manifest import (
    build_handoff_export_manifest,
    verify_handoff_export_manifest,
)
from .handoff_inspector import (
    format_handoff_inspection,
    inspect_handoff_bus,
    sanitize_handoff_inspection_messages,
)
from .loop_bus import validate_bus
from .validate import ValidationReport, validate_policy
from .yamlio import YamlLoadError, load_yaml


DEFAULT_SCHEMA = "schemas/agent_policy.schema.yaml"
DEFAULT_POLICY = "examples/agent_policy.example.yaml"
DEFAULT_SUITE = "evals/agent_safety_eval_suite.yaml"
DEFAULT_CASES = "PI-001,PD-001,SEC-001"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (YamlLoadError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentharness",
        description="Validate AgentHarness policy assets and run policy smoke evals.",
        epilog="Commands include: validate, eval, loop check, handoff inspect, handoff export, handoff manifest, handoff verify-manifest, audit checklist, audit report, audit verify-report",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate an agent policy YAML file")
    validate_parser.add_argument("policy", help="path to agent_policy YAML")
    validate_parser.add_argument(
        "--schema",
        default=DEFAULT_SCHEMA,
        help=f"path to conceptual schema YAML (default: {DEFAULT_SCHEMA})",
    )
    validate_parser.set_defaults(func=_cmd_validate)

    eval_parser = subparsers.add_parser("eval", help="run supported mock policy smoke evals")
    eval_parser.add_argument(
        "--policy",
        default=DEFAULT_POLICY,
        help=f"path to agent policy YAML (default: {DEFAULT_POLICY})",
    )
    eval_parser.add_argument(
        "--schema",
        default=DEFAULT_SCHEMA,
        help=f"path to conceptual schema YAML (default: {DEFAULT_SCHEMA})",
    )
    eval_parser.add_argument(
        "--suite",
        default=DEFAULT_SUITE,
        help=f"path to safety eval suite YAML (default: {DEFAULT_SUITE})",
    )
    eval_parser.add_argument(
        "--cases",
        default=DEFAULT_CASES,
        help=f"comma-separated case IDs (default: {DEFAULT_CASES})",
    )
    eval_parser.set_defaults(func=_cmd_eval)

    loop_parser = subparsers.add_parser("loop", help="loop check file-bus fixtures")
    loop_subparsers = loop_parser.add_subparsers(dest="loop_command", required=True)
    check_parser = loop_subparsers.add_parser(
        "check", help="validate a file-bus directory"
    )
    check_parser.add_argument("bus_root", help="path to file-bus directory")
    check_parser.set_defaults(func=_cmd_loop_check)

    handoff_parser = subparsers.add_parser(
        "handoff", help="inspect, export, manifest, or verify validated handoff reports"
    )
    handoff_subparsers = handoff_parser.add_subparsers(
        dest="handoff_command", required=True
    )
    inspect_parser = handoff_subparsers.add_parser(
        "inspect", help="inspect handoff readiness from a file-bus directory"
    )
    inspect_parser.add_argument("bus_root", help="path to file-bus directory")
    inspect_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="print a deterministic JSON inspection payload",
    )
    inspect_parser.set_defaults(func=_cmd_handoff_inspect)

    export_parser = handoff_subparsers.add_parser(
        "export", help="export registry-backed ready handoffs as deterministic JSON"
    )
    export_parser.add_argument("bus_root", help="path to file-bus directory")
    export_parser.set_defaults(func=_cmd_handoff_export)

    manifest_parser = handoff_subparsers.add_parser(
        "manifest", help="emit a digest manifest for a registry-backed handoff export"
    )
    manifest_parser.add_argument("bus_root", help="path to file-bus directory")
    manifest_parser.set_defaults(func=_cmd_handoff_manifest)

    verify_manifest_parser = handoff_subparsers.add_parser(
        "verify-manifest",
        help="verify a saved handoff manifest against the current file bus",
    )
    verify_manifest_parser.add_argument("bus_root", help="path to file-bus directory")
    verify_manifest_parser.add_argument("manifest_path", help="path to saved manifest JSON")
    verify_manifest_parser.set_defaults(func=_cmd_handoff_verify_manifest)

    audit_parser = subparsers.add_parser(
        "audit", help="build read-only enterprise audit evidence reports"
    )
    audit_subparsers = audit_parser.add_subparsers(
        dest="audit_command", required=True
    )
    report_parser = audit_subparsers.add_parser(
        "report",
        help="emit a deterministic machine-readable enterprise audit report",
    )
    report_parser.add_argument("bus_root", help="path to file-bus directory")
    report_parser.set_defaults(func=_cmd_audit_report)

    checklist_parser = audit_subparsers.add_parser(
        "checklist",
        help="emit a deterministic enterprise audit goal/check checklist",
    )
    checklist_parser.add_argument("bus_root", help="path to file-bus directory")
    checklist_parser.set_defaults(func=_cmd_audit_checklist)

    verify_report_parser = audit_subparsers.add_parser(
        "verify-report",
        help="verify a saved enterprise audit report against the current file bus",
    )
    verify_report_parser.add_argument("bus_root", help="path to file-bus directory")
    verify_report_parser.add_argument(
        "audit_report_path", help="path to saved enterprise audit report JSON"
    )
    verify_report_parser.set_defaults(func=_cmd_audit_verify_report)
    return parser


def _cmd_validate(args: argparse.Namespace) -> int:
    policy = _load_mapping(args.policy, "policy")
    schema = _load_mapping(args.schema, "schema")
    report = validate_policy(policy, schema)
    _print_report(report, Path(args.policy))
    return 0 if report.ok else 1


def _cmd_eval(args: argparse.Namespace) -> int:
    policy = _load_mapping(args.policy, "policy")
    schema = _load_mapping(args.schema, "schema")
    suite = _load_mapping(args.suite, "suite")
    report = validate_policy(policy, schema)
    if not report.ok:
        _print_report(report, Path(args.policy))
        return 1

    case_ids = [case.strip() for case in args.cases.split(",") if case.strip()]
    results = run_smoke_eval(policy, suite, case_ids)
    for result in results:
        print(f"{result.status} {result.case_id}: {result.message}")
    passed = sum(1 for result in results if result.ok)
    print(f"Summary: {passed}/{len(results)} smoke evals passed")
    return 0 if results and all(result.ok for result in results) else 1


def _cmd_loop_check(args: argparse.Namespace) -> int:
    bus_root = Path(args.bus_root)
    report = validate_bus(bus_root)
    _print_loop_report(report, bus_root)
    return 0 if report.ok else 1


def _cmd_handoff_inspect(args: argparse.Namespace) -> int:
    try:
        inspection, report = inspect_handoff_bus(args.bus_root)
    except (YamlLoadError, ValueError, OSError) as exc:
        inspection = None
        report = ValidationReport()
        report.error("handoff_inspection", str(exc))
    if not report.ok or inspection is None:
        if args.json_output:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "errors": sanitize_handoff_inspection_messages(report.errors),
                        "warnings": sanitize_handoff_inspection_messages(report.warnings),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print("FAIL handoff inspection")
            for error in sanitize_handoff_inspection_messages(report.errors):
                print(f"ERROR {error}")
            for warning in sanitize_handoff_inspection_messages(report.warnings):
                print(f"WARN {warning}")
        return 1

    if args.json_output:
        print(json.dumps(inspection, indent=2, sort_keys=True))
    else:
        print(format_handoff_inspection(inspection))
    return 0


def _cmd_handoff_export(args: argparse.Namespace) -> int:
    package, report = build_handoff_export_package(args.bus_root)
    if not report.ok or package is None:
        print(f"FAIL handoff export: {Path(args.bus_root)}")
        for error in report.errors:
            print(f"ERROR {error}")
        for warning in report.warnings:
            print(f"WARN {warning}")
        return 1

    print(json.dumps(package, indent=2, sort_keys=True))
    return 0


def _cmd_handoff_manifest(args: argparse.Namespace) -> int:
    manifest, report = build_handoff_export_manifest(args.bus_root)
    if not report.ok or manifest is None:
        print(f"FAIL handoff manifest: {Path(args.bus_root)}")
        for error in report.errors:
            print(f"ERROR {error}")
        for warning in report.warnings:
            print(f"WARN {warning}")
        return 1

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def _cmd_handoff_verify_manifest(args: argparse.Namespace) -> int:
    report = verify_handoff_export_manifest(args.bus_root, args.manifest_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") is True else 1


def _cmd_audit_report(args: argparse.Namespace) -> int:
    try:
        payload, report = build_enterprise_audit_report(args.bus_root)
        if not report.ok or payload is None:
            print(json.dumps(enterprise_audit_error_payload(report), indent=2, sort_keys=True))
            return 1

        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        try:
            report = ValidationReport()
            report.error(
                "audit_report.unexpected_error",
                f"{type(exc).__name__}: {exc}",
            )
            print(
                json.dumps(
                    enterprise_audit_error_payload(report),
                    indent=2,
                    sort_keys=True,
                )
            )
        except Exception:
            print(json.dumps(_minimal_audit_report_error_payload(), indent=2, sort_keys=True))
        return 1


def _cmd_audit_verify_report(args: argparse.Namespace) -> int:
    report = verify_enterprise_audit_report(args.bus_root, args.audit_report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") is True else 1


def _cmd_audit_checklist(args: argparse.Namespace) -> int:
    payload = build_enterprise_audit_checklist(args.bus_root)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") is True else 1


def _minimal_audit_report_error_payload() -> dict:
    return {
        "version": "0.1.0",
        "kind": "enterprise_audit_report_error",
        "source": "build_enterprise_audit_report",
        "ok": False,
        "result_status": "not_executed",
        "errors": ["audit_report.unexpected_error: could not build enterprise audit report"],
        "warnings": [],
    }


def _load_mapping(path: str, label: str) -> dict:
    value = load_yaml(path)
    if not isinstance(value, dict):
        raise YamlLoadError(f"{label} file {path} must contain a mapping")
    return value


def _print_report(report, policy_path: Path) -> None:
    if report.ok:
        print(f"PASS policy validation: {policy_path}")
    else:
        print(f"FAIL policy validation: {policy_path}")
        for error in report.errors:
            print(f"ERROR {error}")
    for warning in report.warnings:
        print(f"WARN {warning}")


def _print_loop_report(report, bus_root: Path) -> None:
    if report.ok:
        print(f"PASS loop bus validation: {bus_root}")
    else:
        print(f"FAIL loop bus validation: {bus_root}")
        for error in report.errors:
            print(f"ERROR {error}")
    for warning in report.warnings:
        print(f"WARN {warning}")
