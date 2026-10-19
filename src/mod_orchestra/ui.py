"""Local-only browser GUI with per-process bearer token; no silent shell or network install."""
from __future__ import annotations
import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import urlparse, parse_qs
from .state import Store, StateError
from .validation import InputError
from .doctor import inspect
from .workflow import new_project, plan_project, approve_spec, generate_project, summary
from .build import request_build, build_project, tail_log

MAX_BODY = 16_384

def serve(store: Store, port: int = 8765) -> None:
    if not 1024 <= port <= 65535:
        raise ValueError("Use a port between 1024 and 65535")
    token = secrets.token_urlsafe(32)
    origin = f"http://127.0.0.1:{port}"

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
                if path.startswith("/api/project/"):
                    pid = path.removeprefix("/api/project/")
                    if "/" in pid: raise InputError("Unexpected subpath")
                    return summary(store, pid)
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
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
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
