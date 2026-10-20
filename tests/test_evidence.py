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

    def test_controller_cannot_record_game_levels(self):
        for level in ("CLIENT_BOOT_PASS", "SERVER_BOOT_PASS", "CONTENT_VERIFIED"):
            with self.assertRaisesRegex(StateError, "only be recorded by the user"):
                record_evidence(self.store, "e_mod", level, actor="controller")

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
        gradlew = self.root / "gradlew"
        gradlew.write_text("#!/bin/sh\nmkdir -p build/libs; echo jar > build/libs/e_mod-1.0.0.jar; echo BUILD SUCCESSFUL\n")
        gradlew.chmod(gradlew.stat().st_mode | stat.S_IEXEC)
        approval = build_mod.request_build(self.store, "e_mod")
        self.store.decide_approval(approval["id"], True)
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

    def test_mcp_and_ui_cannot_record_evidence(self):
        for module in (mcp, ui):
            src = inspect.getsource(module)
            self.assertNotIn("record_evidence", src); self.assertNotIn("add_evidence", src)


if __name__ == "__main__":
    unittest.main()
