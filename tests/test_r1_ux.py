"""R1 UX fixes from host run 2/3: H3 outdated workspace, H4 delete, H6 lease visibility/release."""
import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import build as build_mod, mcp, ui, workflow
from mod_orchestra.config import GENERATOR_VERSION, WRAPPER_FILES
from mod_orchestra.state import Store, StateError


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        self.proj = workflow.new_project(self.store, name="U", mod_id="u_mod", package="com.x.u", idea="items: gem")
        workflow.plan_project(self.store, "u_mod"); workflow.approve_spec(self.store, "u_mod")
        self.root = Path(self.proj["root"])


class OutdatedWorkspace(Base):  # H3
    def test_manifest_records_generator_version(self):
        workflow.generate_project(self.store, "u_mod")
        m = json.loads((self.root / ".mod-orchestra/generation-manifest.json").read_text())
        self.assertEqual(m["generator_version"], GENERATOR_VERSION)

    def test_missing_version_but_wrapper_present_is_fine(self):
        # host run 4 (D8): workspaces generated between the wrapper and the version marker have no
        # generator_version but DO ship the wrapper; they must stay buildable.
        workflow.generate_project(self.store, "u_mod")
        mf = self.root / ".mod-orchestra/generation-manifest.json"
        m = json.loads(mf.read_text()); m.pop("generator_version"); mf.write_text(json.dumps(m))
        self.assertEqual(build_mod.request_build(self.store, "u_mod")["kind"], "execute_gradle_build")

    def test_old_workspace_gets_specific_message(self):
        workflow.generate_project(self.store, "u_mod")
        mf = self.root / ".mod-orchestra/generation-manifest.json"
        m = json.loads(mf.read_text()); m["generator_version"] = 1
        for k in WRAPPER_FILES: m["files"].pop(k); (self.root / k).unlink()
        mf.write_text(json.dumps(m))
        with self.assertRaisesRegex(StateError, "older generator \\(v1, current v%d\\)" % GENERATOR_VERSION):
            build_mod.request_build(self.store, "u_mod")


class LeaseVisibility(Base):  # H6
    def test_unavailable_message_names_holder_and_time(self):
        self.store.claim("u_mod:SCAFFOLD", "ghost", ttl=300)
        with self.assertRaisesRegex(StateError, "LEASED by 'ghost' for \\d+s more.*craftctl release u_mod:SCAFFOLD"):
            workflow.generate_project(self.store, "u_mod")

    def test_force_release_returns_task_to_ready_and_logs(self):
        self.store.claim("u_mod:SCAFFOLD", "ghost", ttl=300)
        out = self.store.force_release("u_mod:SCAFFOLD", "ghost died")
        self.assertEqual(out["previous_holder"], "ghost")
        self.assertEqual(self.store.lease_info("u_mod:SCAFFOLD")["state"], "READY")
        self.assertIn("TASK_FORCE_RELEASED", [e["kind"] for e in self.store.events("u_mod")])
        workflow.generate_project(self.store, "u_mod")  # retry works

    def test_release_refuses_when_nothing_is_leased(self):
        with self.assertRaisesRegex(StateError, "nothing to release"):
            self.store.force_release("u_mod:SCAFFOLD", "x")
        with self.assertRaisesRegex(StateError, "Task not found"):
            self.store.force_release("u_mod:NOPE", "x")


class DeleteProject(Base):  # H4
    def test_delete_rows_keeps_workspace_by_default(self):
        workflow.generate_project(self.store, "u_mod")
        out = workflow.delete_project(self.store, "u_mod", remove_workspace=False)
        self.assertFalse(out["workspace_removed"]); self.assertTrue(out["workspace_existed"]); self.assertTrue(self.root.is_dir())
        with self.assertRaisesRegex(StateError, "Project not found"):
            self.store.project("u_mod")
        self.assertEqual(self.store.tasks("u_mod"), []); self.assertEqual(self.store.events("u_mod"), [])

    def test_delete_with_workspace_removes_directory_inside_projects_only(self):
        workflow.generate_project(self.store, "u_mod")
        out = workflow.delete_project(self.store, "u_mod", remove_workspace=True)
        self.assertTrue(out["workspace_removed"]); self.assertFalse(self.root.exists())

    def test_delete_refuses_directory_outside_projects_root(self):
        outside = Path(self.tmp.name) / "elsewhere"; outside.mkdir()
        with self.store.tx() as con:
            con.execute("UPDATE projects SET root=? WHERE id=?", (str(outside), "u_mod"))
        with self.assertRaisesRegex(StateError, "outside"):
            workflow.delete_project(self.store, "u_mod", remove_workspace=True)
        self.assertTrue(outside.is_dir())


class UserOnlySurface(unittest.TestCase):
    def test_mcp_and_ui_cannot_delete_or_force_release(self):
        for module in (mcp, ui):
            src = inspect.getsource(module)
            for symbol in ("delete_project", "force_release"):
                self.assertNotIn(symbol, src)


if __name__ == "__main__":
    unittest.main()
