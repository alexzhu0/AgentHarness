"""YAML loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class YamlLoadError(RuntimeError):
    """Raised when a YAML file cannot be loaded."""


class YamlBoundedLoadError(YamlLoadError):
    """Raised with a stable reason code by strict bounded YAML loading."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def load_yaml(path: str | Path) -> Any:
    """Load a YAML file using PyYAML."""

    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise YamlLoadError(
            "PyYAML is required to read AgentHarness YAML assets. "
            "Install project dependencies before running this command."
        ) from exc

    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except OSError as exc:
        raise YamlLoadError(f"Could not read YAML file {source}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise YamlLoadError(f"Could not parse YAML file {source}: {exc}") from exc


def load_yaml_bounded_strict(path: str | Path, *, max_bytes: int) -> Any:
    """Load one UTF-8 YAML document with a byte limit and unique mapping keys."""

    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise YamlBoundedLoadError("malformed") from exc

    try:
        with Path(path).open("rb") as handle:
            source = handle.read(max_bytes + 1)
    except (OSError, TypeError, ValueError) as exc:
        raise YamlBoundedLoadError("read_failed") from exc
    if len(source) > max_bytes:
        raise YamlBoundedLoadError("too_large")
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise YamlBoundedLoadError("invalid_utf8") from exc

    class DuplicateMappingKeyError(yaml.YAMLError):
        pass

    class StrictSafeLoader(yaml.SafeLoader):
        def __init__(self, stream) -> None:
            super().__init__(stream)
            self._agentharness_depth = 0

        def compose_node(self, parent, index):
            event = self.peek_event()
            if isinstance(event, yaml.events.AliasEvent) or getattr(event, "anchor", None):
                raise yaml.YAMLError("YAML anchors and aliases are not allowed")
            self._agentharness_depth += 1
            if self._agentharness_depth > 64:
                raise yaml.YAMLError("YAML nesting too deep")
            try:
                return super().compose_node(parent, index)
            finally:
                self._agentharness_depth -= 1

    def construct_unique_mapping(loader, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as exc:
                raise yaml.YAMLError("mapping key is not scalar") from exc
            if duplicate:
                raise DuplicateMappingKeyError("duplicate mapping key")
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    StrictSafeLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_unique_mapping
    )
    try:
        return yaml.load(text, Loader=StrictSafeLoader)
    except DuplicateMappingKeyError as exc:
        raise YamlBoundedLoadError("duplicate_mapping_key") from exc
    except (yaml.YAMLError, RecursionError, TypeError, ValueError) as exc:
        raise YamlBoundedLoadError("malformed") from exc
