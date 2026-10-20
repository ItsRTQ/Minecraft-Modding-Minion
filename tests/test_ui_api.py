"""UI API (R2 activity feed, U7 verification views): drives the real HTTP server on a free port."""
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import dispatch as dmod, ui, workflow
from mod_orchestra.provider import FakeProvider
from mod_orchestra.state import Store

REPLY = '```handoff\n' + json.dumps({"task": "u_mod:SCAFFOLD", "status": "WAITING_USER", "scope": "s", "changed_files": [],
        "checks_run": [], "evidence": {"level": "STATIC", "pointer": "src"}, "risks": [], "unknowns": [],
        "needs_user": ["craftctl request-build u_mod"], "next_agent": "none"}) + '\n```'


class UiApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name); cls.store = Store(base / "state.sqlite")
        cls.p1 = patch.object(workflow, "PROJECTS", base / "projects"); cls.p1.start(); (base / "projects").mkdir()
        cls.p2 = patch.object(dmod, "provider_from_env", lambda: FakeProvider(REPLY)); cls.p2.start()
        cls.p3 = patch.object(ui.webbrowser, "open", lambda *a, **k: None); cls.p3.start()
        import socket
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); cls.port = sock.getsockname()[1]
        cls.token_holder = {}
        real_token = ui.secrets.token_urlsafe
        def capture(n=32):
            t = real_token(n); cls.token_holder.setdefault("t", t); return t
        cls.p4 = patch.object(ui.secrets, "token_urlsafe", capture); cls.p4.start()
        cls.thread = threading.Thread(target=ui.serve, args=(cls.store, cls.port), daemon=True); cls.thread.start()
        for _ in range(50):
            if "t" in cls.token_holder: break
            time.sleep(0.05)
        time.sleep(0.2)
        workflow.new_project(cls.store, name="U", mod_id="u_mod", package="com.x.u", idea="items: gem")
        workflow.plan_project(cls.store, "u_mod"); workflow.approve_spec(cls.store, "u_mod")

    @classmethod
    def tearDownClass(cls):
        for p in (cls.p1, cls.p2, cls.p3, cls.p4): p.stop()
        cls.tmp.cleanup()

    def call(self, path, payload=None, origin=True):
        headers = {"Authorization": "Bearer " + self.token_holder["t"]}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"; data = json.dumps(payload).encode()
            if origin: headers["Origin"] = f"http://127.0.0.1:{self.port}"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_1_verification_endpoints_before_source(self):
        self.assertEqual(self.call("/api/project/u_mod/validate")[1]["status"], "NO_SOURCE")
        self.assertEqual(self.call("/api/project/u_mod/diagnose")[1]["status"], "NO_LOG")
        self.assertEqual(self.call("/api/project/u_mod/runs")[1], [])
        self.assertEqual(self.call("/api/project/u_mod/bogus")[0], 400)

    def test_2_dispatch_runs_in_background_and_is_single_flight(self):
        code, out = self.call("/api/project/u_mod/dispatch", {})
        self.assertEqual((code, out["started"]), (200, True))
        for _ in range(40):
            runs = self.call("/api/project/u_mod/runs")[1]
            if runs and runs[0]["state"] != "RUNNING": break
            time.sleep(0.1)
        self.assertEqual(runs[0]["state"], "WAITING_USER")
        self.assertEqual(runs[0]["handoff"]["needs_user"], ["craftctl request-build u_mod"])
        detail = self.call("/api/run/" + runs[0]["id"])[1]
        self.assertIn("handoff", detail["log_tail"])
        self.assertFalse(self.call("/api/project/u_mod")[1]["dispatching"])

    def test_3_requeue_and_evidence_from_ui(self):
        code, out = self.call("/api/task/u_mod:SCAFFOLD/requeue", {})
        self.assertEqual((code, out["state"]), (200, "READY"))
        code, out = self.call("/api/project/u_mod/evidence", {"level": "CLIENT_BOOT_PASS", "note": "x"})
        self.assertEqual(code, 400); self.assertIn("cannot be attached", out["error"])

    def test_4_post_without_origin_is_refused(self):
        self.assertEqual(self.call("/api/project/u_mod/dispatch", {}, origin=False)[0], 403)


if __name__ == "__main__":
    unittest.main()
