"""Deterministic tinted textures for tool/armor sets and simple items — stdlib only, no Mojang assets.

Silhouettes are our own 16x16 pixel masks (sword, pickaxe, axe, shovel, hoe, gem, ingot, food) and
our own armor-layer masks on the 64x32 player-model layout (helmet/chestplate/boots on layer 1,
leggings on layer 2). Each mask cell is a shade: 0 transparent, 1 outline, 2 shadow, 3 base,
4 highlight, 5 handle/wood. Colours come from the material (base + accent) and handles are brown.
"""
from __future__ import annotations
import hashlib
import struct
import zlib

# ---- 16x16 masks: rows of 16 chars; '.' transparent ----
SWORD = [
    "..............13", ".............134", "............1343", "...........1343.", "..........1343..", ".........1343...", "........1343....",
    ".......1343.....", "..2...1343......", "...2.1343.......", "....2343........", ".....22.........", "....522.........", "...56.2.........",
    "..56............", ".56.............",
]
PICKAXE = [
    "................", "......12222.....", "....12344432....", "...1344333432...", "..13433...1343..", "..1343....1343..", "..134......13...",
    "..13...5........", "......56........", ".....56.........", "....56..........", "...56...........", "..56............", ".56.............",
    "56..............", "................",
]
AXE = [
    "................", "......1221......", ".....134432.....", "....13444432....", "....13444432....", "....13444432....", "....1343332.....",
    ".....13365......", "......156.......", ".....56.........", "....56..........", "...56...........", "..56............", ".56.............",
    "56..............", "................",
]
SHOVEL = [
    "................", "........12221...", ".......134432...", ".......134432...", ".......134432...", ".......133332...", "........1565....",
    ".........56.....", "........56......", ".......56.......", "......56........", ".....56.........", "....56..........", "...56...........",
    "..56............", ".56.............",
]
HOE = [
    "................", "......122221....", ".....13444321...", ".....12333321...", "......11..56....", ".........56.....", "........56......",
    ".......56.......", "......56........", ".....56.........", "....56..........", "...56...........", "..56............", ".56.............",
    "56..............", "................",
]
GEM = [
    "................", "................", "......1111......", ".....144431.....", "....14444431....", "...1444333331...", "...1443333321...",
    "...1433333221...", "....13332221....", ".....132221.....", "......1221......", ".......11.......", "................", "................",
    "................", "................",
]
INGOT = [
    "................", "................", "................", "................", "....11111111....", "...14444443331..", "..1444433333321.",
    ".13333333333221.", ".13333322222221.", ".12222222222221.", "..111111111111..", "................", "................", "................",
    "................", "................",
]
FOOD = [
    "................", "................", ".......55.......", "......5.........", "....1111111.....", "...144443331....", "..14444333331...",
    "..14443333321...", "..13333333221...", "..13333322221...", "...1332222221...", "....11222211....", ".....111111.....", "................",
    "................", "................",
]
BLOCK = [
    "3333333333333333", "3444444444444443", "3433333333333343", "3433333333333343", "3433333333333343", "3433333333333343", "3433333333333343",
    "3433333333333343", "3433333333333343", "3433333333333343", "3433333333333343", "3433333333333343", "3433333333333343", "3433333333333343",
    "3222222222222223", "3333333333333333",
]
ITEM_MASKS = {"sword": SWORD, "pickaxe": PICKAXE, "axe": AXE, "shovel": SHOVEL, "hoe": HOE, "gem": GEM, "ingot": INGOT, "food": FOOD, "block": BLOCK}


def material_colors(identifier: str, color: str | None = None, accent: str | None = None) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Base and accent RGB. Explicit hex wins; otherwise a stable hue from the identifier."""
    if color:
        base = _hex(color)
    else:
        d = hashlib.sha256(identifier.encode()).digest()
        base = _hsv(d[0] / 255, 0.55 + d[1] / 255 * 0.3, 0.55 + d[2] / 255 * 0.3)
    acc = _hex(accent) if accent else _lighten(base, 0.35)
    return base, acc


def _hex(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
    i = int(h * 6) % 6; f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r, g, b = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]
    return int(r * 255), int(g * 255), int(b * 255)


def _lighten(c, k):
    return tuple(min(255, int(x + (255 - x) * k)) for x in c)


def _darken(c, k):
    return tuple(max(0, int(x * (1 - k))) for x in c)


def shade_palette(base, accent) -> dict[str, tuple]:
    return {"1": (*_darken(base, 0.65), 255), "2": (*_darken(base, 0.3), 255), "3": (*base, 255), "4": (*accent, 255), "5": (92, 64, 36, 255), "6": (120, 86, 50, 255)}


def png_from_pixels(width: int, height: int, pixels: list[list[tuple]]) -> bytes:
    rows = []
    for y in range(height):
        rows.append(b"\x00" + b"".join(bytes(px) for px in pixels[y]))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")


def tinted_item_png(mask_name: str, base, accent) -> bytes:
    mask = ITEM_MASKS[mask_name]
    pal = shade_palette(base, accent)
    pixels = [[pal.get(ch, (0, 0, 0, 0)) for ch in row.ljust(16, ".")] for row in mask]
    return png_from_pixels(16, 16, pixels)


# ---- armor layers (64x32, classic player-model layout) ----
# regions: (x, y, w, h) boxes of the layer texture; helmet = head box, chestplate = body + both arms,
# leggings (layer 2) = body lower + legs, boots (layer 1) = leg boxes lower part.
HEAD = [(0, 0, 32, 16)]
BODY = [(16, 16, 24, 16)]
ARM = [(40, 16, 16, 16)]
LEG = [(0, 16, 16, 16)]


def armor_layer_png(layer: int, base, accent, pieces: tuple) -> bytes:
    pal = shade_palette(base, accent)
    px = [[(0, 0, 0, 0)] * 64 for _ in range(32)]
    def fill(box, shade="3", trim=True):
        x0, y0, w, h = box
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                sh = shade
                if trim and (y == y0 or y == y0 + h - 1 or x == x0 or x == x0 + w - 1): sh = "2"
                elif y == y0 + 1 or x == x0 + 1: sh = "4"
                px[y][x] = pal[sh]
    if layer == 1:
        if "helmet" in pieces:
            for b in HEAD: fill(b)
        if "chestplate" in pieces:
            for b in BODY + ARM: fill(b)
        if "boots" in pieces:
            x0, y0, w, h = LEG[0]; fill((x0, y0 + h - 5, w, 5))
    else:
        if "leggings" in pieces:
            x0, y0, w, h = BODY[0]; fill((x0, y0 + 4, w, h - 4))
            for b in LEG: fill(b)
    return png_from_pixels(64, 32, px)
