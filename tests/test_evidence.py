"""Evidence levels (DEVELOPMENT_PATH R1): BUILD_PASS, CLIENT_BOOT_PASS, SERVER_BOOT_PASS, CONTENT_VERIFIED."""
import inspect
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import build as build_mod, mcp, ui, workflow
from mod_orchestra.evidence import record_evidence, LEVELS
from mod_orchestra.state import Store, StateError


class EvidenceFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.store = Store(base / "footprint.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="E", mod_id="e_mod", package="com.x.e", idea="items: gem; blocks: ore")
        workflow.plan_project(self.store, "e_mod"); workflow.approve_spec(self.store, "e_mod"); workflow.generate_project(self.store, "e_mod")
        self.root = Path(proj["root"])

    def fake_jar(self):
        jar = self.root / "build" / "libs" / "e_mod-1.0.0.jar"
        jar.parent.mkdir(parents=True, exist_ok=True); jar.write_bytes(b"not really a jar")
        return jar

    def test_game_evidence_requires_prior_build_pass(self):
        with self.assertRaisesRegex(StateError, "needs a prior BUILD_PASS"):
            record_evidence(self.store, "e_mod", "CLIENT_BOOT_PASS", actor="user")

    def test_controller_cannot_record_client_or_content_levels(self):
        for level in ("CLIENT_BOOT_PASS", "CONTENT_VERIFIED"):
            with self.assertRaisesRegex(StateError, "only be recorded by the user"):
                record_evidence(self.store, "e_mod", level, actor="controller")
        # SERVER_BOOT_PASS may be recorded by the controller (server-smoke observed the log) but never by a worker
        with self.assertRaisesRegex(StateError, "never by a worker"):
            record_evidence(self.store, "e_mod", "SERVER_BOOT_PASS", actor="agent:qa")

    def test_manual_build_pass_hashes_jar_and_unlocks_game_levels(self):
        jar = self.fake_jar()
        row = record_evidence(self.store, "e_mod", "BUILD_PASS", actor="user", jar=jar, note="built by hand")
        self.assertEqual(len(row["artifact_sha256"]), 64)
        self.assertEqual(row["project_status"], "BUILD_PASSED_GAME_UNTESTED")
        for level in ("CLIENT_BOOT_PASS", "SERVER_BOOT_PASS"):
            self.assertEqual(record_evidence(self.store, "e_mod", level, actor="user")["project_status"], "BUILD_PASSED_GAME_UNTESTED")
        self.assertEqual(record_evidence(self.store, "e_mod", "CONTENT_VERIFIED", actor="user")["project_status"], "GAME_VERIFIED")

    def test_tampered_source_refuses_evidence(self):
        self.fake_jar()
        (self.root / "build.gradle").write_text("tampered", encoding="utf8")
        with self.assertRaisesRegex(StateError, "changed since generation"):
            record_evidence(self.store, "e_mod", "BUILD_PASS", actor="user")

    def test_missing_jar_is_an_error(self):
        with self.assertRaisesRegex(StateError, "JAR not found"):
            record_evidence(self.store, "e_mod", "BUILD_PASS", actor="user", jar=self.root / "nope.jar")

    def test_unknown_level_rejected(self):
        with self.assertRaisesRegex(StateError, "Unknown evidence level"):
            record_evidence(self.store, "e_mod", "LGTM", actor="user")

    @unittest.skipIf(os.name == "nt", "fake gradlew is a POSIX shell script")
    def test_approved_build_records_build_pass_automatically(self):
        # Do not overwrite the shipped (hash-tracked) gradlew; inject a fake launcher instead.
        fake = Path(self.tmp.name) / "fake-gradlew"
        fake.write_text("#!/bin/sh\nmkdir -p build/libs; echo jar > build/libs/e_mod-1.0.0.jar; echo BUILD SUCCESSFUL\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        approval = build_mod.request_build(self.store, "e_mod")
        self.store.decide_approval(approval["id"], True)
        with patch.object(build_mod, "_gradle_launcher", return_value=fake):
            result = build_mod.build_project(self.store, "e_mod", approval["id"])
        self.assertEqual(result["status"], "BUILD_PASS")
        self.assertEqual(len(result["evidence"]["artifact_sha256"]), 64)
        ev = self.store.evidence("e_mod")
        self.assertEqual([(e["level"], e["actor"]) for e in ev], [("BUILD_PASS", "controller")])
        self.assertEqual(self.store.project("e_mod")["status"], "BUILD_PASSED_GAME_UNTESTED")

    def test_summary_and_footprint_expose_evidence(self):
        record_evidence(self.store, "e_mod", "BUILD_PASS", actor="user", jar=self.fake_jar(), note="manual")
        self.assertEqual(workflow.summary(self.store, "e_mod")["evidence"][0]["level"], "BUILD_PASS")
        self.assertIn("## Evidence", workflow.export_state_markdown(self.store, "e_mod"))

    def test_mcp_cannot_record_evidence(self):
        # The UI is the authenticated local user (it already decides approvals), so it may record evidence.
        # Agents reach the controller only through MCP, which must never be able to.
        src = inspect.getsource(mcp)
        self.assertNotIn("record_evidence", src); self.assertNotIn("add_evidence", src)
        self.assertNotIn("dispatch", src); self.assertNotIn("requeue", src)


if __name__ == "__main__":
    unittest.main()
