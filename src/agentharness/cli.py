"""Command line interface for AgentHarness."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
import sys
from typing import Sequence

from .audit_contract import sanitize_audit_message
from .enterprise_audit_checklist import build_enterprise_audit_checklist
from .enterprise_audit_report import (
    build_enterprise_audit_report,
    enterprise_audit_error_payload,
    verify_enterprise_audit_report,
)
from .eval_contract import EvalContractError, MAX_SCALAR_LENGTH
from .eval_loader import load_eval_suite, select_eval_cases
from .eval_report import (
    format_eval_error_json,
    format_eval_error_junit,
    format_eval_json,
    format_eval_junit,
    format_eval_text,
)
from .eval_runner import preflight_eval_cases, run_eval_cases
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
from .pi_evidence_contract_v1 import (
    ContractValidationError,
    MAX_JSON_DOCUMENT_BYTES,
    evaluate_pi_evidence_request_v1,
    parse_pi_observation_batch_json_v1,
    rejected_response_v1,
)
from .pi_methodology_permit_v1 import (
    MAX_PERMIT_DOCUMENT_BYTES,
    MethodologyPermitValidationError,
    denied_methodology_permit_response_v1,
    evaluate_methodology_permit_request_v1,
    parse_methodology_permit_request_json_v1,
)
from .pi_tool_call_mapping import build_pi_tool_call_mapping_report
from .validate import ValidationReport, validate_policy
from .yamlio import YamlLoadError, load_yaml


DEFAULT_SCHEMA = "schemas/agent_policy.schema.yaml"
DEFAULT_POLICY = "examples/agent_policy.example.yaml"
DEFAULT_SUITE = "evals/agent_safety_eval_suite.yaml"
DEFAULT_CASES = "PI-001,PD-001,SEC-001"
MAX_EVAL_ARG_COUNT = 128


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    values = sys.argv[1:] if argv is None else argv
    is_eval = _is_eval_invocation(values)
    eval_format = _requested_eval_format(values) if is_eval else "text"
    if is_eval and not _eval_argv_is_bounded(values):
        return _emit_eval_error_for_format(eval_format, "argument.invalid")
    try:
        if is_eval:
            with redirect_stderr(StringIO()):
                args = parser.parse_args(argv)
        else:
            args = parser.parse_args(argv)
    except SystemExit as exc:
        if is_eval and exc.code != 0:
            return _emit_eval_error_for_format(eval_format, "argument.invalid")
        raise
    try:
        return args.func(args)
    except EvalContractError as exc:
        if args.command == "eval":
            return _emit_eval_error(args, exc.code)
        print(f"ERROR: {exc}")
        return 2
    except (YamlLoadError, ValueError) as exc:
        if args.command == "eval":
            return _emit_eval_error(args, "evaluation.input_invalid")
        print(f"ERROR: {exc}")
        return 2
    except Exception:
        if args.command == "eval":
            return _emit_eval_error(args, "evaluation.internal_error", internal=True)
        raise


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentharness",
        description="Validate AgentHarness policy assets and run policy smoke evals.",
        epilog="Commands include: validate, eval, loop check, handoff inspect, handoff export, handoff manifest, handoff verify-manifest, audit checklist, audit report, audit verify-report, pi contract-check, pi evidence-evaluate-v1, pi methodology-permit-v1",
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
    selection_group = eval_parser.add_mutually_exclusive_group()
    selection_group.add_argument(
        "--cases",
        default=None,
        help=f"comma-separated case IDs (default: {DEFAULT_CASES})",
    )
    selection_group.add_argument(
        "--all", action="store_true", dest="select_all", help="run every executable case"
    )
    selection_group.add_argument(
        "--tags", help="comma-separated case tags (OR selection)"
    )
    eval_parser.add_argument(
        "--format",
        choices=("text", "json", "junit"),
        default="text",
        help="report format (default: text)",
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

    pi_parser = subparsers.add_parser(
        "pi", help="run static Pi boundary contract checks"
    )
    pi_subparsers = pi_parser.add_subparsers(dest="pi_command", required=True)
    contract_check_parser = pi_subparsers.add_parser(
        "contract-check",
        help="validate static Pi-like tool-call observations against AgentHarness evidence",
    )
    contract_check_parser.add_argument(
        "observations_path", help="path to static Pi-like observation JSON"
    )
    contract_check_parser.add_argument(
        "expectations_path", help="path to expected mapping JSON"
    )
    contract_check_parser.add_argument(
        "bus_root", help="path to registry-backed AgentHarness file-bus directory"
    )
    contract_check_parser.set_defaults(func=_cmd_pi_contract_check)
    evidence_evaluate_parser = pi_subparsers.add_parser(
        "evidence-evaluate-v1",
        help="evaluate one versioned Pi observation batch from bounded stdin",
    )
    evidence_evaluate_parser.add_argument(
        "bus_root", help="path to registry-backed AgentHarness file-bus directory"
    )
    evidence_evaluate_parser.set_defaults(func=_cmd_pi_evidence_evaluate_v1)
    methodology_permit_parser = pi_subparsers.add_parser(
        "methodology-permit-v1",
        help=(
            "evaluate one finite methodology evidence-decision request "
            "from bounded stdin"
        ),
    )
    methodology_permit_parser.set_defaults(func=_cmd_pi_methodology_permit_v1)
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
    report = validate_policy(policy, schema)
    if not report.ok:
        return _emit_eval_error(args, "policy.invalid")

    requested = _csv_values(args.cases) if args.cases is not None else None
    tags = _csv_values(args.tags) if args.tags is not None else None
    suite = load_eval_suite(args.suite)
    fixtures = {"policy": policy}
    preflight_eval_cases(suite, fixtures)
    if args.cases is not None and not requested:
        raise EvalContractError("selection.case_not_found")
    if args.tags is not None and not tags:
        raise EvalContractError("selection.no_tag_match")
    if requested is None and tags is None and not args.select_all:
        requested = tuple(DEFAULT_CASES.split(","))
    cases = select_eval_cases(
        suite,
        case_ids=requested,
        tags=tags,
        select_all=args.select_all,
    )
    eval_report = run_eval_cases(cases, fixtures)
    formatter = {
        "text": format_eval_text,
        "json": format_eval_json,
        "junit": format_eval_junit,
    }[args.format]
    print(formatter(eval_report), end="")
    return 0 if eval_report.ok else 1


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _emit_eval_error(
    args: argparse.Namespace, code: str, *, internal: bool = False
) -> int:
    return _emit_eval_error_for_format(args.format, code, internal=internal)


def _emit_eval_error_for_format(
    output_format: str, code: str, *, internal: bool = False
) -> int:
    if output_format == "json":
        print(format_eval_error_json(code), end="")
    elif output_format == "junit":
        print(format_eval_error_junit(code, internal=internal), end="")
    else:
        print(f"ERROR: {code}", file=sys.stderr)
    return 2


def _is_eval_invocation(values: Sequence[str]) -> bool:
    try:
        return bool(values) and type(values[0]) is str and values[0] == "eval"
    except (TypeError, IndexError):
        return False


def _eval_argv_is_bounded(values: Sequence[str]) -> bool:
    try:
        if len(values) > MAX_EVAL_ARG_COUNT:
            return False
        return all(
            type(value) is str and len(value) <= MAX_SCALAR_LENGTH
            for value in values
        )
    except TypeError:
        return False


def _requested_eval_format(values: Sequence[str]) -> str:
    """Identify only a bounded, explicitly requested machine report format."""

    output_format = "text"
    try:
        scan_count = min(len(values), MAX_EVAL_ARG_COUNT)
        for index in range(scan_count):
            value = values[index]
            if value == "--format=json":
                output_format = "json"
            elif value == "--format=junit":
                output_format = "junit"
            elif value == "--format" and index + 1 < scan_count:
                candidate = values[index + 1]
                if candidate in {"json", "junit"}:
                    output_format = candidate
    except (TypeError, IndexError):
        return "text"
    return output_format


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
        print(f"FAIL handoff export: {_sanitize_failure_message(Path(args.bus_root))}")
        for error in report.errors:
            print(f"ERROR {_sanitize_failure_message(error)}")
        for warning in report.warnings:
            print(f"WARN {_sanitize_failure_message(warning)}")
        return 1

    print(json.dumps(package, indent=2, sort_keys=True))
    return 0


def _cmd_handoff_manifest(args: argparse.Namespace) -> int:
    manifest, report = build_handoff_export_manifest(args.bus_root)
    if not report.ok or manifest is None:
        print(f"FAIL handoff manifest: {_sanitize_failure_message(Path(args.bus_root))}")
        for error in report.errors:
            print(f"ERROR {_sanitize_failure_message(error)}")
        for warning in report.warnings:
            print(f"WARN {_sanitize_failure_message(warning)}")
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


def _cmd_pi_contract_check(args: argparse.Namespace) -> int:
    payload = build_pi_tool_call_mapping_report(
        args.observations_path,
        args.expectations_path,
        args.bus_root,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") is True else 1


def _cmd_pi_evidence_evaluate_v1(args: argparse.Namespace) -> int:
    stream = getattr(sys.stdin, "buffer", sys.stdin)
    try:
        raw = stream.read(MAX_JSON_DOCUMENT_BYTES + 1)
    except (OSError, ValueError):
        payload = rejected_response_v1(("request.invalid",))
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 2

    try:
        request = parse_pi_observation_batch_json_v1(raw)
    except ContractValidationError as exc:
        payload = rejected_response_v1(exc.codes)
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 2

    try:
        payload = evaluate_pi_evidence_request_v1(request, args.bus_root)
    except (RecursionError, OverflowError):
        payload = rejected_response_v1(("evaluation.depth_exceeded",))
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 1
    except Exception:
        payload = rejected_response_v1(("evaluation.internal_error",))
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 1
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0


def _cmd_pi_methodology_permit_v1(_args: argparse.Namespace) -> int:
    stream = getattr(sys.stdin, "buffer", sys.stdin)
    try:
        raw = stream.read(MAX_PERMIT_DOCUMENT_BYTES + 1)
    except (OSError, ValueError):
        payload = denied_methodology_permit_response_v1("deny.request_invalid")
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 2

    try:
        request = parse_methodology_permit_request_json_v1(raw)
    except MethodologyPermitValidationError as exc:
        payload = denied_methodology_permit_response_v1(exc.code)
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 2

    try:
        payload = evaluate_methodology_permit_request_v1(request)
    except (RecursionError, OverflowError):
        payload = denied_methodology_permit_response_v1("deny.evaluation_depth")
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 1
    except Exception:
        payload = denied_methodology_permit_response_v1("deny.evaluation_internal")
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 1
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0


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
        print(f"PASS loop bus validation: {_sanitize_failure_message(bus_root)}")
    else:
        print(f"FAIL loop bus validation: {_sanitize_failure_message(bus_root)}")
        for error in report.errors:
            print(f"ERROR {_sanitize_failure_message(error)}")
    for warning in report.warnings:
        print(f"WARN {_sanitize_failure_message(warning)}")


def _sanitize_failure_message(value: object) -> str:
    return sanitize_audit_message(value)
