"""Item catalog for the UI's drop picker.

Vanilla item icons are read, on the user's machine only, from the Minecraft client jar that Loom
already downloaded into the Gradle caches for this profile (they are Mojang's assets and are never
copied into the repo or shipped). The mod's own items come from assets/<mod>/textures/item.
Texture file names match item ids for the vast majority of items; the picker shows the name and a
wrong id is caught later by the dedicated-server smoke ("Unknown item"). Nothing here is required
for generation: the user can always type ids by hand.
"""
from __future__ import annotations
import functools
import os
import re
import zipfile
from pathlib import Path

from .state import Store
from .validation import InputError

ITEM_PREFIX = "assets/minecraft/textures/item/"
BLOCK_PREFIX = "assets/minecraft/textures/block/"
# texture names that are not item ids (animation frames, overlays, template parts)
SKIP = re.compile(r"(_overlay|_pulling_\d|_base|_pattern|_\d+$|^barrier$|^structure_void$|^light_\d+|^debug|^air$|^empty_|^spawn_egg|_handle$|_head$|_frame$|^bundle_|^fishing_rod_cast|^crossbow_(arrow|firework|pulling))")


def candidate_jars(workspace: Path | None = None) -> list[Path]:
    """Jars that may contain the client assets, most specific first."""
    out: list[Path] = []
    if workspace:
        out += sorted((workspace / ".gradle" / "loom-cache").rglob("minecraft-merged-*.jar"))
        out += sorted((workspace / ".gradle" / "loom-cache").rglob("*.jar"))
    home = Path(os.environ.get("GRADLE_USER_HOME") or (Path.home() / ".gradle"))
    loom = home / "caches" / "fabric-loom"
    if loom.is_dir():
        out += sorted(loom.rglob("minecraft-client*.jar")) + sorted(loom.rglob("minecraft-merged*.jar")) + sorted(loom.rglob("*client*.jar"))
    seen, uniq = set(), []
    for p in out:
        if p.is_file() and p not in seen:
            seen.add(p); uniq.append(p)
    return uniq


@functools.lru_cache(maxsize=4)
def _index(jar: str) -> dict:
    items, blocks = [], []
    with zipfile.ZipFile(jar) as z:
        for n in z.namelist():
            if n.startswith(ITEM_PREFIX) and n.endswith(".png"):
                name = n[len(ITEM_PREFIX):-4]
                if "/" not in name and not SKIP.search(name):
                    items.append(name)
            elif n.startswith(BLOCK_PREFIX) and n.endswith(".png"):
                name = n[len(BLOCK_PREFIX):-4]
                if "/" not in name and not SKIP.search(name) and not re.search(r"_(top|bottom|side|front|back|inner|outer|stage\d|on|off|lit|open|closed|end|up|down|north|south|east|west)$", name):
                    blocks.append(name)
    return {"items": sorted(set(items)), "blocks": sorted(set(blocks))}


def find_assets_jar(workspace: Path | None = None) -> Path | None:
    for jar in candidate_jars(workspace):
        try:
            with zipfile.ZipFile(jar) as z:
                if ITEM_PREFIX + "diamond.png" in z.namelist():
                    return jar
        except (zipfile.BadZipFile, OSError):
            continue
    return None


def item_catalog(store: Store, pid: str) -> dict:
    proj = store.project(pid)
    ws = Path(proj["root"])
    jar = find_assets_jar(ws)
    vanilla = _index(str(jar)) if jar else {"items": [], "blocks": []}
    mod_items = sorted(p.stem for p in (ws / "src/main/resources/assets" / pid / "textures/item").glob("*.png")) if ws.is_dir() else []
    mod_blocks = sorted(p.stem for p in (ws / "src/main/resources/assets" / pid / "textures/block").glob("*.png")) if ws.is_dir() else []
    return {"source_jar": str(jar) if jar else None,
            "note": None if jar else "Vanilla icons appear after the first build (Loom downloads the game jar); you can still type ids by hand.",
            "mod": {"items": mod_items, "blocks": mod_blocks},
            "vanilla": vanilla}


def vanilla_texture(workspace: Path, kind: str, name: str) -> bytes:
    if kind not in ("item", "block") or not re.fullmatch(r"[a-z0-9_]+", name):
        raise InputError("Bad texture request")
    jar = find_assets_jar(workspace)
    if not jar:
        raise InputError("No Minecraft jar available yet")
    prefix = ITEM_PREFIX if kind == "item" else BLOCK_PREFIX
    with zipfile.ZipFile(jar) as z:
        try:
            return z.read(f"{prefix}{name}.png")
        except KeyError:
            raise InputError("Unknown texture")
