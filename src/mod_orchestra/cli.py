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
from .workflow import new_project, plan_project, approve_spec, generate_project, summary, export_state_markdown
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
    sub.add_parser("projects", help="List all managed projects")
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
        return store.projects()
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
            if project["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED"):
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
