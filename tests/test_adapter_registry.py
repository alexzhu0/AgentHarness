from copy import deepcopy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentharness.adapter_registry import (
    adapter_spec_digest,
    validate_adapter_registry_binding,
    validate_runtime_adapter_registry,
)
from agentharness.loop_bus import validate_bus
from agentharness.yamlio import load_yaml


REGISTRY_BUS_ROOT = ROOT / "examples" / "agent_bus_adapter_registry"
REGISTRY_PATH = REGISTRY_BUS_ROOT / "adapters" / "registry.yaml"
HANDOFF_REPORT_PATH = (
    REGISTRY_BUS_ROOT / "handoffs" / "T008-handoff-report.yaml"
)
ADAPTER_SPEC_PATH = REGISTRY_BUS_ROOT / "adapters" / "pi-tool-call-v0.yaml"
ZERO_DIGEST = "sha256:" + "0" * 64


class AdapterRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_yaml(REGISTRY_PATH)
        self.handoff_report = load_yaml(HANDOFF_REPORT_PATH)
        self.adapter_spec = load_yaml(ADAPTER_SPEC_PATH)

    def test_valid_registry_passes(self):
        report = validate_runtime_adapter_registry(self.registry, REGISTRY_BUS_ROOT)

        self.assertEqual([], report.errors)

    def test_valid_registry_binding_passes(self):
        report = validate_adapter_registry_binding(
            self.handoff_report,
            self.adapter_spec,
            REGISTRY_BUS_ROOT,
        )

        self.assertEqual([], report.errors)

    def test_valid_registry_binding_without_adapter_ref_digest_passes(self):
        handoff = deepcopy(self.handoff_report)
        del handoff["adapter_ref"]["adapter_spec_digest"]

        report = validate_adapter_registry_binding(
            handoff,
            self.adapter_spec,
            REGISTRY_BUS_ROOT,
        )

        self.assertEqual([], report.errors)

    def test_registry_backed_bus_fixture_passes(self):
        report = validate_bus(REGISTRY_BUS_ROOT)

        self.assertEqual([], report.errors)

    def test_adapter_spec_digest_is_stable_when_key_order_changes(self):
        reordered = dict(reversed(list(self.adapter_spec.items())))

        self.assertEqual(
            adapter_spec_digest(self.adapter_spec),
            adapter_spec_digest(reordered),
        )

    def test_missing_adapter_registry_path_when_adapter_ref_present_fails(self):
        handoff = deepcopy(self.handoff_report)
        del handoff["adapter_registry_path"]

        report = validate_adapter_registry_binding(
            handoff,
            self.adapter_spec,
            REGISTRY_BUS_ROOT,
        )

        self.assertIn(
            "adapter_registry_path: required when adapter_ref is present",
            report.errors,
        )

    def test_missing_adapter_ref_when_adapter_registry_path_present_fails(self):
        handoff = deepcopy(self.handoff_report)
        del handoff["adapter_ref"]

        report = validate_adapter_registry_binding(
            handoff,
            self.adapter_spec,
            REGISTRY_BUS_ROOT,
        )

        self.assertIn(
            "adapter_ref: required when adapter_registry_path is present",
            report.errors,
        )

    def test_malformed_adapter_ref_fails(self):
        handoff = deepcopy(self.handoff_report)
        handoff["adapter_ref"] = ["not", "a", "mapping"]

        report = validate_adapter_registry_binding(
            handoff,
            self.adapter_spec,
            REGISTRY_BUS_ROOT,
        )

        self.assertIn("adapter_ref.$: must be a mapping", report.errors)

    def test_missing_required_adapter_ref_fields_fail(self):
        for field_name in ("adapter_id", "adapter_version"):
            with self.subTest(field_name=field_name):
                handoff = deepcopy(self.handoff_report)
                del handoff["adapter_ref"][field_name]

                report = validate_adapter_registry_binding(
                    handoff,
                    self.adapter_spec,
                    REGISTRY_BUS_ROOT,
                )

                self.assertTrue(any(field_name in error for error in report.errors))

    def test_non_string_required_adapter_ref_fields_fail(self):
        for field_name in ("adapter_id", "adapter_version"):
            with self.subTest(field_name=field_name):
                handoff = deepcopy(self.handoff_report)
                handoff["adapter_ref"][field_name] = 123

                report = validate_adapter_registry_binding(
                    handoff,
                    self.adapter_spec,
                    REGISTRY_BUS_ROOT,
                )

                self.assertTrue(any(field_name in error for error in report.errors))

    def test_non_string_optional_adapter_ref_digest_fails_when_present(self):
        handoff = deepcopy(self.handoff_report)
        handoff["adapter_ref"]["adapter_spec_digest"] = 123

        report = validate_adapter_registry_binding(
            handoff,
            self.adapter_spec,
            REGISTRY_BUS_ROOT,
        )

        self.assertIn(
            "adapter_ref.adapter_spec_digest: must be a non-empty string",
            report.errors,
        )

    def test_malformed_optional_adapter_ref_digest_fails_when_present(self):
        handoff = deepcopy(self.handoff_report)
        handoff["adapter_ref"]["adapter_spec_digest"] = "sha256:not-a-digest"

        report = validate_adapter_registry_binding(
            handoff,
            self.adapter_spec,
            REGISTRY_BUS_ROOT,
        )

        self.assertIn(
            "adapter_ref.adapter_spec_digest: must be a sha256 digest",
            report.errors,
        )

    def test_adapter_registry_path_traversal_fails(self):
        handoff = deepcopy(self.handoff_report)
        handoff["adapter_registry_path"] = "../registry.yaml"

        report = validate_adapter_registry_binding(
            handoff,
            self.adapter_spec,
            REGISTRY_BUS_ROOT,
        )

        self.assertTrue(any("adapter_registry_path" in e and "bus_root" in e for e in report.errors))

    def test_registry_entry_adapter_spec_path_traversal_fails(self):
        registry = deepcopy(self.registry)
        registry["entries"][0]["adapter_spec_path"] = "../pi-tool-call-v0.yaml"

        report = validate_runtime_adapter_registry(registry, REGISTRY_BUS_ROOT)

        self.assertTrue(any("adapter_spec_path" in e and "bus_root" in e for e in report.errors))

    def test_top_level_registry_not_mapping_fails(self):
        report = validate_runtime_adapter_registry(["not", "a", "mapping"], REGISTRY_BUS_ROOT)

        self.assertIn("$: adapter registry must be a mapping", report.errors)

    def test_invalid_registry_kind_fails(self):
        registry = deepcopy(self.registry)
        registry["kind"] = "adapter_registry"

        report = validate_runtime_adapter_registry(registry, REGISTRY_BUS_ROOT)

        self.assertIn("kind: must be runtime_adapter_registry", report.errors)

    def test_missing_registry_entries_fails(self):
        registry = deepcopy(self.registry)
        del registry["entries"]

        report = validate_runtime_adapter_registry(registry, REGISTRY_BUS_ROOT)

        self.assertIn("entries: must be a non-empty list", report.errors)

    def test_registry_entries_not_list_fails(self):
        registry = deepcopy(self.registry)
        registry["entries"] = "not-a-list"

        report = validate_runtime_adapter_registry(registry, REGISTRY_BUS_ROOT)

        self.assertIn("entries: must be a non-empty list", report.errors)

    def test_empty_registry_entries_fails(self):
        registry = deepcopy(self.registry)
        registry["entries"] = []

        report = validate_runtime_adapter_registry(registry, REGISTRY_BUS_ROOT)

        self.assertIn("entries: must be a non-empty list", report.errors)

    def test_registry_entry_not_mapping_fails(self):
        registry = deepcopy(self.registry)
        registry["entries"][0] = "not-a-mapping"

        report = validate_runtime_adapter_registry(registry, REGISTRY_BUS_ROOT)

        self.assertIn("entries[0]: must be a mapping", report.errors)

    def test_missing_required_registry_entry_fields_fail(self):
        registry = deepcopy(self.registry)
        del registry["entries"][0]["adapter_kind"]

        report = validate_runtime_adapter_registry(registry, REGISTRY_BUS_ROOT)

        self.assertTrue(any("adapter_kind" in error for error in report.errors))

    def test_invalid_registry_entry_status_fails(self):
        registry = deepcopy(self.registry)
        registry["entries"][0]["status"] = "retired"

        report = validate_runtime_adapter_registry(registry, REGISTRY_BUS_ROOT)

        self.assertTrue(any("status" in error for error in report.errors))

    def test_duplicate_registry_entries_fail(self):
        registry = deepcopy(self.registry)
        registry["entries"].append(deepcopy(registry["entries"][0]))

        report = validate_runtime_adapter_registry(registry, REGISTRY_BUS_ROOT)

        self.assertTrue(any("duplicate adapter_id" in error for error in report.errors))

    def test_selected_adapter_not_found_fails(self):
        handoff = deepcopy(self.handoff_report)
        handoff["adapter_ref"]["adapter_version"] = "0.2.0"

        report = validate_adapter_registry_binding(
            handoff,
            self.adapter_spec,
            REGISTRY_BUS_ROOT,
        )

        self.assertIn("adapter_ref: must select a registered adapter", report.errors)

    def test_deprecated_selected_adapter_fails(self):
        report = _run_registry_binding_with_status("deprecated")

        self.assertTrue(any("selected adapter must be active" in e for e in report.errors))

    def test_disabled_selected_adapter_fails(self):
        report = _run_registry_binding_with_status("disabled")

        self.assertTrue(any("selected adapter must be active" in e for e in report.errors))

    def test_registry_spec_identity_mismatch_fails(self):
        for field_name in (
            "adapter_id",
            "adapter_version",
            "adapter_kind",
            "execution_plane",
        ):
            with self.subTest(field_name=field_name):
                registry = deepcopy(self.registry)
                registry["entries"][0][field_name] = f"other-{field_name}"

                report = validate_runtime_adapter_registry(registry, REGISTRY_BUS_ROOT)

                self.assertTrue(
                    any(field_name in error and "adapter spec" in error for error in report.errors)
                )

    def test_forged_registry_adapter_spec_digest_fails(self):
        registry = deepcopy(self.registry)
        registry["entries"][0]["adapter_spec_digest"] = ZERO_DIGEST

        report = validate_runtime_adapter_registry(registry, REGISTRY_BUS_ROOT)

        self.assertTrue(
            any("adapter_spec_digest" in error and "canonical" in error for error in report.errors)
        )

    def test_adapter_ref_digest_mismatch_fails(self):
        handoff = deepcopy(self.handoff_report)
        handoff["adapter_ref"]["adapter_spec_digest"] = ZERO_DIGEST

        report = validate_adapter_registry_binding(
            handoff,
            self.adapter_spec,
            REGISTRY_BUS_ROOT,
        )

        self.assertTrue(
            any("adapter_ref.adapter_spec_digest" in error for error in report.errors)
        )

    def test_adapter_id_wildcard_selection_fails(self):
        handoff = deepcopy(self.handoff_report)
        handoff["adapter_ref"]["adapter_id"] = "*"

        report = validate_adapter_registry_binding(
            handoff,
            self.adapter_spec,
            REGISTRY_BUS_ROOT,
        )

        self.assertTrue(any("wildcard or range" in error for error in report.errors))

    def test_adapter_ref_rejects_version_aliases_and_ranges(self):
        for value in ("0.1.x", "latest", ">=0.1.0", "^0.1.0", "~0.1.0", "*"):
            with self.subTest(value=value):
                handoff = deepcopy(self.handoff_report)
                handoff["adapter_ref"]["adapter_version"] = value

                report = validate_adapter_registry_binding(
                    handoff,
                    self.adapter_spec,
                    REGISTRY_BUS_ROOT,
                )

                self.assertTrue(
                    any("adapter_version" in error and "semver" in error for error in report.errors)
                )

    def test_registry_entry_rejects_version_aliases_and_ranges(self):
        for value in ("0.1.x", "latest", ">=0.1.0", "^0.1.0", "~0.1.0", "*"):
            with self.subTest(value=value):
                registry = deepcopy(self.registry)
                registry["entries"][0]["adapter_version"] = value

                report = validate_runtime_adapter_registry(registry, REGISTRY_BUS_ROOT)

                self.assertTrue(
                    any("adapter_version" in error and "semver" in error for error in report.errors)
                )

    def test_handoff_adapter_spec_path_mismatch_fails(self):
        handoff = deepcopy(self.handoff_report)
        handoff["adapter_spec_path"] = "adapters/other.yaml"

        report = validate_adapter_registry_binding(
            handoff,
            self.adapter_spec,
            REGISTRY_BUS_ROOT,
        )

        self.assertIn(
            "adapter_spec_path: must match selected registry entry adapter_spec_path",
            report.errors,
        )

    def test_validate_bus_rejects_partial_registry_binding(self):
        report = _run_mutated_bus(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff: handoff.pop("adapter_ref"),
            )
        )

        self.assertTrue(any("adapter_ref" in error for error in report.errors))

    def test_validate_bus_rejects_forged_registry_digest(self):
        report = _run_mutated_bus(
            lambda bus_root: _mutate_registry(
                bus_root,
                lambda registry: registry["entries"][0].__setitem__(
                    "adapter_spec_digest", ZERO_DIGEST
                ),
            )
        )

        self.assertTrue(any("adapter_spec_digest" in error for error in report.errors))

    def test_validate_bus_rejects_disabled_selected_adapter(self):
        report = _run_mutated_bus(
            lambda bus_root: _mutate_registry(
                bus_root,
                lambda registry: registry["entries"][0].__setitem__("status", "disabled"),
            )
        )

        self.assertTrue(any("selected adapter must be active" in error for error in report.errors))

    def test_validate_bus_rejects_handoff_adapter_spec_path_mismatch(self):
        report = _run_mutated_bus(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff: handoff.__setitem__("adapter_spec_path", "adapters/other.yaml"),
            )
        )

        self.assertTrue(any("adapter_spec_path" in error for error in report.errors))

    def test_validate_bus_rejects_adapter_registry_path_traversal(self):
        report = _run_mutated_bus(
            lambda bus_root: _mutate_handoff_report(
                bus_root,
                lambda handoff: handoff.__setitem__("adapter_registry_path", "../registry.yaml"),
            )
        )

        self.assertTrue(any("adapter_registry_path" in error for error in report.errors))


def _run_registry_binding_with_status(status):
    with tempfile.TemporaryDirectory() as tmpdir:
        bus_root = Path(tmpdir) / "agent_bus_adapter_registry"
        shutil.copytree(REGISTRY_BUS_ROOT, bus_root)
        _mutate_registry(
            bus_root,
            lambda registry: registry["entries"][0].__setitem__("status", status),
        )
        handoff = load_yaml(bus_root / "handoffs" / "T008-handoff-report.yaml")
        adapter_spec = load_yaml(bus_root / "adapters" / "pi-tool-call-v0.yaml")
        return validate_adapter_registry_binding(handoff, adapter_spec, bus_root)


def _run_mutated_bus(mutate):
    with tempfile.TemporaryDirectory() as tmpdir:
        bus_root = Path(tmpdir) / "agent_bus_adapter_registry"
        shutil.copytree(REGISTRY_BUS_ROOT, bus_root)
        mutate(bus_root)
        return validate_bus(bus_root)


def _mutate_registry(bus_root, mutate):
    path = bus_root / "adapters" / "registry.yaml"
    registry = load_yaml(path)
    mutate(registry)
    _write_yaml(path, registry)


def _mutate_handoff_report(bus_root, mutate):
    path = bus_root / "handoffs" / "T008-handoff-report.yaml"
    handoff = load_yaml(path)
    mutate(handoff)
    _write_yaml(path, handoff)


def _write_yaml(path, value):
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
