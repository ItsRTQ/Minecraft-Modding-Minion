"""craftctl: honest, local-first prototype interface."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .config import PROFILE
from .doctor import inspect
from .state import Store, StateError
from .validation import InputError
from .workflow import delete_project, new_project, plan_project, approve_spec, generate_project, summary, export_state_markdown
from .fabric import validate_generated
from .build import request_build, build_project, tail_log
from .capabilities import CAPABILITIES, available_tasks, handoff
from .kb import search as kb_search
from .diagnostics import project_diagnose


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="craftctl", description="Minecraft Mod Orchestra: local-first Fabric starter")
    p.add_argument("--state-db", type=Path, help="Override local SQLite location (for isolated testing)")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Inspect OS/JDK/Gradle/Git/Blockbench/Minecraft; no changes")
    sub.add_parser("profiles", help="Print pinned candidate toolchain")
    a = sub.add_parser("kb-search", help="Find relevant Markdown knowledge notes")
    a.add_argument("query")
    a.add_argument("--profile")
    a.add_argument("--limit", type=int, default=8)
    a = sub.add_parser("new", help="Interpret idea and record a new project")
    a.add_argument("--name", required=True)
    a.add_argument("--id", required=True)
    a.add_argument("--package", required=True)
    a.add_argument("--idea", required=True)
    a = sub.add_parser("plan", help="Create dependency task graph")
    a.add_argument("project")
    a = sub.add_parser("approve-spec", help="USER-ONLY: explicitly accept deterministic specification")
    a.add_argument("project")
    a = sub.add_parser("generate", help="Generate approved new Fabric starter source (no overwrite)")
    a.add_argument("project")
    a = sub.add_parser("status", help="Show project, tasks, evidence")
    a.add_argument("project")
    a = sub.add_parser("tasks", help="List task graph state")
    a.add_argument("project")
    a = sub.add_parser("footprint", help="Generate bounded Markdown snapshot to stdout")
    a.add_argument("project")
    a.add_argument("--write", action="store_true", help="Save a bounded STATE.md inside the generated project's metadata folder")
    a = sub.add_parser("validate", help="Validate static file manifest/JSON only")
    a.add_argument("project")
    a = sub.add_parser("request-build", help="Request concrete approval for running Gradle")
    a.add_argument("project")
    a = sub.add_parser("approvals", help="List pending approvals")
    a.add_argument("project")
    a = sub.add_parser("decide", help="USER-ONLY: grant or deny a specific operation")
    a.add_argument("approval_id")
    a.add_argument("decision", choices=["grant", "deny"])
    a = sub.add_parser("dispatch", help="Run ONE bounded agent worker on a READY task (uses the user's installed Claude Code)")
    a.add_argument("project"); a.add_argument("--task", default=None, help="Task id; default: first READY task")
    a.add_argument("--provider", choices=["claude-code", "fake"], default="claude-code")
    a.add_argument("--fake-reply-file", default=None, help="With --provider fake: file whose content is the worker's reply")
    a = sub.add_parser("requeue", help="USER-ONLY: return a FAILED/WAITING_USER/BLOCKED task to READY")
    a.add_argument("task_id"); a.add_argument("--reason", default="requeued by user")
    a = sub.add_parser("add-task", help="USER-ONLY: add an ad-hoc task to a project board")
    a.add_argument("project"); a.add_argument("--id", required=True, help="Short task suffix, e.g. SAPPHIRE -> <project>:SAPPHIRE")
    a.add_argument("--role", required=True, choices=sorted(__import__("mod_orchestra.capabilities", fromlist=["CAPABILITIES"]).CAPABILITIES))
    a.add_argument("--title", required=True); a.add_argument("--after", nargs="*", default=None, help="Task ids this one depends on")
    a = sub.add_parser("orchestrate", help="USER-ONLY: dispatch READY tasks one after another until you are needed or a budget is hit")
    a.add_argument("project"); a.add_argument("--max-runs", type=int, default=5); a.add_argument("--max-cost-usd", type=float, default=5.0)
    a.add_argument("--max-seconds", type=int, default=3600)
    a.add_argument("--provider", choices=["claude-code", "fake"], default="claude-code"); a.add_argument("--fake-reply-file", default=None)
    a = sub.add_parser("accept-changes", help="USER-ONLY: accept the files a run reported as changed into the manifest (after reviewing `craftctl run <id>`)")
    a.add_argument("run_id")
    a = sub.add_parser("run", help="Show one agent run in full: handoff, error, and the end of its log")
    a.add_argument("run_id"); a.add_argument("--lines", type=int, default=60)
    a = sub.add_parser("runs", help="List agent runs for a project")
    a.add_argument("project")
    a = sub.add_parser("delete", help="USER-ONLY: remove a project from the Footprint (and its workspace with --workspace)")
    a.add_argument("project"); a.add_argument("--yes", action="store_true", help="Required; confirms the deletion")
    a.add_argument("--workspace", action="store_true", help="Also delete the generated directory (only inside the projects root)")
    a = sub.add_parser("release", help="USER-ONLY: break a stuck task lease and return the task to READY")
    a.add_argument("task_id"); a.add_argument("--reason", default="released by user")
    a = sub.add_parser("evidence", help="USER-ONLY: record what you observed (BUILD_PASS, CLIENT_BOOT_PASS, SERVER_BOOT_PASS, CONTENT_VERIFIED)")
    a.add_argument("project"); a.add_argument("level", choices=["BUILD_PASS", "CLIENT_BOOT_PASS", "SERVER_BOOT_PASS", "CONTENT_VERIFIED"])
    a.add_argument("--note", default="", help="What exactly you saw (log line, tab, behaviour)")
    a.add_argument("--jar", default=None, help="Path to the built JAR to hash (default: build/libs/<id>-*.jar for BUILD_PASS)")
    a = sub.add_parser("build", help="Execute approved, one-use, unsandboxed Gradle build")
    a.add_argument("project")
    a.add_argument("--approval-id", required=True)
    a = sub.add_parser("diagnose", help="Classify latest Gradle log with bounded known-error fingerprints")
    a.add_argument("project")
    a = sub.add_parser("logs", help="Read bounded latest build log")
    a.add_argument("project")
    a.add_argument("--lines", type=int, default=70)
    a = sub.add_parser("ui", help="Run local-only web UI")
    a.add_argument("--port", type=int, default=8765)
    a = sub.add_parser("projects", help="List all managed projects (table; --json for scripts)")
    a.add_argument("--json", action="store_true")
    sub.add_parser("capabilities", help="List available agent roles and capabilities")
    a = sub.add_parser("next", help="Select currently READY tasks")
    a.add_argument("project")
    a = sub.add_parser("handoff", help="Prepare a bounded task context for a Claude Code worker")
    a.add_argument("project")
    a.add_argument("task_id")
    sub.add_parser("mcp", help="Run stdio MCP server (no approval grant tool exposed)")
    return p


def dispatch(args: argparse.Namespace) -> object:
    if args.command == "doctor":
        return inspect()
    if args.command == "profiles":
        return PROFILE
    if args.command == "kb-search":
        return kb_search(args.query, args.profile, limit=args.limit)
    store = Store(args.state_db)
    if args.command == "new":
        return new_project(store, name=args.name, mod_id=args.id, package=args.package, idea=args.idea)
    if args.command == "projects":
        rows = store.projects()
        if args.json:
            return rows
        return projects_table(rows)
    if args.command == "capabilities":
        return CAPABILITIES
    if args.command == "next":
        return available_tasks(store, args.project)
    if args.command == "handoff":
        return handoff(store, args.project, args.task_id)
    if args.command == "plan":
        return plan_project(store, args.project)
    if args.command == "approve-spec":
        approve_spec(store, args.project)
        return {"status": "SPEC_APPROVED", "project": args.project}
    if args.command == "generate":
        return generate_project(store, args.project)
    if args.command == "status":
        return summary(store, args.project)
    if args.command == "tasks":
        return store.tasks(args.project)
    if args.command == "footprint":
        content = export_state_markdown(store, args.project)
        if args.write:
            from .validation import safe_inside
            project = store.project(args.project)
            if project["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
                raise StateError("Project workspace is not yet generated")
            root = Path(project["root"])
            target = safe_inside(root, ".mod-orchestra/STATE.md")
            target.write_text(content, encoding="utf-8")
            return {"written": str(target), "length": len(content)}
        return content
    if args.command == "validate":
        return validate_generated(Path(store.project(args.project)["root"]))
    if args.command == "request-build":
        return request_build(store, args.project)
    if args.command == "approvals":
        return store.approvals(args.project)
    if args.command == "decide":
        store.decide_approval(args.approval_id, args.decision == "grant")
        return {"status": args.decision.upper(), "id": args.approval_id}
    if args.command == "build":
        return build_project(store, args.project, args.approval_id)
    if args.command == "dispatch":
        from .dispatch import dispatch
        from .provider import FakeProvider
        provider = None
        if args.provider == "fake":
            reply = Path(args.fake_reply_file).read_text(encoding="utf8") if args.fake_reply_file else ""
            provider = FakeProvider(reply)
        return dispatch(store, args.project, task_id=args.task, provider=provider)
    if args.command == "requeue":
        return store.requeue(args.task_id, args.reason)
    if args.command == "add-task":
        tid = f"{args.project}:{args.id.upper()}"
        return store.add_task(args.project, tid, args.role, args.title, after=args.after)
    if args.command == "orchestrate":
        from .dispatch import orchestrate
        from .provider import FakeProvider
        provider = None
        if args.provider == "fake":
            reply = Path(args.fake_reply_file).read_text(encoding="utf8") if args.fake_reply_file else ""
            provider = FakeProvider(reply)
        return orchestrate(store, args.project, max_runs=args.max_runs, max_cost_usd=args.max_cost_usd, max_seconds=args.max_seconds, provider=provider)
    if args.command == "accept-changes":
        from .dispatch import accept_run_changes
        return accept_run_changes(store, args.run_id)
    if args.command == "run":
        from .redact import redact
        for p in store.projects():
            for r in store.runs(p["id"]):
                if r["id"] == args.run_id:
                    tail = ""
                    lp = Path(r["log_path"]) if r.get("log_path") else None
                    if lp and lp.is_file():
                        tail = redact("\n".join(lp.read_text(encoding="utf8", errors="replace").splitlines()[-args.lines:]))
                    return r | {"log_tail": tail}
        raise StateError(f"Run not found: {args.run_id}")
    if args.command == "runs":
        return [{k: v for k, v in r.items() if k != "handoff"} | {"handoff_status": (r["handoff"] or {}).get("status")} for r in store.runs(args.project)]
    if args.command == "delete":
        if not args.yes:
            raise StateError("Refusing to delete without --yes")
        return delete_project(store, args.project, remove_workspace=args.workspace)
    if args.command == "release":
        return store.force_release(args.task_id, args.reason)
    if args.command == "evidence":
        from .evidence import record_evidence
        return record_evidence(store, args.project, args.level, actor="user", note=args.note,
                               jar=Path(args.jar) if args.jar else None)
    if args.command == "diagnose":
        return project_diagnose(store, args.project)
    if args.command == "logs":
        return tail_log(store, args.project, args.lines)
    if args.command == "ui":
        from .ui import serve
        serve(store, args.port)
        return None
    if args.command == "mcp":
        from .mcp import run
        run(store)
        return None
    raise AssertionError(args.command)


def projects_table(rows: list[dict]) -> str:
    if not rows:
        return "No projects yet. Create one with: craftctl new --name ... --id ... --package ... --idea ..."
    import datetime as _dt
    cols = ["id", "name", "status", "spec", "created"]
    data = [[r["id"], r["name"], r["status"], r["spec_state"],
             _dt.datetime.fromtimestamp(r["created_at"]).strftime("%Y-%m-%d %H:%M")] for r in rows]
    widths = [max(len(c), *(len(d[i]) for d in data)) for i, c in enumerate(cols)]
    line = lambda cells: "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells)).rstrip()
    return "\n".join([line(cols), line(["-" * w for w in widths])] + [line(d) for d in data])


def main(argv: list[str] | None = None) -> int:
    try:
        result = dispatch(parser().parse_args(argv))
        if result is not None:
            print(json.dumps(result, indent=2, ensure_ascii=False) if not isinstance(result, str) else result)
        return 0
    except (InputError, StateError, OSError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
