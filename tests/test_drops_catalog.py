"""Neutral mobs, mob drop tables with range/chance, item catalog from a local jar, drop editing."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import catalog, workflow
from mod_orchestra.config import SUPPORTED_PROFILE
from mod_orchestra.geckolib import entity_java, entity_loot
from mod_orchestra.models import set_mob_drops
from mod_orchestra.spec import Mob, MobDrop, interpret, read_spec
from mod_orchestra.state import Store
from mod_orchestra.validation import InputError


class Neutral(unittest.TestCase):
    def test_grammar_and_java(self):
        s = interpret(name="N", mod_id="n_mod", package="com.x.n", idea="items: gem; neutral mobs: moon fox; mobs: sky critter; hostile mobs: stalker", profile=SUPPORTED_PROFILE)
        self.assertEqual({m.identifier: m.behavior for m in s.mobs}, {"moon_fox": "neutral", "sky_critter": "passive", "stalker": "hostile"})
        fox = next(m for m in s.mobs if m.identifier == "moon_fox")
        java = entity_java(s, fox)
        self.assertIn("extends PathfinderMob", java); self.assertIn("HurtByTargetGoal", java); self.assertIn("MeleeAttackGoal", java)
        self.assertNotIn("NearestAttackableTargetGoal", java); self.assertIn("ATTACK_DAMAGE", java)


class DropTables(unittest.TestCase):
    def spec(self, drops):
        base = interpret(name="D", mod_id="d_mod", package="com.x.d", idea="items: gem", profile=SUPPORTED_PROFILE).to_dict()
        return read_spec(base | {"mobs": [{"identifier": "fox", "label": "Fox", "drops": drops}]})

    def test_strings_dicts_and_objects_are_accepted(self):
        s = self.spec(["gem", {"item": "minecraft:feather", "count_min": 0, "count_max": 2, "chance": 0.5}])
        self.assertEqual(s.mobs[0].drops[0], MobDrop(item="gem")); self.assertEqual(s.mobs[0].drops[1].chance, 0.5)

    def test_loot_json(self):
        s = self.spec(["gem", {"item": "minecraft:feather", "count_min": 0, "count_max": 2, "chance": 0.25}])
        loot = entity_loot(s, s.mobs[0])
        self.assertEqual(len(loot["pools"]), 2)
        self.assertNotIn("conditions", loot["pools"][0]); self.assertEqual(loot["pools"][0]["entries"][0]["name"], "d_mod:gem")
        self.assertEqual(loot["pools"][1]["conditions"], [{"condition": "minecraft:random_chance", "chance": 0.25}])
        self.assertEqual(loot["pools"][1]["entries"][0]["functions"][0]["count"], {"type": "minecraft:uniform", "min": 0, "max": 2})
        self.assertEqual(loot["pools"][1]["entries"][0]["functions"][1]["function"], "minecraft:enchanted_count_increase")

    def test_validation(self):
        with self.assertRaisesRegex(InputError, "chance"):
            self.spec([{"item": "gem", "chance": 0}])
        with self.assertRaisesRegex(InputError, "counts"):
            self.spec([{"item": "gem", "count_min": 3, "count_max": 1}])
        with self.assertRaisesRegex(InputError, "Unknown result"):
            self.spec(["emerald"])


class Catalog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="C", mod_id="c_mod", package="com.x.c", idea="items: gem; blocks: ore; mobs: fox")
        workflow.plan_project(self.store, "c_mod"); workflow.approve_spec(self.store, "c_mod"); workflow.generate_project(self.store, "c_mod")
        self.ws = Path(proj["root"])
        # fake Minecraft client jar in the workspace's loom cache
        jar = self.ws / ".gradle" / "loom-cache" / "minecraftMaven" / "minecraft-merged-abc.jar"; jar.parent.mkdir(parents=True)
        with zipfile.ZipFile(jar, "w") as z:
            for n in ("diamond", "feather", "bow_pulling_0", "spawn_egg", "stick"):
                z.writestr(f"assets/minecraft/textures/item/{n}.png", b"\x89PNG" + n.encode())
            for n in ("stone", "oak_log_top", "furnace_front_on", "obsidian"):
                z.writestr(f"assets/minecraft/textures/block/{n}.png", b"\x89PNG" + n.encode())
        catalog._index.cache_clear()

    def test_catalog_lists_vanilla_and_mod_items_filtering_non_items(self):
        cat = catalog.item_catalog(self.store, "c_mod")
        self.assertTrue(cat["source_jar"].endswith("minecraft-merged-abc.jar"))
        self.assertEqual(cat["vanilla"]["items"], ["diamond", "feather", "stick"])
        self.assertEqual(cat["vanilla"]["blocks"], ["obsidian", "stone"])
        self.assertEqual(cat["mod"]["items"], ["gem"]); self.assertEqual(cat["mod"]["blocks"], ["ore"])
        self.assertEqual(catalog.vanilla_texture(self.ws, "item", "diamond"), b"\x89PNGdiamond")
        with self.assertRaises(InputError):
            catalog.vanilla_texture(self.ws, "item", "../etc")
        with self.assertRaises(InputError):
            catalog.vanilla_texture(self.ws, "item", "nope")

    def test_no_jar_is_a_note_not_an_error(self):
        import shutil; shutil.rmtree(self.ws / ".gradle")
        with patch.object(catalog, "candidate_jars", return_value=[]):
            cat = catalog.item_catalog(self.store, "c_mod")
        self.assertIsNone(cat["source_jar"]); self.assertIn("after the first build", cat["note"]); self.assertEqual(cat["mod"]["items"], ["gem"])

    def test_set_mob_drops_rewrites_loot_table_as_revision_and_reopens_build(self):
        from mod_orchestra.fabric import validate_generated
        with self.store.tx() as con:
            con.execute("UPDATE tasks SET state='DONE' WHERE id='c_mod:BUILD'")
        out = set_mob_drops(self.store, "c_mod", "fox", [{"item": "gem", "count_min": 1, "count_max": 3, "chance": 0.5}, "minecraft:feather"])
        loot = json.loads((self.ws / "src/main/resources/data/c_mod/loot_table/entities/fox.json").read_text())
        self.assertEqual(len(loot["pools"]), 2); self.assertEqual(loot["pools"][0]["conditions"][0]["chance"], 0.5)
        self.assertEqual(validate_generated(self.ws)["status"], "PASS")
        self.assertEqual([d["item"] for d in self.store.project("c_mod")["spec"]["mobs"][0]["drops"]], ["gem", "minecraft:feather"])
        self.assertNotEqual(next(t["state"] for t in self.store.tasks("c_mod") if t["id"] == "c_mod:BUILD"), "DONE")
        with self.assertRaisesRegex(InputError, "Unknown mob"):
            set_mob_drops(self.store, "c_mod", "dragon", [])


if __name__ == "__main__":
    unittest.main()


class ItemsAfterGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="I", mod_id="i_mod", package="com.x.i", idea="items: gem; blocks: ore; tab: Gems")
        self.ws = Path(proj["root"])

    def test_before_generation_edits_the_spec(self):
        from mod_orchestra.content import add_feature, remove_feature, rename_feature, list_features
        out = add_feature(self.store, "i_mod", kind="block", label="Moon Block")
        self.assertEqual((out["identifier"], out["generated"], out["spec_state"]), ("moon_block", False, "DRAFT"))
        self.assertEqual(rename_feature(self.store, "i_mod", "gem", "Shiny Gem")["label"], "Shiny Gem")
        self.assertEqual([f["label"] for f in list_features(self.store, "i_mod")], ["Shiny Gem", "ore", "Moon Block"])
        self.assertEqual(remove_feature(self.store, "i_mod", "moon_block")["removed"], "moon_block")
        with self.assertRaisesRegex(InputError, "already exists"):
            add_feature(self.store, "i_mod", kind="item", label="gem")

    def test_after_generation_writes_files_and_coder_task(self):
        from mod_orchestra.content import add_feature, remove_feature, rename_feature
        from mod_orchestra.fabric import validate_generated
        from mod_orchestra.state import StateError
        workflow.plan_project(self.store, "i_mod"); workflow.approve_spec(self.store, "i_mod"); workflow.generate_project(self.store, "i_mod")
        with self.store.tx() as con:
            con.execute("UPDATE tasks SET state='DONE' WHERE id='i_mod:BUILD'")
        out = add_feature(self.store, "i_mod", kind="block", label="Moon Block")
        self.assertTrue(out["generated"]); self.assertEqual(out["task"], "i_mod:ADD_BLOCK:moon_block")
        for rel in ("blockstates/moon_block.json", "models/block/moon_block.json", "models/item/moon_block.json", "textures/block/moon_block.png"):
            self.assertTrue((self.ws / "src/main/resources/assets/i_mod" / rel).is_file(), rel)
        self.assertTrue((self.ws / "src/main/resources/data/i_mod/loot_table/blocks/moon_block.json").is_file())
        self.assertEqual(validate_generated(self.ws)["status"], "PASS")
        instr = self.store.task_instructions("i_mod:ADD_BLOCK:moon_block")
        self.assertIn("MOON_BLOCK_ITEM", instr); self.assertIn("BUILDING_BLOCKS", instr); self.assertIn("output.accept(MOON_BLOCK_ITEM)", instr)
        self.assertNotEqual(next(t["state"] for t in self.store.tasks("i_mod") if t["id"] == "i_mod:BUILD"), "DONE")
        self.assertEqual([f["identifier"] for f in self.store.project("i_mod")["spec"]["features"]], ["gem", "ore", "moon_block"])
        out = rename_feature(self.store, "i_mod", "gem", "Sky Gem")
        lang = json.loads((self.ws / "src/main/resources/assets/i_mod/lang/en_us.json").read_text())
        self.assertEqual(lang["item.i_mod.gem"], "Sky Gem"); self.assertEqual(validate_generated(self.ws)["status"], "PASS")
        with self.assertRaisesRegex(StateError, "not supported yet"):
            remove_feature(self.store, "i_mod", "gem")
