"""R5: autonomous repair loop (v1 criterion 4).

A failed build never waits for a human to open a ticket: the controller creates a
<project>:REPAIR:<n> task for the debugger with the diagnosis attached. orchestrate() then
dispatches it like any other task. After MAX_ATTEMPTS failures for the same episode the task
is BLOCKED and the user is told. The trusted build stays the user's: the debugger verifies
its own fix with the workspace gradle, the user confirms with `craftctl build`.
"""
from __future__ import annotations
import re
from pathlib import Path

from .build import log_path, tail_log
from .diagnostics import project_diagnose
from .state import Store, StateError

MAX_ATTEMPTS = 3
REPAIR_RE = re.compile(r":REPAIR:(\d+)$")


def repair_attempt_number(task_id: str) -> int | None:
    m = REPAIR_RE.search(task_id)
    return int(m.group(1)) if m else None


def _episode_attempts(store: Store, pid: str) -> list[dict]:
    """Repair tasks since the last non-repair success (BUILD_PASS evidence or DONE non-repair build)."""
    tasks = [t for t in store.tasks(pid) if ":REPAIR:" in t["id"]]
    # An episode ends when a repair task reaches DONE; everything after belongs to a new episode.
    episode: list[dict] = []
    for t in sorted(tasks, key=lambda t: repair_attempt_number(t["id"]) or 0):
        if t["state"] == "DONE":
            episode = []
        else:
            episode.append(t)
    return episode


def open_repair_task(store: Store, pid: str, *, reason: str, source: str, after: list[str] | None = None) -> dict:
    """Create the next REPAIR task, or BLOCK the last one if the episode is exhausted."""
    existing = [t for t in store.tasks(pid) if ":REPAIR:" in t["id"]]
    n = max((repair_attempt_number(t["id"]) or 0 for t in existing), default=0) + 1
    episode = _episode_attempts(store, pid)
    open_ones = [t for t in episode if t["state"] in ("READY", "LEASED", "RUNNING", "BACKLOG")]
    if open_ones:
        return {"task": open_ones[0]["id"], "state": open_ones[0]["state"], "note": "repair already pending"}
    if len(episode) >= MAX_ATTEMPTS:
        store.add_event(pid, "controller", "REPAIR_EXHAUSTED", {"attempts": len(episode), "reason": reason[:300]})
        raise StateError(f"Repair loop exhausted after {len(episode)} attempts; a human must look. Last failure: {reason[:200]}")
    tid = f"{pid}:REPAIR:{n}"
    store.add_task(pid, tid, "debugger", f"Repair build failure (attempt {len(episode) + 1}/{MAX_ATTEMPTS}): {reason[:80]}", after=after)
    store.add_event(pid, "controller", "REPAIR_OPENED", {"task": tid, "attempt": len(episode) + 1, "source": source, "reason": reason[:300]})
    return {"task": tid, "state": "READY", "attempt": len(episode) + 1, "max": MAX_ATTEMPTS}


def repair_context(store: Store, pid: str) -> str:
    """Diagnosis block appended to a REPAIR task's handoff packet."""
    diag = project_diagnose(store, pid)
    lines = ["", "## Build failure diagnosis (from craftctl diagnose)"]
    if diag.get("status") == "NO_LOG":
        lines.append("- No build log on the controller side; the failure was reported by a worker. Run `./gradlew build` yourself first.")
    else:
        if not diag["classifications"]:
            lines.append("- No known fingerprint matched; read the log tail below.")
        for c in diag["classifications"][:4]:
            lines.append(f"- **{c['kind']}**: {c['symptom'][:160]}")
            lines.append(f"  Guidance: {c['guidance'][:200]}")
    tail = tail_log(store, pid, 60)
    lines += ["", "## Build log tail (controller build, redacted)", "```", tail[-4000:], "```"]
    smoke = Path(store.project(pid)["root"]) / ".mod-orchestra" / "logs" / "latest-server-smoke.log"
    if smoke.is_file():
        from .redact import redact
        text = smoke.read_text(encoding="utf8", errors="replace")
        hits = [l.strip()[:300] for l in text.splitlines() if ("/ERROR]" in l or "/FATAL]" in l or "Exception" in l) and pid in l][-15:]
        lines += ["", "## Dedicated server smoke: lines mentioning this mod (redacted)", "```", redact("\n".join(hits) or "(none)"), "```"]
    lines += ["",
              "## Repair contract",
              "One root cause, one minimal fix. Verify with `./gradlew build` (or `gradlew.bat build`) in this workspace and",
              "report BUILD_PASS only with its exit 0 in checks_run. If the cause is outside this workspace or needs a",
              "decision from the user, report BLOCKED with the question under unknowns."]
    return "\n".join(lines)
