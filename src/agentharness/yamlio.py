"""YAML loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class YamlLoadError(RuntimeError):
    """Raised when a YAML file cannot be loaded."""


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
