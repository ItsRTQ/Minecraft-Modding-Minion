"""v1 criterion 2: recipes (shaped/shapeless/cooking, counts, tags, vanilla ids), drops, creative tab, lang."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import workflow
from mod_orchestra.config import SUPPORTED_PROFILE
from mod_orchestra.spec import Drop, Recipe, interpret, read_spec, validate_spec_content
from mod_orchestra.specedit import add_drop, add_recipe, remove_recipe, set_tab
from mod_orchestra.state import Store, StateError
from mod_orchestra.validation import InputError

IDEA = "items: ruby, ruby dust; blocks: ruby ore, ruby block; tab: Ruby Stuff"


def spec_with(recipes=(), drops=(), tab="Ruby Stuff", icon="ruby"):
    base = interpret(name="R", mod_id="r_mod", package="com.x.r", idea=IDEA, profile=SUPPORTED_PROFILE)
    raw = base.to_dict() | {"recipes": [json.loads(json.dumps(r.__dict__)) for r in recipes], "drops": [d.__dict__ for d in drops], "tab": tab, "tab_icon": icon}
    return read_spec(raw)


class SpecValidation(unittest.TestCase):
    def test_text_grammar_picks_up_tab(self):
        s = interpret(name="R", mod_id="r_mod", package="com.x.r", idea=IDEA, profile=SUPPORTED_PROFILE)
        self.assertEqual((s.tab, s.tab_icon, s.schema_version), ("Ruby Stuff", "ruby", 2))

    def test_v1_specs_still_read(self):
        old = {"schema_version": 1, "name": "O", "mod_id": "o_mod", "package": "com.x.o", "idea": "items: gem", "profile": SUPPORTED_PROFILE,
               "features": [{"kind": "item", "identifier": "gem", "label": "gem"}], "questions": [], "assumptions": []}
        s = read_spec(old)
        self.assertEqual((s.recipes, s.drops, s.tab), ([], [], None))

    def test_shaped_rules(self):
        ok = Recipe(id="ruby_block", kind="shaped", result="ruby_block", pattern=("RRR", "RRR", "RRR"), key={"R": "ruby"})
        validate_spec_content(spec_with([ok]))
        for bad, msg in [
            (Recipe(id="xx", kind="shaped", result="ruby_block", pattern=("RR", "RRR"), key={"R": "ruby"}), "same width"),
            (Recipe(id="xx", kind="shaped", result="ruby_block", pattern=("RS",), key={"R": "ruby"}), "without a key"),
            (Recipe(id="xx", kind="shaped", result="ruby_block", pattern=("R",), key={"R": "emerald"}), "Unknown local ingredient"),
            (Recipe(id="xx", kind="shaped", result="nope", pattern=("R",), key={"R": "ruby"}), "Unknown result"),
            (Recipe(id="xx", kind="shaped", result="ruby", pattern=("RRRR",), key={"R": "ruby"}), "1-3 rows of 1-3"),
            (Recipe(id="Bad Id", kind="shaped", result="ruby", pattern=("R",), key={"R": "ruby"}), "snake_case"),
        ]:
            with self.assertRaisesRegex(InputError, msg):
                validate_spec_content(spec_with([bad]))

    def test_vanilla_ids_and_tags_are_accepted(self):
        r = Recipe(id="dust", kind="shapeless", result="ruby_dust", count=4, ingredients=("ruby", "minecraft:stick", "#minecraft:planks"))
        validate_spec_content(spec_with([r]))
        with self.assertRaisesRegex(InputError, "Bad tag ingredient"):
            validate_spec_content(spec_with([Recipe(id="dd", kind="shapeless", result="ruby", ingredients=("#planks",))]))

    def test_cooking_takes_exactly_one_ingredient(self):
        validate_spec_content(spec_with([Recipe(id="ss", kind="smelting", result="ruby", ingredients=("ruby_ore",), experience=0.7)]))
        with self.assertRaisesRegex(InputError, "exactly one"):
            validate_spec_content(spec_with([Recipe(id="ss", kind="smelting", result="ruby", ingredients=("ruby_ore", "ruby"))]))

    def test_drop_rules(self):
        validate_spec_content(spec_with(drops=[Drop(block="ruby_ore", item="ruby", count_min=1, count_max=3, fortune=True, silk_touch=True)]))
        with self.assertRaisesRegex(InputError, "not a block"):
            validate_spec_content(spec_with(drops=[Drop(block="ruby", item="ruby")]))
        with self.assertRaisesRegex(InputError, "Only one drop rule"):
            validate_spec_content(spec_with(drops=[Drop(block="ruby_ore", item="ruby"), Drop(block="ruby_ore", item="ruby_dust")]))

    def test_tab_icon_must_be_local(self):
        with self.assertRaisesRegex(InputError, "Tab icon"):
            validate_spec_content(spec_with(icon="emerald"))


class Generated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="R", mod_id="r_mod", package="com.x.r", idea=IDEA)
        self.root = Path(proj["root"])
        add_recipe(self.store, "r_mod", recipe_id="ruby_block", kind="shaped", result="ruby_block", pattern=["RRR", "RRR", "RRR"], key={"R": "ruby"})
        add_recipe(self.store, "r_mod", recipe_id="ruby_from_block", kind="shapeless", result="ruby", count=9, ingredients=["ruby_block"])
        add_recipe(self.store, "r_mod", recipe_id="ruby_smelt", kind="smelting", result="ruby", ingredients=["ruby_ore"], experience=0.7)
        add_recipe(self.store, "r_mod", recipe_id="pick", kind="shaped", result="minecraft:diamond_pickaxe", pattern=["RRR", " S ", " S "], key={"R": "ruby", "S": "minecraft:stick"})
        add_drop(self.store, "r_mod", block="ruby_ore", item="ruby", count_min=1, count_max=2, fortune=True, silk_touch=True)
        workflow.plan_project(self.store, "r_mod"); workflow.approve_spec(self.store, "r_mod"); workflow.generate_project(self.store, "r_mod")
        self.data = self.root / "src/main/resources/data/r_mod"

    def j(self, rel):
        return json.loads((self.data / rel).read_text())

    def test_recipe_files_follow_1_21_format(self):
        shaped = self.j("recipe/ruby_block.json")
        self.assertEqual(shaped["type"], "minecraft:crafting_shaped"); self.assertEqual(shaped["key"]["R"], {"item": "r_mod:ruby"})
        self.assertEqual(shaped["result"], {"id": "r_mod:ruby_block", "count": 1})
        less = self.j("recipe/ruby_from_block.json")
        self.assertEqual(less["ingredients"], [{"item": "r_mod:ruby_block"}]); self.assertEqual(less["result"]["count"], 9)
        smelt = self.j("recipe/ruby_smelt.json")
        self.assertEqual((smelt["type"], smelt["cookingtime"], smelt["experience"]), ("minecraft:smelting", 200, 0.7))
        self.assertEqual(smelt["result"], {"id": "r_mod:ruby"})
        pick = self.j("recipe/pick.json")
        self.assertEqual(pick["pattern"], ["RRR", " S ", " S "]); self.assertEqual(pick["key"]["S"], {"item": "minecraft:stick"})
        self.assertEqual(pick["result"]["id"], "minecraft:diamond_pickaxe")

    def test_unlock_advancements_exist(self):
        adv = self.j("advancement/recipes/ruby_block.json")
        self.assertEqual(adv["rewards"]["recipes"], ["r_mod:ruby_block"])
        self.assertEqual(adv["criteria"]["has_input"]["conditions"]["items"][0]["items"], ["r_mod:ruby"])

    def test_ore_loot_has_silk_touch_fortune_and_range(self):
        loot = self.j("loot_table/blocks/ruby_ore.json")
        children = loot["pools"][0]["entries"][0]["children"]
        self.assertEqual(children[0]["name"], "r_mod:ruby_ore"); self.assertIn("minecraft:silk_touch", json.dumps(children[0]))
        fns = {f["function"] for f in children[1]["functions"]}
        self.assertEqual(children[1]["name"], "r_mod:ruby"); self.assertIn("minecraft:apply_bonus", fns); self.assertIn("minecraft:set_count", fns)
        plain = self.j("loot_table/blocks/ruby_block.json")
        self.assertEqual(plain["pools"][0]["entries"][0]["name"], "r_mod:ruby_block")

    def test_tab_java_and_lang(self):
        java = (self.root / "src/main/java/com/x/r/ModMain.java").read_text()
        for needle in ("FabricItemGroup.builder()", 'ResourceKey.create(Registries.CREATIVE_MODE_TAB, id("r_mod_tab"))',
                       "Registry.register(BuiltInRegistries.CREATIVE_MODE_TAB, TAB_KEY, TAB)", "output.accept(RUBY_ORE_ITEM)", "new ItemStack(RUBY)"):
            self.assertIn(needle, java)
        lang = json.loads((self.root / "src/main/resources/assets/r_mod/lang/en_us.json").read_text())
        self.assertEqual(lang["itemGroup.r_mod.r_mod_tab"], "Ruby Stuff"); self.assertIn("item.r_mod.ruby", lang)

    def test_spec_edits_reset_approval_and_are_blocked_after_generation(self):
        with self.assertRaisesRegex(StateError, "cannot change once source is generated"):
            set_tab(self.store, "r_mod", label="Other", icon="ruby")


class SpecEditFlow(unittest.TestCase):
    def test_edit_returns_spec_to_draft(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name); store = Store(base / "state.sqlite")
        with patch.object(workflow, "PROJECTS", base / "projects"):
            (base / "projects").mkdir()
            workflow.new_project(store, name="R", mod_id="r_mod", package="com.x.r", idea=IDEA)
            workflow.plan_project(store, "r_mod"); workflow.approve_spec(store, "r_mod")
            out = add_recipe(store, "r_mod", recipe_id="xx", kind="shapeless", result="ruby", ingredients=["ruby_dust"])
            self.assertEqual(out["spec_state"], "DRAFT"); self.assertEqual(store.project("r_mod")["spec_state"], "DRAFT")
            self.assertEqual(remove_recipe(store, "r_mod", "xx")["recipes"], [])
            with self.assertRaises(InputError):
                add_recipe(store, "r_mod", recipe_id="yy", kind="shapeless", result="ruby", ingredients=["emerald"])


if __name__ == "__main__":
    unittest.main()
