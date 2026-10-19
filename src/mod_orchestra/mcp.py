"""Minimal MCP stdio JSON-RPC 2.0 server (line-delimited messages).

This is an experimental API facade, not a sandbox. It deliberately exposes
NO approval-grant endpoint. The trusted local user must approve from CLI/UI.
"""
from __future__ import annotations
import json
import sys
from .state import Store
from .doctor import inspect
from .workflow import summary, plan_project, generate_project, export_state_markdown
from .capabilities import CAPABILITIES, available_tasks, handoff
from .kb import search as kb_search
from .diagnostics import project_diagnose
from .build import tail_log
from .fabric import validate_generated
from pathlib import Path

TOOLS = [
    {"name": "orchestra_doctor", "description": "Read-only Java/Gradle/Blockbench diagnostic", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "orchestra_project_status", "description": "Read project and task status", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_diagnose_build", "description": "Classify recent build log using bounded error patterns (hypotheses only)", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_logs_tail", "description": "Read the tail of the local project's latest build log", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_knowledge_search", "description": "Read-only Markdown KB search, version-filtered", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "profile": {"type": "string"}}, "required": ["query"], "additionalProperties": False}},
    {"name": "orchestra_capabilities", "description": "List the declared specialist roles and capabilities", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "orchestra_next_tasks", "description": "Read ready tasks and role suggestions", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_task_handoff", "description": "Create bounded context package for a specific task", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}, "task_id": {"type": "string"}}, "required": ["project", "task_id"], "additionalProperties": False}},
    {"name": "orchestra_project_plan", "description": "Create task DAG, once per project", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_generate_source", "description": "Generate source only for previously USER-APPROVED, empty project; no overwrite or code execution", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_footprint", "description": "Bounded Markdown project state", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
    {"name": "orchestra_validate_source", "description": "Static manifest + JSON verification; not a build or runtime check", "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"], "additionalProperties": False}},
]

def invoke(store: Store, name: str, a: dict) -> object:
    if name == "orchestra_doctor":
        return inspect()
    if name == "orchestra_diagnose_build":
        return project_diagnose(store, a["project"])
    if name == "orchestra_logs_tail":
        return tail_log(store, a["project"], 80)
    if name == "orchestra_knowledge_search":
        return kb_search(a["query"], a.get("profile"))
    if name == "orchestra_capabilities":
        return CAPABILITIES
    if name == "orchestra_next_tasks":
        return available_tasks(store, a["project"])
    if name == "orchestra_task_handoff":
        return handoff(store, a["project"], a["task_id"])
    if name == "orchestra_project_status":
        return summary(store, a["project"])
    if name == "orchestra_project_plan":
        return plan_project(store, a["project"])
    if name == "orchestra_generate_source":
        return generate_project(store, a["project"])
    if name == "orchestra_footprint":
        return export_state_markdown(store, a["project"])
    if name == "orchestra_validate_source":
        return validate_generated(Path(store.project(a["project"])["root"]))
    raise ValueError("Unknown or forbidden MCP tool")

def handle(store: Store, message: dict) -> dict | None:
    mid = message.get("id")
    method = message.get("method")
    if mid is None:  # notifications
        return None
    try:
        if method == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "minecraft-mod-orchestra", "version": "0.1.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = message.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            allowed = next((x for x in TOOLS if x["name"] == name), None)
            if allowed is None or not isinstance(args, dict):
                raise ValueError("Unknown tool or invalid arguments")
            keys = set(allowed["inputSchema"]["properties"])
            if not set(args) <= keys or not set(allowed["inputSchema"].get("required", [])) <= set(args):
                raise ValueError("Unexpected or missing arguments")
            value = invoke(store, name, args)
            result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value}]}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    except Exception as exc:
        if method == "tools/call":
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}}
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(exc)}}

def run(store: Store | None = None) -> None:
    store = store or Store()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("JSON-RPC request must be object")
            result = handle(store, payload)
        except Exception as exc:
            result = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
        if result is not None:
            print(json.dumps(result, separators=(",", ":")), flush=True)

if __name__ == "__main__":
    run()
