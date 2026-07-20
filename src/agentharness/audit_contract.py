"""Shared audit-plane contract constants and sanitization helpers."""

from __future__ import annotations

import re
from typing import Any


VERSION = "0.1.0"
NOT_EXECUTED = "not_executed"
EVIDENCE_CHAIN = [
    "file_bus",
    "tool_gate",
    "approval_record",
    "preflight",
    "handoff",
    "adapter_registry",
    "export_package",
    "digest_manifest",
    "manifest_verification",
]
RUNTIME_RESULT_STATUSES = {"executed", "completed", "complete", "runtime_executed"}
SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

_URL_PATTERN = re.compile(r"https?://[^\s'\"{}()[\],]+")
_ESCAPED_UNC_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z]:)\\{4,}[^\\/\s:'\"{}()[\],]+(?:\\{2,}[^\\/\s:'\"{}()[\],]+)+"
)
_UNC_PATH_PATTERN = re.compile(
    r"\\\\[^\\/\s:'\"{}()[\],]+(?:\\[^\\/\s:'\"{}()[\],]+)+"
)
_WINDOWS_DRIVE_PATH_PATTERN = re.compile(r"\b[A-Za-z]:[\\/]+[^\s:'\"{}()[\],]*")
_POSIX_PATH_PATTERN = re.compile(r"(?<![:/])/(?:[^\s:'\"{}()[\],]+/)*[^\s:'\"{}()[\],]*")


def sanitize_audit_message(message: Any) -> str:
    """Sanitize audit error/warning text while preserving ordinary URLs."""

    text = str(message)
    protected_urls: list[str] = []

    def protect_url(match: re.Match[str]) -> str:
        protected_urls.append(match.group(0))
        return f"__AGENTHARNESS_URL_{len(protected_urls) - 1}__"

    text = _URL_PATTERN.sub(protect_url, text)
    text = _ESCAPED_UNC_PATH_PATTERN.sub("<path>", text)
    text = _UNC_PATH_PATTERN.sub("<path>", text)
    text = _WINDOWS_DRIVE_PATH_PATTERN.sub("<path>", text)
    text = _POSIX_PATH_PATTERN.sub("<path>", text)
    for index, url in enumerate(protected_urls):
        text = text.replace(f"__AGENTHARNESS_URL_{index}__", url)
    return text


def contains_raw_audit_path(message: str) -> bool:
    """Return true when sanitized audit payload text still contains a raw path."""

    text = _URL_PATTERN.sub("<url>", message)
    return any(
        pattern.search(text)
        for pattern in (
            _ESCAPED_UNC_PATH_PATTERN,
            _UNC_PATH_PATTERN,
            _WINDOWS_DRIVE_PATH_PATTERN,
            _POSIX_PATH_PATTERN,
        )
    )
