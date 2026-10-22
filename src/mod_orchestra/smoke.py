"""R5 QA automation: dedicated-server smoke run (SERVER_BOOT_PASS without a human watching).

Runs `gradlew runServer` in the project's isolated run/ directory under a one-use approval
(it executes the built mod), pre-accepts the Minecraft EULA only because the approval text says
so, waits for `Done (…)!`, checks the log for errors mentioning this mod, sends `stop`, and
records SERVER_BOOT_PASS (actor controller, pointer = log) or opens a repair task with the
offending lines. Client boot and in-game content remain the user's to verify.
"""
from __future__ import annotations
import os
import re
from pathlib import Path

from .broker import run_watch
from .build import _gradle_launcher, _require_current_generator, BUILDABLE_STATUSES, log_path
from .evidence import record_evidence
from .fabric import validate_generated
from .redact import redact
from .state import Store, StateError

SMOKE_TIMEOUT = int(os.environ.get("CRAFTCTL_SMOKE_TIMEOUT", "600"))
READY = re.compile(r"Done \([\d.]+s\)! For help, type \"help\"")


def smoke_log_path(root: Path) -> Path:
    return root / ".mod-orchestra" / "logs" / "latest-server-smoke.log"


def request_smoke(store: Store, pid: str) -> dict:
    proj = store.project(pid)
    if proj["status"] not in ("BUILD_PASSED_GAME_UNTESTED", "GAME_VERIFIED"):
        raise StateError("Server smoke needs a BUILD_PASS on the current source first (craftctl build)")
    root = Path(proj["root"])
    args = {"root": str(root), "task": "runServer", "version": proj["spec"]["profile"]}
    return store.request_approval(pid, "run_dedicated_server_smoke", args,
        "Start the Minecraft dedicated server with the built mod in " + redact(str(root)) + "/run (isolated; your saves are not touched). "
        "This accepts the Minecraft EULA (https://aka.ms/MinecraftEULA) in run/eula.txt on your behalf, waits for the server to finish booting, then stops it.")


def _mod_errors(text: str, mod_id: str) -> list[str]:
    hits = []
    for line in text.splitlines():
        low = line.lower()
        if ("/error]" in low or "/fatal]" in low or "exception" in low) and mod_id in low:
            hits.append(line.strip()[:300])
    return hits[:20]


def server_smoke(store: Store, pid: str, approval_id: str) -> dict:
    proj = store.project(pid)
    if proj["status"] not in BUILDABLE_STATUSES:
        raise StateError("Generate and build first")
    root = Path(proj["root"])
    _require_current_generator(root)
    checked = validate_generated(root)
    if checked["status"] != "PASS":
        raise StateError("Generated files changed since generation; refusing to run: " + "; ".join(checked["problems"][:5]))
    gradle = _gradle_launcher(root)
    if gradle is None:
        raise StateError("No Gradle wrapper in workspace")
    args = {"root": str(root), "task": "runServer", "version": proj["spec"]["profile"]}
    if not store.consume_approval(approval_id, pid, "run_dedicated_server_smoke", args):
        raise StateError("An unexpired, one-use, specifically approved server smoke run is required")
    run_dir = root / "run"
    run_dir.mkdir(exist_ok=True)
    (run_dir / "eula.txt").write_text("eula=true\n", encoding="utf8")
    props = run_dir / "server.properties"
    if not props.is_file():
        props.write_text("online-mode=false\nserver-port=25599\nmax-players=1\nview-distance=2\n", encoding="utf8")  # no level-type: flat w/o generator-settings logs an ERROR (F1)
    log = smoke_log_path(root)
    rec = run_watch([str(gradle), "--no-daemon", "--console=plain", "runServer"], cwd=root, log=log, timeout=SMOKE_TIMEOUT,
                    ready=READY, stop_input="stop\n")
    text = log.read_text(encoding="utf8", errors="replace")
    errors = _mod_errors(text, pid)
    loaded = bool(re.search(rf"^\s*- {re.escape(pid)} ", text, re.M))
    result = {"log": str(log), "ready": rec["ready"], "mod_loaded": loaded, "mod_errors": errors, "exit_code": rec["exit_code"],
              "duration_s": rec["duration_s"], "status": "SERVER_BOOT_PASS" if rec["ready"] and loaded and not errors else "SERVER_BOOT_FAILED"}
    store.add_event(pid, "controller", "SERVER_SMOKE_RESULT", result)
    if result["status"] == "SERVER_BOOT_PASS":
        ev = record_evidence(store, pid, "SERVER_BOOT_PASS", actor="controller",
                             note=f"dedicated server booted with {pid} loaded; no mod errors in {log.name}")
        result["evidence"] = {"id": ev["id"]}
    else:
        from .repair import open_repair_task
        why = ("mod errors: " + " | ".join(errors[:3])) if errors else ("mod not in loaded list" if rec["ready"] else "server did not reach Done")
        try:
            result["repair"] = open_repair_task(store, pid, reason=f"server smoke failed: {why}", source="server-smoke")
        except StateError as exc:
            result["repair"] = {"exhausted": True, "error": str(exc)}
    return result


def run_client(store: Store, pid: str) -> dict:
    """Launch the game client for this project from any directory (no approval: it is the same action as
    `gradlew runClient` the user already runs by hand, in the project's isolated run/ dir). Blocks until the
    game closes; the user watches the window, so nothing is recorded automatically."""
    proj = store.project(pid)
    root = Path(proj["root"])
    if proj["status"] not in BUILDABLE_STATUSES:
        raise StateError("Generate and build first")
    gradle = _gradle_launcher(root)
    if gradle is None:
        raise StateError("No Gradle wrapper in workspace")
    log = root / ".mod-orchestra" / "logs" / "latest-client.log"
    from .broker import run_logged
    rec = run_logged([str(gradle), "--no-daemon", "--console=plain", "runClient"], cwd=root, log=log, timeout=6 * 3600)
    text = log.read_text(encoding="utf8", errors="replace")
    loaded = bool(re.search(rf"^\s*- {re.escape(pid)} ", text, re.M))
    mods = re.search(r"Loading (\d+) mods", text)
    store.add_event(pid, "user", "CLIENT_RUN", {"exit_code": rec["exit_code"], "duration_s": rec["duration_s"], "mod_loaded": loaded})
    return {"project": pid, "exit_code": rec["exit_code"], "duration_s": rec["duration_s"], "mod_loaded": loaded,
            "mods_loaded": int(mods.group(1)) if mods else None, "log": str(log),
            "next": [f'craftctl evidence {pid} CLIENT_BOOT_PASS --note "Loading {mods.group(1) if mods else "N"} mods: - {pid} 1.0.0"' if loaded else "client did not load the mod; check the log",
                     f'craftctl evidence {pid} CONTENT_VERIFIED --note "<exactly what you saw>"']}
