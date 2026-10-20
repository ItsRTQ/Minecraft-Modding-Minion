"""SEC-002 process broker and SEC-003 redaction."""
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import broker, build as build_mod, redact as redact_mod, workflow
from mod_orchestra.broker import controlled_env, run_logged
from mod_orchestra.redact import redact, redact_obj
from mod_orchestra.state import Store


class Redaction(unittest.TestCase):
    def test_home_and_projects_paths_are_replaced(self):
        from mod_orchestra.config import PROJECTS, HOME
        self.assertEqual(redact(f"root={PROJECTS / 'x_mod'}"), "root=<projects>/x_mod".replace("/", os.sep) if os.name == "nt" else "root=<projects>/x_mod")
        self.assertIn("<craftctl-home>", redact(str(HOME / "state.sqlite")))
        self.assertIn("~", redact(str(Path.home() / "Documents")))

    def test_secrets_are_masked_but_keys_kept(self):
        self.assertEqual(redact("TOKEN=github_pat_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"), "TOKEN=[redacted]")
        self.assertEqual(redact("password=hunter2222"), "password=[redacted]")
        self.assertIn("[redacted]", redact("ghp_abcdefghijklmnopqrstuvwxyz1234"))
        self.assertIn("[redacted]", redact("Authorization: Bearer abcdefghijklmnop"))
        self.assertEqual(redact("BUILD SUCCESSFUL in 1m 4s"), "BUILD SUCCESSFUL in 1m 4s")

    def test_redact_obj_walks_nested_structures(self):
        out = redact_obj({"a": [{"b": "password=hunter2222"}], "n": 3})
        self.assertEqual(out, {"a": [{"b": "password=[redacted]"}], "n": 3})


class Broker(unittest.TestCase):
    def test_controlled_env_drops_unlisted_variables(self):
        with patch.dict(os.environ, {"SUPER_SECRET": "x", "PATH": os.environ.get("PATH", "")}):
            env = controlled_env()
        self.assertNotIn("SUPER_SECRET", env)
        self.assertIn("PATH", env)
        self.assertIn("-Dfile.encoding=UTF-8", env["JAVA_TOOL_OPTIONS"])

    @unittest.skipIf(os.name == "nt", "POSIX shell script")
    def test_timeout_kills_process_tree_and_reports(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        d = Path(tmp.name); script = d / "slow.sh"; pidfile = d / "child.pid"
        script.write_text(f"#!/bin/sh\nsleep 300 &\necho $! > {pidfile}\nwait\n"); script.chmod(script.stat().st_mode | stat.S_IEXEC)
        r = run_logged([str(script)], cwd=d, log=d / "log.txt", timeout=2)
        self.assertTrue(r["killed"]); self.assertEqual(r["exit_code"], 124); self.assertLess(r["duration_s"], 20)
        child = int(pidfile.read_text().strip())
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                st = Path(f"/proc/{child}/stat").read_text().split()[2]
            except FileNotFoundError:
                st = "gone"
            if st in ("gone", "Z"):
                break
            time.sleep(0.2)
        self.assertIn(st, ("gone", "Z"), "background child must not survive the tree kill")
        self.assertIn("timeout after 2s", (d / "log.txt").read_text())

    @unittest.skipIf(os.name == "nt", "POSIX shell script")
    def test_build_event_carries_broker_record(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "state.sqlite")
        p1 = patch.object(workflow, "PROJECTS", base / "projects"); p1.start(); self.addCleanup(p1.stop)
        p2 = patch.object(redact_mod, "PROJECTS", base / "projects"); p2.start(); self.addCleanup(p2.stop)
        if True:
            (base / "projects").mkdir()
            workflow.new_project(store, name="B", mod_id="b_mod", package="com.x.b", idea="items: gem")
            workflow.plan_project(store, "b_mod"); workflow.approve_spec(store, "b_mod"); workflow.generate_project(store, "b_mod")
        fake = base / "fake"; fake.write_text("#!/bin/sh\nmkdir -p build/libs; echo j > build/libs/b_mod-1.0.0.jar\n"); fake.chmod(0o755)
        a = build_mod.request_build(store, "b_mod"); store.decide_approval(a["id"], True)
        with patch.object(build_mod, "_gradle_launcher", return_value=fake):
            r = build_mod.build_project(store, "b_mod", a["id"])
        self.assertEqual(r["status"], "BUILD_PASS"); self.assertFalse(r["killed"]); self.assertIn("duration_s", r)
        ev = next(e for e in store.events("b_mod") if e["kind"] == "BUILD_RESULT")
        self.assertIn("pid", ev["payload"])
        self.assertNotIn(str(base), ev["payload"]["log"], "event payloads must be redacted")


if __name__ == "__main__":
    unittest.main()
