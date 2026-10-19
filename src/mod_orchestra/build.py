"""Explicit user-authorized, bounded Gradle build runner. Not an OS sandbox."""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path
from .fabric import validate_generated
from .state import Store, StateError


def request_build(store: Store, pid: str) -> dict:
    proj = store.project(pid)
    if proj["status"] != "SOURCE_GENERATED_UNVERIFIED":
        raise StateError("Only a generated starter may be built")
    root = Path(proj["root"])
    # We approve a concrete workspace build, not a generic command execution.
    args = {"root": str(root), "task": "build", "version": proj["spec"]["profile"]}
    return store.request_approval(pid, "execute_gradle_build", args,
        "Run Gradle build scripts and resolve dependencies for " + str(root) + " (Gradle is executable project code; not sandboxed)")


def build_project(store: Store, pid: str, approval_id: str) -> dict:
    proj = store.project(pid)
    if proj["status"] != "SOURCE_GENERATED_UNVERIFIED":
        raise StateError("Project has not generated a buildable source tree")
    root = Path(proj["root"])
    checked = validate_generated(root)
    if checked["status"] != "PASS":
        raise StateError("Generated files changed; investigate before build")
    args = {"root": str(root), "task": "build", "version": proj["spec"]["profile"]}
    if not store.consume_approval(approval_id, pid, "execute_gradle_build", args):
        raise StateError("An unexpired, one-use, specifically approved build is required")
    gradle = (root / "gradlew.bat") if os.name == "nt" else (root / "gradlew")
    if not gradle.is_file():
        candidate = shutil.which("gradle")
        if not candidate:
            store.add_event(pid, "build", "BUILD_BLOCKED", {"reason": "No Gradle wrapper or installed Gradle"})
            raise StateError("No Gradle wrapper or installed Gradle. Run the project README's trusted Gradle-wrapper setup first.")
        gradle = Path(candidate)
    cmd = [str(gradle), "--no-daemon", "build"]
    log_dir = root / ".mod-orchestra" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / "latest-build.log"
    env = os.environ.copy()
    env["JAVA_TOOL_OPTIONS"] = (env.get("JAVA_TOOL_OPTIONS", "") + " -Dfile.encoding=UTF-8").strip()
    try:
        with log.open("wb") as f:
            proc = subprocess.run(cmd, cwd=root, stdout=f, stderr=subprocess.STDOUT, env=env, timeout=900, check=False)
            code = proc.returncode
    except subprocess.TimeoutExpired:
        code = 124
    result = {"exit_code": code, "log": str(log), "status": "BUILD_PASS" if code == 0 else "BUILD_FAILED"}
    store.add_event(pid, "build", "BUILD_RESULT", result)
    if code == 0:
        tid = pid + ":BUILD"
        lease = store.claim(tid, "build", ttl=300)
        if lease:
            store.finish(tid, "build", lease["version"], [{"kind": "BUILD_EXIT_0", "value": str(log)}])
            store.refresh_ready(pid)
        store.update_project(pid, status="BUILD_PASSED_GAME_UNTESTED")
    else:
        store.update_project(pid, status="BUILD_FAILED")
    return result


def tail_log(store: Store, pid: str, limit: int = 100) -> str:
    proj = store.project(pid)
    log = Path(proj["root"]) / ".mod-orchestra" / "logs" / "latest-build.log"
    if not log.is_file():
        return "No build log available"
    # Bound content reading and output; never flood the model context.
    with log.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 65536))
        data = f.read()
    lines = data.decode("utf-8", "replace").splitlines()[-min(max(limit, 1), 250):]
    return "\n".join(lines)
