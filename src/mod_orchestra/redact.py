"""SEC-003: scrub user paths and secrets from anything that leaves the local machine's trust
boundary — events, approvals, log excerpts, agent handoff packets. The on-disk build log is
kept verbatim for the user; only shared/derived text is redacted."""
from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any
from .config import HOME, PROJECTS

_SECRET_PATTERNS = [
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)(\b(?:token|password|passwd|secret|api[_-]?key|authorization)\s*[=:]\s*)([^\s'\",;]{6,})"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def _variants(path: Path) -> list[str]:
    raw = str(path)
    out = {raw, raw.replace("\\", "/"), raw.replace("/", "\\")}
    if os.name == "nt":
        out.add(raw.replace("\\", "\\\\"))
    return sorted(out, key=len, reverse=True)


def _replacements() -> list[tuple[str, str]]:
    reps: list[tuple[str, str]] = []
    for v in _variants(PROJECTS):
        reps.append((v, "<projects>"))
    for v in _variants(HOME):
        reps.append((v, "<craftctl-home>"))
    user_home = Path.home()
    for v in _variants(user_home):
        reps.append((v, "~"))
    return reps


def redact(text: str) -> str:
    if not text:
        return text
    for needle, label in _replacements():
        if len(needle) > 3:
            text = text.replace(needle, label)
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 2:  # key=value: keep the key, hide the value
            text = pattern.sub(lambda m: m.group(1) + "[redacted]", text)
        else:
            text = pattern.sub(lambda m: m.group(0)[:4] + "…[redacted]", text)
    return text


def redact_obj(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_obj(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_obj(v) for v in value]
    return value
