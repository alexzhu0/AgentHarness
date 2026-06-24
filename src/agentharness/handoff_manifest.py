"""Digest-addressed manifest for handoff export packages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .execution_handoff import execution_handoff_digest
from .handoff_exporter import build_handoff_export_package
from .validate import ValidationReport


NOT_EXECUTED = "not_executed"


def build_handoff_export_manifest(
    bus_root: str | Path,
) -> tuple[dict[str, Any] | None, ValidationReport]:
    """Build a deterministic digest manifest from the T011 export package."""

    package, report = build_handoff_export_package(bus_root)
    if not report.ok or package is None:
        return None, report

    if package.get("kind") != "handoff_export_package":
        report.error("package.kind", "must be handoff_export_package")
        return None, report

    exports = package.get("exports")
    if not isinstance(exports, list):
        report.error("package.exports", "must be a list")
        return None, report

    items: list[dict[str, Any]] = []
    for index, export_item in enumerate(exports):
        if not isinstance(export_item, Mapping):
            report.error(f"package.exports[{index}]", "must be a mapping")
            continue
        items.append(_manifest_item(export_item))

    if not report.ok:
        return None, report

    manifest = {
        "version": "0.1.0",
        "kind": "handoff_export_manifest",
        "source": "build_handoff_export_manifest",
        "result_status": NOT_EXECUTED,
        "package_kind": package["kind"],
        "package_digest": execution_handoff_digest(package),
        "summary": dict(package.get("summary", {})),
        "items": items,
    }
    return manifest, report


def _manifest_item(export_item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": "handoff_export_manifest_item",
        "result_status": NOT_EXECUTED,
        "request_id": export_item.get("request_id"),
        "handoff_id": export_item.get("handoff_id"),
        "task_id": export_item.get("task_id"),
        "objective_ref": export_item.get("objective_ref"),
        "attempt": export_item.get("attempt"),
        "handoff_digest": export_item.get("handoff_digest"),
        "export_item_digest": execution_handoff_digest(export_item),
        "adapter_ref": dict(_mapping_or_empty(export_item.get("adapter_ref"))),
    }


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def verify_handoff_export_manifest(
    bus_root: str | Path,
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Verify a saved manifest against the regenerated T012 manifest."""

    expected_manifest, expected_report = build_handoff_export_manifest(bus_root)
    manifest, load_errors = _load_manifest_json(manifest_path)
    errors = [f"expected_manifest.{error}" for error in expected_report.errors]
    errors.extend(load_errors)

    if expected_manifest is not None and manifest is not None:
        if _canonical_json(expected_manifest) != _canonical_json(manifest):
            errors.append("manifest: canonical object differs from regenerated manifest")
        errors.extend(_manifest_field_errors(expected_manifest, manifest))

    item_reports, item_summary, item_errors = _verification_items(
        expected_manifest, manifest
    )
    errors.extend(item_errors)

    report = {
        "version": "0.1.0",
        "kind": "handoff_manifest_verification_report",
        "source": "verify_handoff_export_manifest",
        "result_status": NOT_EXECUTED,
        "ok": not errors,
        "package_kind": "handoff_export_package",
        "manifest_kind": manifest.get("kind") if manifest is not None else None,
        "expected_package_digest": _mapping_get(expected_manifest, "package_digest"),
        "manifest_package_digest": _mapping_get(manifest, "package_digest"),
        "summary": item_summary,
        "items": item_reports,
        "errors": errors,
    }
    return report


def _load_manifest_json(path: str | Path) -> tuple[Mapping[str, Any] | None, list[str]]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return None, [
            f"manifest: malformed UTF-8 at byte {exc.start}: {exc.reason}"
        ]
    except OSError:
        return None, ["manifest_path: could not read manifest JSON"]
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, [
            f"manifest: malformed JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"
        ]
    if not isinstance(value, Mapping):
        return None, ["manifest: must be a JSON object"]
    return value, []


def _manifest_field_errors(
    expected: Mapping[str, Any], manifest: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    for field_name in (
        "kind",
        "source",
        "package_kind",
        "result_status",
        "package_digest",
    ):
        if manifest.get(field_name) != expected.get(field_name):
            errors.append(
                f"{field_name}: expected {_display(expected.get(field_name))}, got {_display(manifest.get(field_name))}"
            )
    expected_items = expected.get("items")
    manifest_items = manifest.get("items")
    if not isinstance(manifest_items, list):
        errors.append("items: must be a list")
    elif isinstance(expected_items, list) and len(manifest_items) != len(expected_items):
        errors.append(
            f"items: expected {len(expected_items)} item(s), got {len(manifest_items)}"
        )
    return errors


def _verification_items(
    expected_manifest: Mapping[str, Any] | None,
    manifest: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    expected_items = _item_list(expected_manifest)
    manifest_items = _item_list(manifest)
    errors: list[str] = []
    reports: list[dict[str, Any]] = []
    matched = 0
    mismatched = 0
    missing = 0
    extra = 0

    max_length = max(len(expected_items), len(manifest_items))
    for index in range(max_length):
        expected_item = expected_items[index] if index < len(expected_items) else None
        manifest_item = manifest_items[index] if index < len(manifest_items) else None

        if expected_item is None:
            extra += 1
            errors.append(
                f"items[{index}]: unexpected manifest item request_id {_display(_mapping_get(manifest_item, 'request_id'))}"
            )
            reports.append(_verification_item(expected_item, manifest_item, False))
            continue
        if manifest_item is None:
            missing += 1
            errors.append(
                f"items[{index}]: missing manifest item request_id {_display(expected_item.get('request_id'))}"
            )
            reports.append(_verification_item(expected_item, manifest_item, False))
            continue

        item_errors = _item_field_errors(index, expected_item, manifest_item)
        item_ok = not item_errors and _canonical_json(expected_item) == _canonical_json(manifest_item)
        if item_ok:
            matched += 1
        else:
            mismatched += 1
            if _canonical_json(expected_item) != _canonical_json(manifest_item):
                errors.append(
                    f"items[{index}]: canonical item differs from regenerated item"
                )
            errors.extend(item_errors)
        reports.append(_verification_item(expected_item, manifest_item, item_ok))

    summary = {
        "items": len(expected_items),
        "matched": matched,
        "mismatched": mismatched,
        "missing": missing,
        "extra": extra,
        "result_status": NOT_EXECUTED,
    }
    return reports, summary, errors


def _item_field_errors(
    index: int,
    expected: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    for field_name in (
        "kind",
        "result_status",
        "request_id",
        "handoff_digest",
        "export_item_digest",
    ):
        if manifest.get(field_name) != expected.get(field_name):
            errors.append(
                f"items[{index}].{field_name}: expected {_display(expected.get(field_name))}, got {_display(manifest.get(field_name))}"
            )
    return errors


def _verification_item(
    expected: Mapping[str, Any] | None,
    manifest: Mapping[str, Any] | None,
    ok: bool,
) -> dict[str, Any]:
    return {
        "kind": "handoff_manifest_verification_item",
        "result_status": NOT_EXECUTED,
        "request_id": _mapping_get(expected, "request_id")
        if expected is not None
        else _mapping_get(manifest, "request_id"),
        "ok": ok,
        "expected_handoff_digest": _mapping_get(expected, "handoff_digest"),
        "manifest_handoff_digest": _mapping_get(manifest, "handoff_digest"),
        "expected_export_item_digest": _mapping_get(expected, "export_item_digest"),
        "manifest_export_item_digest": _mapping_get(manifest, "export_item_digest"),
    }


def _item_list(value: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    items = value.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def _mapping_get(value: Mapping[str, Any] | None, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _display(value: Any) -> str:
    return repr(value)
