"""Regression tests for pilot testing round 1 (docs/TESTING_LOG.md B1, B2, U1-U5)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import build as build_mod, workflow
from mod_orchestra.config import SUPPORTED_PROFILE
from mod_orchestra.diagnostics import project_diagnose
from mod_orchestra.spec import interpret
from mod_orchestra.state import Store, StateError
from mod_orchestra.validation import InputError, normalize_id


class JavaNameCollisions(unittest.TestCase):
    def interp(self, idea):
        return interpret(name="T", mod_id="t_mod", package="com.x.t", idea=idea, profile=SUPPORTED_PROFILE)

    def test_item_named_mod_id_collides_with_reserved_constant(self):  # B1
        with self.assertRaisesRegex(InputError, "MOD_ID.*generator reserved"):
            self.interp("items: mod_id")

    def test_item_x_item_collides_with_block_x(self):  # B2
        with self.assertRaisesRegex(InputError, "RUBY_ITEM"):
            self.interp("items: ruby_item; blocks: ruby")
        with self.assertRaisesRegex(InputError, "RUBY_ITEM"):
            self.interp("blocks: ruby; items: ruby_item")

    def test_non_colliding_names_still_pass(self):
        spec = self.interp("items: ruby, ruby_dust; blocks: ruby_ore, ruby_block")
        self.assertEqual(len(spec.features), 4)


class IdentifierMessages(unittest.TestCase):
    def test_single_char_message_states_min_length(self):  # U3
        with self.assertRaisesRegex(InputError, "2–50 chars"):
            normalize_id("a", content=True)

    def test_long_value_is_truncated_in_message(self):  # U4
        with self.assertRaises(InputError) as ctx:
            normalize_id("a" * 300, content=True)
        self.assertLess(len(str(ctx.exception)), 260)
        self.assertIn("…", str(ctx.exception))


class BuildFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.store = Store(base / "footprint.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        self.proj = workflow.new_project(self.store, name="M", mod_id="m_mod", package="com.x.m", idea="items: gem")
        workflow.plan_project(self.store, "m_mod")
        workflow.approve_spec(self.store, "m_mod")
        workflow.generate_project(self.store, "m_mod")
        self.root = Path(self.proj["root"])

    def test_missing_gradle_does_not_consume_approval(self):  # U1
        approval = build_mod.request_build(self.store, "m_mod")
        self.store.decide_approval(approval["id"], True)
        # The workspace now ships the official wrapper, so "no launcher" can only happen if it is
        # unusable; simulate that at the resolver rather than by deleting hash-tracked files.
        with patch.object(build_mod, "_gradle_launcher", return_value=None):
            with self.assertRaisesRegex(StateError, "not consumed"):
                build_mod.build_project(self.store, "m_mod", approval["id"])
        row = next(a for a in self.store.approvals("m_mod") if a["id"] == approval["id"])
        self.assertEqual(row["state"], "GRANTED", "approval must survive a BUILD_BLOCKED outcome")
        # Sanity: the old behaviour (consume first) would have left it CONSUMED.
        self.assertIsNone(row.get("used_at"))

    def test_request_build_refuses_tampered_workspace(self):  # U2
        (self.root / "build.gradle").write_text("tampered", encoding="utf8")
        with self.assertRaisesRegex(StateError, "changed since generation"):
            build_mod.request_build(self.store, "m_mod")

    def test_diagnose_without_log_reports_no_log(self):  # U5
        result = project_diagnose(self.store, "m_mod")
        self.assertEqual(result["status"], "NO_LOG")
        self.assertEqual(result["lines_reviewed"], 0)


if __name__ == "__main__":
    unittest.main()


class WrapperShipping(unittest.TestCase):
    def test_generated_workspace_ships_hash_verified_wrapper(self):
        import hashlib
        from mod_orchestra.config import WRAPPER_FILES, PROFILE
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "db.sqlite")
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            proj = workflow.new_project(store, name="W", mod_id="w_mod", package="com.x.w", idea="items: gem")
            workflow.plan_project(store, "w_mod"); workflow.approve_spec(store, "w_mod"); workflow.generate_project(store, "w_mod")
        root = Path(proj["root"])
        for relative, expected in WRAPPER_FILES.items():
            self.assertEqual(hashlib.sha256((root / relative).read_bytes()).hexdigest(), expected, relative)
        props = (root / "gradle/wrapper/gradle-wrapper.properties").read_text()
        self.assertIn(f"distributionSha256Sum={PROFILE['gradle_dist_sha256']}", props)
        self.assertIn(f"gradle-{PROFILE['gradle']}-bin.zip", props)
        if os.name != "nt":
            self.assertTrue(os.access(root / "gradlew", os.X_OK))

    def test_drifted_embedded_wrapper_is_refused(self):
        from mod_orchestra.fabric import verified_wrapper_file
        with self.assertRaisesRegex(StateError, "refusing to ship"):
            verified_wrapper_file("gradlew", "0" * 64)


class GenerateAtomicity(unittest.TestCase):
    def test_failed_generation_leaves_no_partial_workspace(self):
        from mod_orchestra import fabric
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "db.sqlite")
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            proj = workflow.new_project(store, name="A", mod_id="a_mod", package="com.x.a", idea="items: gem")
            workflow.plan_project(store, "a_mod"); workflow.approve_spec(store, "a_mod")
            with patch.object(fabric, "verified_wrapper_file", side_effect=StateError("hash drift")):
                with self.assertRaisesRegex(StateError, "hash drift"):
                    workflow.generate_project(store, "a_mod")
            self.assertFalse(Path(proj["root"]).exists(), "partial workspace must be removed")
            self.assertEqual(store.project("a_mod")["status"], "PLAN_READY")
            # And a retry succeeds once the cause is fixed.
            workflow.generate_project(store, "a_mod")
            self.assertTrue((Path(proj["root"]) / "gradlew").is_file())
