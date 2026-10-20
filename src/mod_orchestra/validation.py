"""Input and workspace validation. Symlink traversal is denied for managed writes."""
from __future__ import annotations
import re
from pathlib import Path

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
CONTENT_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{1,49}$")
PACKAGE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")

class InputError(ValueError):
    pass

def _short(value: str, limit: int = 40) -> str:
    return value if len(value) <= limit else value[:limit] + "…"

def normalize_id(value: str, *, content: bool = False) -> str:
    name = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    limit = 50 if content else 40
    if not (CONTENT_IDENTIFIER if content else IDENTIFIER).fullmatch(name):
        raise InputError(f"Invalid identifier: {_short(value)!r} (normalized: {_short(name)!r}); "
                         f"expected 2–{limit} chars of lowercase letters/numbers/underscores, starting with a letter")
    return name

def validate_package(value: str) -> str:
    if not PACKAGE.fullmatch(value) or len(value) > 120:
        raise InputError("Java package must be a dotted lowercase identifier, e.g. com.example.crystalmod")
    return value

def project_id(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise InputError("Project ID is not a valid normalized mod ID")
    return value

def safe_inside(root: Path, relative: str | Path) -> Path:
    """Resolve paths and reject filesystem escapes including existing symlink parents."""
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        raise InputError(f"Unsafe relative path: {relative}")
    base = root.resolve(strict=True)
    candidate = (base / rel).resolve(strict=False)
    if not candidate.is_relative_to(base):
        raise InputError(f"Path escapes allowed workspace: {relative}")
    return candidate

def ensure_new_directory(root: Path) -> None:
    if root.exists():
        if root.is_symlink():
            raise InputError("Refusing to write into a symlink workspace")
        if any(root.iterdir()):
            raise InputError(f"Refusing to overwrite nonempty directory: {root}")
