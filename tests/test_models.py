"""R6 slice 2: MODEL tasks, designer MCP wiring, deliverable validation and installation."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import provider as pmod, workflow
from mod_orchestra.dispatch import dispatch
from mod_orchestra.models import SAFE_DIR, SAFE_SERVER, blockbench_server_config, install_model, validate_model_files
from mod_orchestra.geckolib import placeholder_geo, placeholder_animation
from mod_orchestra.fabric import placeholder_png
from mod_orchestra.provider import FakeProvider, TaskEnvelope
from mod_orchestra.spec import Mob
from mod_orchestra.state import Store
from mod_orchestra.validation import InputError

ROOT = Path(__file__).resolve().parents[1]
IDEA = "items: gem; mobs: sky critter; tab: Critters"


def handoff(task, status="DONE", files=()):
    h = {"task": task, "status": status, "scope": "model", "changed_files": list(files),
         "checks_run": [{"command": "bbmodel_geckolib_validate require_idle_walk", "exit_code": 0}],
         "evidence": {"level": "STATIC", "pointer": "models/"}, "risks": [], "unknowns": [], "needs_user": [], "next_agent": "coder"}
    return "```handoff\n" + json.dumps(h) + "\n```"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="C", mod_id="c_mod", package="com.x.c", idea=IDEA)
        workflow.plan_project(self.store, "c_mod"); workflow.approve_spec(self.store, "c_mod"); workflow.generate_project(self.store, "c_mod")
        self.ws = Path(proj["root"]); self.models = self.ws / "models"; self.models.mkdir(exist_ok=True)

    def deliver(self, mob="sky_critter", geo=None, anim=None, png=None):
        m = Mob(identifier=mob, label="x")
        (self.models / f"{mob}.bbmodel").write_text("{}")
        (self.models / f"{mob}.geo.json").write_text(json.dumps(geo or placeholder_geo(m)))
        (self.models / f"{mob}.animation.json").write_text(json.dumps(anim or placeholder_animation(m)))
        (self.models / f"{mob}.png").write_bytes(png or placeholder_png("t", 64, 32))


class Planning(Base):
    def test_model_task_sits_between_scaffold_and_build(self):
        tasks = {t["id"]: t for t in self.store.tasks("c_mod")}
        self.assertEqual(tasks["c_mod:MODEL:sky_critter"]["role"], "designer")
        self.assertEqual(tasks["c_mod:MODEL:sky_critter"]["state"], "READY")  # SCAFFOLD done by generate
        self.assertEqual(tasks["c_mod:BUILD"]["state"], "BACKLOG")

    def test_designer_run_gets_the_blockbench_server_and_instructions(self):
        captured = {}
        def fake_run(cmd, *, cwd, log, timeout, env, stdin_text=None):
            for i, a in enumerate(cmd):
                if a == "--mcp-config": captured["mcp"] = json.loads(Path(cmd[i + 1]).read_text())
            captured["prompt"] = stdin_text
            log.parent.mkdir(parents=True, exist_ok=True); log.write_text("$ x\n" + json.dumps({"result": handoff("c_mod:MODEL:sky_critter", "FAILED")}))
            return {"pid": 1, "exit_code": 0, "killed": False, "timeout_s": timeout, "duration_s": 1.0, "cmd": cmd}
        with patch.object(pmod, "run_logged", fake_run):
            prov = pmod.ClaudeCodeProvider(binary="claude-fake")
            env = TaskEnvelope("c_mod", "c_mod:MODEL:sky_critter", "designer", "t", self.ws, "# packet", "## Your job on this task (designer)")
            prov.run(env, self.ws / ".mod-orchestra/runs/r.log")
        srv = captured["mcp"]["mcpServers"]["blockbench"]
        self.assertEqual(srv["command"], "node"); self.assertEqual(Path(srv["args"][0]), SAFE_SERVER)
        self.assertEqual(srv["args"][1:], ["--root", str(self.ws / "models"), "--allow-write"])
        self.assertIn("minecraft-orchestra", captured["mcp"]["mcpServers"])
        self.assertIn("designer", captured["prompt"])


class Deliverables(Base):
    def test_valid_set_passes_and_installs_over_placeholders(self):
        self.deliver()
        out = dispatch(self.store, "c_mod", task_id="c_mod:MODEL:sky_critter", provider=FakeProvider(handoff("c_mod:MODEL:sky_critter", files=["models/sky_critter.geo.json"])))
        self.assertEqual(out["task_state"], "DONE", out.get("error"))
        res = self.ws / "src/main/resources/assets/c_mod"
        self.assertEqual(json.loads((res / "geo/entity/sky_critter.geo.json").read_text())["minecraft:geometry"][0]["description"]["identifier"], "geometry.sky_critter")
        self.assertTrue((res / "animations/entity/sky_critter.animation.json").is_file())
        self.assertIn("MODEL_INSTALLED", [e["kind"] for e in self.store.events("c_mod")])
        from mod_orchestra.fabric import validate_generated
        self.assertEqual(validate_generated(self.ws)["status"], "PASS", "installed files must be accepted as a revision")
        self.assertEqual(out["handoff"]["model"]["bones"], ["body", "head", "leg0", "leg1", "leg2", "leg3"])
        self.assertTrue((self.models / "sky_critter.bbmodel").is_file(), "editable source stays in models/")

    def test_missing_or_wrong_deliverables_fail_the_task_with_reason(self):
        out = dispatch(self.store, "c_mod", task_id="c_mod:MODEL:sky_critter", provider=FakeProvider(handoff("c_mod:MODEL:sky_critter")))
        self.assertEqual(out["task_state"], "FAILED"); self.assertIn("deliverables missing", out["error"])
        self.store.requeue("c_mod:MODEL:sky_critter", "retry")
        geo = placeholder_geo(Mob(identifier="other", label="x"))  # wrong identifier
        self.deliver(geo=geo)
        with self.assertRaisesRegex(InputError, "geometry.sky_critter"):
            validate_model_files(self.ws, "sky_critter")
        anim = placeholder_animation(Mob(identifier="sky_critter", label="x")); anim["animations"]["animation.sky_critter.walk"]["bones"]["tail"] = {}
        self.deliver(anim=anim)
        with self.assertRaisesRegex(InputError, "not in geo.json"):
            validate_model_files(self.ws, "sky_critter")
        self.deliver(png=placeholder_png("t", 32, 32))
        with self.assertRaisesRegex(InputError, "geo declares 64x32"):
            validate_model_files(self.ws, "sky_critter")
        bad = placeholder_animation(Mob(identifier="sky_critter", label="x")); del bad["animations"]["animation.sky_critter.idle"]
        self.deliver(anim=bad)
        with self.assertRaisesRegex(InputError, "lacks animation.sky_critter.idle"):
            validate_model_files(self.ws, "sky_critter")


class VendoredServer(unittest.TestCase):
    def test_packaged_copy_matches_tools_dir(self):
        for rel in ["package.json", "SHA256SUMS.txt"] + [f"src/{p.name}" for p in (ROOT / "tools/blockbench-mcp-safe/src").glob("*.mjs")]:
            self.assertEqual((ROOT / "tools/blockbench-mcp-safe" / rel).read_bytes(), (SAFE_DIR / rel).read_bytes(), rel)

    def test_server_has_no_dependencies_and_no_network_or_exec(self):
        pkg = json.loads((SAFE_DIR / "package.json").read_text())
        self.assertFalse(pkg.get("dependencies")); self.assertEqual(pkg.get("license"), "MIT")
        src = "\n".join(p.read_text(encoding="utf8") for p in (SAFE_DIR / "src").glob("*.mjs"))
        for bad in ("child_process", "fetch(", "new Function", "node:http", "node:net", "eval("):
            self.assertNotIn(bad, src, bad)

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_server_starts_and_lists_tools(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        cfg = blockbench_server_config(Path(tmp.name))
        p = subprocess.Popen([cfg["command"]] + cfg["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}) + "\n")
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n"); p.stdin.flush()
        tools = None
        for _ in range(10):
            line = p.stdout.readline()
            try: msg = json.loads(line)
            except Exception: continue
            if msg.get("id") == 2: tools = [t["name"] for t in msg["result"]["tools"]]; break
        p.stdin.close(); p.wait(timeout=10)
        self.assertIsNotNone(tools)
        for needed in ("bbmodel_geckolib_create", "bbmodel_edit", "bbmodel_geckolib_upsert_animation", "bbmodel_geckolib_validate",
                       "bbmodel_geckolib_export_geometry", "bbmodel_geckolib_export_animations", "bbmodel_geckolib_set_texture", "bbmodel_render"):
            self.assertIn(needed, tools)


if __name__ == "__main__":
    unittest.main()
