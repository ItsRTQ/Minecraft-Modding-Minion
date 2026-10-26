"""Tinted silhouettes, armor layers, feature textures and user uploads."""
import base64
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import workflow
from mod_orchestra.content import set_texture
from mod_orchestra.specedit import add_material, add_food
from mod_orchestra.state import Store, StateError
from mod_orchestra.textures import ITEM_MASKS, armor_layer_png, material_colors, tinted_item_png
from mod_orchestra.validation import InputError


def png_size(raw: bytes):
    return struct.unpack(">II", raw[16:24])


class Masks(unittest.TestCase):
    def test_masks_are_16x16_and_render(self):
        for name, mask in ITEM_MASKS.items():
            self.assertEqual(len(mask), 16, name); self.assertTrue(all(len(r) == 16 for r in mask), name)
            self.assertEqual(png_size(tinted_item_png(name, (200, 20, 40), (255, 120, 130))), (16, 16))

    def test_colours_stable_and_overridable(self):
        a, b = material_colors("ruby"), material_colors("ruby")
        self.assertEqual(a, b); self.assertNotEqual(material_colors("ruby")[0], material_colors("opal")[0])
        self.assertEqual(material_colors("x", "#C8102E")[0], (200, 16, 46))

    def test_armor_layers_cover_the_right_regions(self):
        l1 = armor_layer_png(1, (10, 20, 200), (80, 90, 255), ("helmet", "chestplate", "boots"))
        l2 = armor_layer_png(2, (10, 20, 200), (80, 90, 255), ("leggings",))
        self.assertEqual(png_size(l1), (64, 32)); self.assertEqual(png_size(l2), (64, 32))
        self.assertNotEqual(l1, l2)


class Generated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name); self.store = Store(base / "state.sqlite")
        p = patch.object(workflow, "PROJECTS", base / "projects"); p.start(); self.addCleanup(p.stop)
        (base / "projects").mkdir()
        proj = workflow.new_project(self.store, name="T", mod_id="t_mod", package="com.x.t", idea="items: gem; blocks: ore; mobs: fox")
        add_material(self.store, "t_mod", identifier="gemsteel", label="Gemsteel", ingredient="gem", tools=["sword"], armor=["helmet", "leggings"], color="#C8102E")
        add_food(self.store, "t_mod", identifier="gem_pie", label="Gem Pie")
        workflow.plan_project(self.store, "t_mod"); workflow.approve_spec(self.store, "t_mod"); workflow.generate_project(self.store, "t_mod")
        self.assets = Path(proj["root"]) / "src/main/resources/assets/t_mod"

    def test_generated_textures_are_tinted_not_noise(self):
        sword = (self.assets / "textures/item/gemsteel_sword.png").read_bytes()
        self.assertEqual(sword, tinted_item_png("sword", *material_colors("t_mod/gemsteel", "#C8102E")))
        self.assertEqual(png_size((self.assets / "textures/models/armor/gemsteel_layer_1.png").read_bytes()), (64, 32))
        self.assertEqual(png_size((self.assets / "textures/item/gem.png").read_bytes()), (16, 16))
        self.assertEqual((self.assets / "textures/block/ore.png").read_bytes(), tinted_item_png("block", *material_colors("t_mod/ore")))

    def test_upload_replaces_texture_as_revision(self):
        from mod_orchestra.fabric import validate_generated
        root = Path(self.store.project("t_mod")["root"])
        good = base64.b64encode(tinted_item_png("gem", (1, 2, 3), (4, 5, 6))).decode()
        out = set_texture(self.store, "t_mod", kind="item", identifier="gem", png_base64=good)
        self.assertTrue(out["file"].endswith("textures/item/gem.png")); self.assertEqual(validate_generated(root)["status"], "PASS")
        with self.assertRaisesRegex(InputError, "16x16"):
            set_texture(self.store, "t_mod", kind="item", identifier="gem", png_base64=base64.b64encode(armor_layer_png(1, (1, 1, 1), (2, 2, 2), ("helmet",))).decode())
        with self.assertRaisesRegex(InputError, "Not a PNG"):
            set_texture(self.store, "t_mod", kind="item", identifier="gem", png_base64=base64.b64encode(b"hello").decode())
        with self.assertRaisesRegex(InputError, "Unknown identifier"):
            set_texture(self.store, "t_mod", kind="item", identifier="nope", png_base64=good)
        layer = base64.b64encode(armor_layer_png(2, (9, 9, 9), (8, 8, 8), ("leggings",))).decode()
        out = set_texture(self.store, "t_mod", kind="armor_layer_2", identifier="gemsteel", png_base64=layer)
        self.assertTrue(out["file"].endswith("gemsteel_layer_2.png"))


if __name__ == "__main__":
    unittest.main()
