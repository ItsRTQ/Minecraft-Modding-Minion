"""SEC-001: atomic staging install."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import fabric, workflow
from mod_orchestra.fabric import STAGING_DIRNAME, sweep_orphan_stagings, staging_dir_for
from mod_orchestra.spec import interpret
from mod_orchestra.config import SUPPORTED_PROFILE
from mod_orchestra.state import Store, StateError


class Staging(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.projects = base / "projects"; self.projects.mkdir()
        self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", self.projects); p.start(); self.addCleanup(p.stop)
        proj = workflow.new_project(self.store, name="Crystal Frontier", mod_id="cf_mod", package="com.x.cf", idea="items: gem")
        workflow.plan_project(self.store, "cf_mod"); workflow.approve_spec(self.store, "cf_mod")
        self.root = Path(proj["root"])

    def test_success_installs_atomically_and_leaves_no_staging(self):
        out = workflow.generate_project(self.store, "cf_mod")
        self.assertTrue((self.root / "build.gradle").is_file())
        self.assertRegex(out["staged_as"], r"^crystal_frontier-cf_mod-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual(list((self.projects / STAGING_DIRNAME).iterdir()), [])
        self.assertEqual(out["static_validation"]["status"], "PASS")

    def test_failure_never_touches_final_path(self):
        with patch.object(fabric, "verified_wrapper_file", side_effect=StateError("boom")):
            with self.assertRaisesRegex(StateError, "boom"):
                workflow.generate_project(self.store, "cf_mod")
        self.assertFalse(self.root.exists())
        self.assertEqual(list((self.projects / STAGING_DIRNAME).iterdir()), [])

    def test_simulated_crash_leaves_only_staging_and_sweep_removes_old_ones(self):
        # A crash = exception that skips our cleanup; emulate by raising BaseException subclass we don't catch.
        class Crash(BaseException):
            pass
        with patch.object(fabric, "os") as fake_os:
            fake_os.replace.side_effect = Crash()
            fake_os.name = "posix"
            with self.assertRaises(Crash):
                fabric.generate(workflow.read_spec(self.store.project("cf_mod")["spec"]), self.root)
        self.assertFalse(self.root.exists())
        leftovers = list((self.projects / STAGING_DIRNAME).iterdir())
        self.assertEqual(len(leftovers), 1)
        # Fresh staging is kept; an old one is swept.
        self.assertEqual(sweep_orphan_stagings(self.projects, max_age=3600), [])
        old = time.time() - 7200
        import os; os.utime(leftovers[0], (old, old))
        self.assertEqual(sweep_orphan_stagings(self.projects, max_age=3600), [leftovers[0].name])
        self.assertEqual(list((self.projects / STAGING_DIRNAME).iterdir()), [])

    def test_staging_name_omits_slug_when_equal_to_id(self):
        spec = interpret(name="Crystal Example", mod_id="crystal_example", package="com.x.c", idea="items: a_gem", profile=SUPPORTED_PROFILE)
        self.assertRegex(staging_dir_for(spec, self.projects / "crystal_example").name, r"^crystal_example-\d{8}-")

    def test_nonempty_final_dir_is_refused_before_staging(self):
        self.root.mkdir(); (self.root / "keep.txt").write_text("mine")
        with self.assertRaises(Exception):
            workflow.generate_project(self.store, "cf_mod")
        self.assertTrue((self.root / "keep.txt").is_file())


if __name__ == "__main__":
    unittest.main()
