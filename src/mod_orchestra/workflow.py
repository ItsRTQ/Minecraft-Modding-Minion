"""Coordinator: typed actions, bounded planning, approval and deterministic execution."""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
from .config import PROJECTS, PROFILE, save_json
from .fabric import generate, validate_generated
from .spec import interpret, read_spec
from .state import Store, StateError
from .validation import InputError, project_id


def new_project(store: Store, *, name: str, mod_id: str, package: str, idea: str, profile: str | None = None) -> dict:
    pid = project_id(mod_id)
    spec = interpret(name=name, mod_id=pid, package=package, idea=idea, profile=profile or PROFILE["id"])
    root = (PROJECTS / pid).resolve()
    if root.exists() and any(root.iterdir()):
        raise InputError("Workspace already exists; never overwrite an existing project")
    result = store.create_project(pid, str(root), name, spec.to_dict())
    return {"id": result["id"], "root": result["root"], "spec": result["spec"], "questions": spec.questions}


def plan_project(store: Store, pid: str) -> dict:
    project = store.project(pid)
    spec = read_spec(project["spec"])
    tasks = [
        {"id": f"{pid}:SPEC", "role": "interpreter", "title": "Review, resolve questions, approve idea", "ready": True},
        {"id": f"{pid}:SCAFFOLD", "role": "coder", "title": "Generate new Fabric starter workspace"},
    ]
    edges = [(f"{pid}:SPEC", f"{pid}:SCAFFOLD")]
    for index, feat in enumerate(spec.features, 1):
        tid = f"{pid}:CONTENT:{index:02d}"
        tasks.append({"id": tid, "role": "designer" if feat.kind == "block" else "coder", "title": f"Generate {feat.kind}: {feat.label}"})
        edges.append((f"{pid}:SCAFFOLD", tid))
    tasks.append({"id": f"{pid}:BUILD", "role": "debugger", "title": "Compile with trusted approved Gradle toolchain"})
    tasks.append({"id": f"{pid}:GAME", "role": "qa", "title": "Launch isolated Minecraft test and verify behavior"})
    if spec.features:
        edges.extend((f"{pid}:CONTENT:{i:02d}", f"{pid}:BUILD") for i in range(1, len(spec.features) + 1))
    else:
        edges.append((f"{pid}:SCAFFOLD", f"{pid}:BUILD"))
    edges.append((f"{pid}:BUILD", f"{pid}:GAME"))
    store.set_tasks(pid, tasks, edges)
    store.update_project(pid, status="PLAN_READY")
    return {"project": pid, "tasks": tasks, "dependencies": edges, "blocking_questions": spec.questions,
            "note": "This is a bounded deterministic implementation plan, not a full AI-generated engineering plan."}


def approve_spec(store: Store, pid: str) -> None:
    project = store.project(pid)
    spec = read_spec(project["spec"])
    if spec.questions:
        raise StateError("Blocking questions remain. Update the idea in a new project: " + " | ".join(spec.questions))
    if project["spec_state"] != "DRAFT":
        raise StateError("Spec is already approved")
    store.update_project(pid, spec_state="APPROVED")
    if not store.tasks(pid):
        plan_project(store, pid)
    tid = pid + ":SPEC"
    task = store.claim(tid, "interpreter")
    if task is None or not store.finish(tid, "interpreter", task["version"], [{"kind": "SPEC_REVIEW", "value": hashlib.sha256(json.dumps(spec.to_dict(), sort_keys=True).encode()).hexdigest()}]):
        raise StateError("Failed to complete SPEC task")
    store.refresh_ready(pid)


def generate_project(store: Store, pid: str) -> dict:
    project = store.project(pid)
    if project["spec_state"] != "APPROVED":
        raise StateError("Spec approval required before generation")
    if project["status"] != "PLAN_READY":
        raise StateError("Generation is only allowed once per approved new project")
    t_id = pid + ":SCAFFOLD"
    lease = store.claim(t_id, "coder", ttl=600)
    if not lease:
        raise StateError("Scaffold task unavailable")
    output = generate(read_spec(project["spec"]), Path(project["root"]))
    checked = validate_generated(Path(project["root"]))
    if checked["status"] != "PASS":
        raise StateError("Generated source failed static integrity validation: " + str(checked))
    if not store.finish(t_id, "coder", lease["version"], [{"kind": "STATIC_MANIFEST", "value": output["manifest"]}]):
        raise StateError("Scaffold lease expired")
    store.refresh_ready(pid)
    # Contents generated in one atomic generator step: record each as static evidence, never BUILD evidence.
    for task in store.tasks(pid):
        if ":CONTENT:" in task["id"]:
            lease = store.claim(task["id"], "generator", ttl=600)
            if lease is None:
                raise StateError("Content task unavailable")
            if not store.finish(task["id"], "generator", lease["version"], [{"kind": "STATIC_MANIFEST", "value": output["manifest"]}]):
                raise StateError("Content task lease expired")
    store.refresh_ready(pid)
    store.update_project(pid, status="SOURCE_GENERATED_UNVERIFIED")
    store.add_event(pid, "generator", "SOURCE_GENERATED", output)
    return output | {"static_validation": checked}


def summary(store: Store, pid: str) -> dict:
    project = store.project(pid)
    tasks = store.tasks(pid)
    return {"id": pid, "name": project["name"], "root": project["root"],
            "status": project["status"], "spec_state": project["spec_state"], "spec": project["spec"],
            "tasks": [{"id": t["id"], "title": t["title"], "role": t["role"], "state": t["state"]} for t in tasks],
            "approvals": [{"id": a["id"], "kind": a["kind"], "state": a["state"], "description": a["description"]} for a in store.approvals(pid)],
            "events": store.events(pid, 20)}


def export_state_markdown(store: Store, pid: str) -> str:
    data = summary(store, pid)
    lines = ["# Project State", "", f"Project: {data['name']} ({pid})", f"Status: {data['status']}",
             f"Spec: {data['spec_state']}", "", "## Task board"]
    for task in data["tasks"][:50]:
        lines.append(f"- {task['state']}: {task['id']} — {task['title']} [{task['role']}]")
    lines.extend(["", "## Recent events"])
    for event in data["events"][:10]:
        lines.append(f"- {event['kind']} by {event['actor']} (event {event['id']})")
    result = "\n".join(lines)[:7000] + "\n"
    # Deliberately bounded output. SQLite retains full event history.
    return result
