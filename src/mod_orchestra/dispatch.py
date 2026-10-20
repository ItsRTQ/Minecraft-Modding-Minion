"""R2: controller-driven dispatch of one bounded worker per READY task.

dispatch() is the only path by which an agent is started from application state:
  pick task -> lease -> envelope -> provider.run -> validate handoff -> task state + Footprint.
The worker never decides its own task state; the handoff's `status` is a claim the
controller maps onto the task after validation.
"""
from __future__ import annotations
import os
import time
from pathlib import Path

from .capabilities import CAPABILITIES, handoff
from .provider import AgentProvider, ClaudeCodeProvider, FakeProvider, TaskEnvelope, RunResult
from .redact import redact_obj
from .state import Store, StateError

DISPATCHABLE_ROLES = tuple(CAPABILITIES)        # every role may be dispatched; some will mostly produce WAITING_USER
LEASE_TTL = 3600


def pick_task(store: Store, pid: str, task_id: str | None) -> dict:
    store.refresh_ready(pid)
    tasks = store.tasks(pid)
    if task_id:
        t = next((t for t in tasks if t["id"] == task_id), None)
        if t is None:
            raise StateError(f"Task not found: {task_id}")
        if t["state"] != "READY":
            raise StateError(f"Task {task_id} is {t['state']}, not READY" + (f" (last error: {t['last_error']})" if t.get("last_error") else ""))
        return t
    ready = [t for t in tasks if t["state"] == "READY" and t["role"] in DISPATCHABLE_ROLES]
    if not ready:
        raise StateError("No READY task to dispatch; run `craftctl next <project>` to see the board")
    return ready[0]


def build_envelope(store: Store, pid: str, task: dict) -> TaskEnvelope:
    proj = store.project(pid)
    packet = handoff(store, pid, task["id"])
    return TaskEnvelope(project_id=pid, task_id=task["id"], role=task["role"], title=task["title"],
                        workspace=Path(proj["root"]), packet=packet)


def apply_outcome(store: Store, pid: str, task: dict, lease: dict, run: dict, result: RunResult) -> dict:
    worker, version = lease["lease_owner"], lease["version"]
    log = str(result.log_path)
    if result.errors or result.handoff is None:
        error = "; ".join(result.errors)[:500] or "no handoff"
        store.set_task_state(task["id"], worker, version, "FAILED", error=error)
        store.finish_run(run["id"], state="FAILED", exit_code=result.exit_code, duration_s=result.duration_s, log_path=log,
                         session_id=result.session_id, cost_usd=result.cost_usd, turns=result.turns, handoff=result.handoff, error=error)
        return {"task_state": "FAILED", "error": error}
    h = redact_obj(result.handoff)
    status = h["status"]
    if status == "DONE":
        evidence = [{"kind": "WORKER_HANDOFF", "value": f"run:{run['id']}"},
                    {"kind": h["evidence"]["level"], "value": str(h["evidence"].get("pointer") or log)}]
        store.finish(task["id"], worker, version, evidence)
        task_state = "DONE"
    elif status == "WAITING_USER":
        store.set_task_state(task["id"], worker, version, "WAITING_USER", error=None)
        task_state = "WAITING_USER"
    elif status == "BLOCKED":
        store.set_task_state(task["id"], worker, version, "BLOCKED", error="; ".join(h["unknowns"] + h["risks"])[:500])
        task_state = "BLOCKED"
    else:
        store.set_task_state(task["id"], worker, version, "FAILED", error="worker reported FAILED: " + "; ".join(h["risks"])[:400])
        task_state = "FAILED"
    store.finish_run(run["id"], state=task_state, exit_code=result.exit_code, duration_s=result.duration_s, log_path=log,
                     session_id=result.session_id, cost_usd=result.cost_usd, turns=result.turns, handoff=h, error=None)
    return {"task_state": task_state, "handoff": h}


def provider_from_env() -> AgentProvider:
    """CRAFTCTL_PROVIDER=fake (+ CRAFTCTL_FAKE_REPLY_FILE) lets the UI/CLI be exercised without Claude Code."""
    if os.environ.get("CRAFTCTL_PROVIDER") == "fake":
        path = os.environ.get("CRAFTCTL_FAKE_REPLY_FILE")
        return FakeProvider(Path(path).read_text(encoding="utf8") if path else "")
    return ClaudeCodeProvider()


def dispatch(store: Store, pid: str, *, task_id: str | None = None, provider: AgentProvider | None = None) -> dict:
    proj = store.project(pid)
    if proj["spec_state"] != "APPROVED":
        raise StateError("Dispatch requires a user-approved spec (craftctl approve-spec)")
    provider = provider or provider_from_env()
    task = pick_task(store, pid, task_id)
    worker = f"agent:{task['role']}"
    lease = store.claim(task["id"], worker, ttl=LEASE_TTL)
    if not lease:
        raise StateError(f"Could not lease {task['id']}")
    run = store.create_run(pid, task["id"], task["role"], provider.name)
    log_path = Path(proj["root"]) / ".mod-orchestra" / "runs" / f"{run['id']}.log"
    try:
        envelope = build_envelope(store, pid, task)
        result = provider.run(envelope, log_path)
    except Exception as exc:  # provider crash: release the task, record the run, re-raise
        store.release(task["id"], worker, lease["version"], f"provider error: {exc}")
        store.finish_run(run["id"], state="FAILED", exit_code=None, duration_s=None, log_path=str(log_path), error=str(exc)[:500])
        raise
    outcome = apply_outcome(store, pid, task, lease, run, result)
    store.refresh_ready(pid)
    return {"run": run["id"], "task": task["id"], "role": task["role"], "provider": provider.name,
            "exit_code": result.exit_code, "duration_s": result.duration_s, "cost_usd": result.cost_usd, "turns": result.turns,
            "log": str(log_path), **outcome}


STALE_RUN_AFTER = LEASE_TTL + 300


def reconcile_stale_runs(store: Store, pid: str) -> list[str]:
    """Restart safety: a run still RUNNING long after its lease could have expired belonged to a
    controller that died mid-dispatch. Mark it FAILED so the board is honest; the task's lease has
    expired on its own and refresh_ready puts it back to READY."""
    stale = []
    now = time.time()
    for r in store.runs(pid):
        if r["state"] == "RUNNING" and now - r["created_at"] > STALE_RUN_AFTER:
            store.finish_run(r["id"], state="FAILED", exit_code=None, duration_s=None, log_path=r.get("log_path"),
                             error="controller restarted while this run was in progress")
            stale.append(r["id"])
    store.refresh_ready(pid)
    return stale


HUMAN_NEEDED = ("WAITING_USER", "BLOCKED", "FAILED")


def orchestrate(store: Store, pid: str, *, max_runs: int = 5, max_cost_usd: float = 5.0, max_seconds: int = 3600,
                provider: AgentProvider | None = None) -> dict:
    """Coordinator loop: dispatch READY tasks one at a time until the user is needed or a budget is hit.
    Never crosses an approval gate: a WAITING_USER/BLOCKED/FAILED outcome ends the loop."""
    started = time.time()
    stale = reconcile_stale_runs(store, pid)
    runs, cost = [], 0.0
    reason = "no READY tasks"
    while True:
        if len(runs) >= max_runs:
            reason = f"max_runs ({max_runs}) reached"; break
        if cost >= max_cost_usd:
            reason = f"max_cost_usd ({max_cost_usd}) reached"; break
        if time.time() - started > max_seconds:
            reason = f"max_seconds ({max_seconds}) reached"; break
        store.refresh_ready(pid)
        if not any(t["state"] == "READY" and t["role"] in DISPATCHABLE_ROLES for t in store.tasks(pid)):
            reason = "no READY tasks"; break
        out = dispatch(store, pid, provider=provider)
        runs.append({k: out.get(k) for k in ("run", "task", "role", "task_state", "cost_usd", "duration_s", "error")})
        cost += float(out.get("cost_usd") or 0.0)
        if out["task_state"] in HUMAN_NEEDED:
            needs = (out.get("handoff") or {}).get("needs_user") or []
            reason = f"{out['task_state']} on {out['task']}" + (": " + "; ".join(needs) if needs else "")
            break
    store.add_event(pid, "controller", "ORCHESTRATE_STOPPED", {"reason": reason, "runs": len(runs), "cost_usd": round(cost, 4)})
    return {"project": pid, "runs": runs, "total_cost_usd": round(cost, 4), "elapsed_s": round(time.time() - started, 1),
            "stopped_because": reason, "stale_runs_reconciled": stale}
