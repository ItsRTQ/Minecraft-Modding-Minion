"""Local-only browser GUI with per-process bearer token; no silent shell or network install."""
from __future__ import annotations
import threading
import time
import json
from pathlib import Path
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import urlparse, parse_qs, parse_qs
from .state import Store, StateError
from .validation import InputError
from .doctor import inspect
from .workflow import new_project, plan_project, approve_spec, generate_project, summary
from .build import request_build, build_project, tail_log
from .diagnostics import project_diagnose
from .dispatch import dispatch, orchestrate
from .guidance import guidance
from .feedback import model_gallery, file_for_ui, give_model_feedback
from .interpreter import answer
from .smoke import request_smoke, server_smoke, run_client
from .evidence import record_evidence
from .fabric import validate_generated
from .redact import redact

MAX_BODY = 16_384

def serve(store: Store, port: int = 8765) -> None:
    if not 1024 <= port <= 65535:
        raise ValueError("Use a port between 1024 and 65535")
    token = secrets.token_urlsafe(32)
    origin = f"http://127.0.0.1:{port}"

    inflight: dict[str, dict] = {}   # pid -> {"thread", "job", "started", "result", "error"}
    inflight_lock = threading.Lock()

    def start_job(pid: str, job: str, fn) -> dict:
        """The UI is the user: long operations (agent runs, builds, smokes, the game client) run in a
        background thread; the page polls /api/project/<id> whose `job` field shows progress and outcome."""
        with inflight_lock:
            cur = inflight.get(pid)
            if cur and cur["thread"].is_alive():
                raise StateError(f"'{cur['job']}' is still running for this project; wait for it to finish")
            entry = {"job": job, "started": time.time(), "result": None, "error": None}
            def worker():
                try:
                    entry["result"] = fn()
                except Exception as exc:
                    entry["error"] = str(exc)[:500]
                    store.add_event(pid, "controller", "JOB_ERROR", {"job": job, "error": str(exc)[:400]})
                finally:
                    entry["finished"] = time.time()
            th = threading.Thread(target=worker, name=f"{job}-{pid}", daemon=True)
            entry["thread"] = th
            inflight[pid] = entry
            th.start()
        return {"started": True, "project": pid, "job": job}

    def job_status(pid: str) -> dict | None:
        e = inflight.get(pid)
        if not e:
            return None
        return {"job": e["job"], "running": e["thread"].is_alive(), "elapsed_s": round(time.time() - e["started"], 1),
                "result": e.get("result") if not e["thread"].is_alive() else None, "error": e.get("error")}

    def start_dispatch(pid: str, task_id: str | None) -> dict:
        return start_job(pid, "dispatch", lambda: dispatch(store, pid, task_id=task_id))

    def run_detail(run_id: str) -> dict:
        for p in store.projects():
            for r in store.runs(p["id"]):
                if r["id"] == run_id:
                    log = Path(r["log_path"]) if r.get("log_path") else None
                    tail = ""
                    if log and log.is_file():
                        data = log.read_bytes()[-32768:]
                        tail = redact("\n".join(data.decode("utf-8", "replace").splitlines()[-150:]))
                    return r | {"log_tail": tail}
        raise InputError("Run not found")

    class Handler(BaseHTTPRequestHandler):
        server_version = "CraftCtlLocal/0.1"
        def log_message(self, fmt, *args):
            pass  # Do not log secrets or request bodies.

        def response(self, data: object, code: int = 200) -> None:
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self) -> bool:
            host = self.headers.get("Host", "")
            return host == f"127.0.0.1:{port}" and self.headers.get("Authorization") == "Bearer " + token

        def handle_api(self, body: dict | None = None):
            path = urlparse(self.path).path
            payload = body or {}
            if self.command == "GET":
                if path == "/api/doctor": return inspect()
                if path == "/api/projects": return store.projects()
                if path.startswith("/api/run/"):
                    run_id = path.removeprefix("/api/run/")
                    if "/" in run_id: raise InputError("Unexpected run path")
                    return run_detail(run_id)
                if path.startswith("/api/project/"):
                    parts = path.strip("/").split("/")
                    if len(parts) == 3:
                        pid = parts[2]
                        js = job_status(pid)
                        return summary(store, pid) | {"dispatching": bool(js and js["running"]), "job": js,
                                                      "guidance": guidance(store, pid), "gallery": model_gallery(store, pid)}
                    if len(parts) != 4: raise InputError("Unexpected subpath")
                    pid, op = parts[2], parts[3]
                    if op == "runs": return store.runs(pid)
                    if op == "guidance": return guidance(store, pid)
                    if op == "gallery": return model_gallery(store, pid)
                    if op == "job": return job_status(pid) or {"job": None, "running": False}
                    if op == "logs": return {"text": tail_log(store, pid, 200)}
                    if op == "diagnose": return project_diagnose(store, pid)
                    if op == "validate":
                        root = Path(store.project(pid)["root"])
                        if not (root / ".mod-orchestra" / "generation-manifest.json").is_file():
                            return {"status": "NO_SOURCE", "checked": 0, "problems": ["No generated source yet"]}
                        return validate_generated(root)
                    raise InputError("Unknown project query")
            else:
                if path == "/api/projects":
                    return new_project(store, name=payload["name"], mod_id=payload["id"], package=payload["package"], idea=payload["idea"])
                if path.startswith("/api/project/"):
                    parts = path.strip("/").split("/")
                    if len(parts) != 4:
                        raise InputError("Invalid project command")
                    pid, op = parts[2], parts[3]
                    if op == "plan": return plan_project(store, pid)
                    if op == "approve":
                        approve_spec(store, pid)
                        return {"status": "SPEC_APPROVED"}
                    if op == "generate": return generate_project(store, pid)
                    if op == "request-build": return request_build(store, pid)
                    if op == "build": return build_project(store, pid, payload["approval_id"])
                    if op == "dispatch": return start_dispatch(pid, payload.get("task") or None)
                    if op == "orchestrate":
                        return start_job(pid, "orchestrate", lambda: orchestrate(store, pid, max_runs=int(payload.get("max_runs", 5)),
                                                                                    max_cost_usd=float(payload.get("max_cost_usd", 5.0))))
                    if op == "build-bg": return start_job(pid, "build", lambda: build_project(store, pid, payload["approval_id"]))
                    if op == "request-smoke": return request_smoke(store, pid)
                    if op == "server-smoke": return start_job(pid, "server-smoke", lambda: server_smoke(store, pid, payload["approval_id"]))
                    if op == "run-client": return start_job(pid, "run-client", lambda: run_client(store, pid))
                    if op == "answer": return answer(store, pid, str(payload.get("text", "")))
                    if op == "feedback": return give_model_feedback(store, pid, str(payload.get("mob", "")), str(payload.get("text", "")))
                    if op == "decide":
                        store.decide_approval(payload["approval_id"], bool(payload.get("grant", True)))
                        return {"id": payload["approval_id"], "status": "GRANT" if payload.get("grant", True) else "DENY"}
                    if op == "evidence":
                        return record_evidence(store, pid, payload["level"], actor="user", note=str(payload.get("note", "")),
                                               jar=Path(payload["jar"]) if payload.get("jar") else None)
                if path.startswith("/api/task/"):
                    parts = path.strip("/").split("/")
                    if len(parts) != 4 or parts[3] != "requeue": raise InputError("Unknown task command")
                    return store.requeue(parts[2], str(payload.get("reason") or "requeued from UI"))
                if path.startswith("/api/approval/"):
                    approval_id = path.removeprefix("/api/approval/")
                    if "/" in approval_id: raise InputError("Unexpected approval path")
                    store.decide_approval(approval_id, payload["grant"] is True)
                    return {"status": "DECIDED"}
            raise InputError("Unknown endpoint")

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/app.js", "/style.css"):
                if self.headers.get("Host") != f"127.0.0.1:{port}":
                    return self.response({"error": "Invalid host"}, 403)
                resource = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[path]
                raw = files("mod_orchestra").joinpath("static", resource).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8" if path == "/" else "text/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if path.startswith("/api/project/") and path.endswith("/file"):
                # <img src> cannot carry headers: the page passes the token as a query parameter for this one route.
                qs = parse_qs(urlparse(self.path).query)
                if self.headers.get("Host") != f"127.0.0.1:{port}" or qs.get("token", [""])[0] != token:
                    return self.response({"error": "Unauthorized"}, 403)
                pid = path.strip("/").split("/")[2]
                try:
                    file_path, ctype = file_for_ui(store, pid, qs.get("path", [""])[0])
                except (InputError, StateError) as exc:
                    return self.response({"error": str(exc)}, 404)
                raw = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("Content-Length", str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
                return
            if not self.authorized(): return self.response({"error": "Unauthorized"}, 403)
            try:
                self.response(self.handle_api())
            except (InputError, StateError, ValueError, KeyError, OSError) as exc:
                self.response({"error": str(exc)}, 400)

        def do_POST(self):
            if not self.authorized() or self.headers.get("Origin") != origin:
                return self.response({"error": "Unauthorized or invalid origin"}, 403)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= MAX_BODY:
                    return self.response({"error": "Request too large"}, 413)
                payload = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(payload, dict): raise InputError("JSON object required")
                self.response(self.handle_api(payload))
            except (InputError, StateError, ValueError, KeyError, OSError) as exc:
                self.response({"error": str(exc)}, 400)

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        url = f"{origin}/#{token}"
        print("Local app URL: " + url, flush=True)
        print("Access token is stored only in this process. Close the terminal to stop the server.", flush=True)
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
