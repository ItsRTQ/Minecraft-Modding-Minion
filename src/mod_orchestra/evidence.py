"""Verification evidence levels (DEVELOPMENT_PATH R1).

Static validation says the generated files are intact. Evidence says what was actually
*observed*: a JAR produced, a client that loaded the mod, a dedicated server that booted,
content that behaved in-game. BUILD_PASS is recorded by the controller from an approved
build; the game levels can only be recorded by the user, because the controller never runs
Minecraft. Every record carries the workspace manifest hash so evidence is tied to the
exact source it was observed on.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .state import Store, StateError
from .fabric import validate_generated

LEVELS = ("BUILD_PASS", "CLIENT_BOOT_PASS", "SERVER_BOOT_PASS", "CONTENT_VERIFIED")
USER_ONLY_LEVELS = ("CLIENT_BOOT_PASS", "SERVER_BOOT_PASS", "CONTENT_VERIFIED")
GAME_LEVELS = frozenset(USER_ONLY_LEVELS)
# Project statuses in which evidence may be attached (source must exist and be unchanged).
EVIDENCE_STATUSES = ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_digest(root: Path) -> str:
    manifest = root / ".mod-orchestra" / "generation-manifest.json"
    if not manifest.is_file():
        raise StateError("No generated source; evidence needs a generated workspace")
    return sha256_file(manifest)


def find_built_jar(root: Path, mod_id: str) -> Path | None:
    libs = root / "build" / "libs"
    if not libs.is_dir():
        return None
    jars = sorted(j for j in libs.glob(f"{mod_id}-*.jar") if not j.name.endswith(("-sources.jar", "-dev.jar")))
    return jars[-1] if jars else None


def derive_status(current: str, levels: set[str]) -> str:
    if GAME_LEVELS <= levels and "BUILD_PASS" in levels:
        return "GAME_VERIFIED"
    if "BUILD_PASS" in levels and current in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED"):
        return "BUILD_PASSED_GAME_UNTESTED"
    return current


def record_evidence(store: Store, pid: str, level: str, *, actor: str, note: str = "",
                    jar: Path | None = None, payload: dict | None = None) -> dict:
    if level not in LEVELS:
        raise StateError(f"Unknown evidence level {level!r}; expected one of {', '.join(LEVELS)}")
    if actor != "user" and level in USER_ONLY_LEVELS:
        raise StateError(f"{level} can only be recorded by the user; the controller never observes the game")
    proj = store.project(pid)
    if proj["status"] not in EVIDENCE_STATUSES:
        raise StateError(f"Evidence cannot be attached in status {proj['status']}")
    root = Path(proj["root"])
    checked = validate_generated(root)
    if checked["status"] != "PASS":
        raise StateError("Generated files changed since generation; evidence must describe unmodified source: "
                         + "; ".join(checked["problems"][:5]))
    manifest_hash = manifest_digest(root)
    if level in GAME_LEVELS:
        builds = [e for e in store.evidence(pid) if e["level"] == "BUILD_PASS" and e["manifest_sha256"] == manifest_hash]
        if not builds:
            raise StateError(f"{level} needs a prior BUILD_PASS on this exact source. If you built by hand, record it first: "
                             f"craftctl evidence {pid} BUILD_PASS --jar <path-to-jar>")
    artifact = None
    if jar is None and level == "BUILD_PASS":
        jar = find_built_jar(root, pid)
    if jar is not None:
        jar = Path(jar)
        if not jar.is_file():
            raise StateError(f"JAR not found: {jar}")
        artifact = sha256_file(jar)
    row = store.add_evidence(pid, level, actor, note, artifact_sha256=artifact,
                             manifest_sha256=manifest_hash,
                             payload=dict(payload or {}, jar=str(jar) if jar else None))
    levels = {e["level"] for e in store.evidence(pid)}
    new_status = derive_status(proj["status"], levels)
    if new_status != proj["status"]:
        store.update_project(pid, status=new_status)
    row["project_status"] = new_status
    return row
