"""R5 fixtures for v1 criterion 4: deliberately injected failures the repair loop must fix.

USER-ONLY and explicit. Each fault edits exactly one file and is recorded as a user-attributed
manifest revision (the user knowingly changed the source), so validate/request-build keep working
and the repair loop sees a normal "source changed, build failed" episode.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

from .fabric import accept_changes
from .state import Store, StateError
from .validation import safe_inside


def _mod_main(root: Path, package: str) -> Path:
    return root / "src/main/java" / package.replace(".", "/") / "ModMain.java"


def fault_missing_import(root: Path, package: str, mod_id: str) -> str:
    """javac: cannot find symbol (Item). Classic broken edit."""
    f = _mod_main(root, package); s = f.read_text(encoding="utf8")
    if "import net.minecraft.world.item.Item;\n" not in s:
        raise StateError("ModMain.java has no Item import to remove")
    f.write_text(s.replace("import net.minecraft.world.item.Item;\n", ""), encoding="utf8")
    return str(f.relative_to(root)).replace("\\", "/")


def fault_wrong_mapping(root: Path, package: str, mod_id: str) -> str:
    """javac: ResourceLocation(String,String) has private access — the Yarn->Mojmap mistake every porter makes."""
    f = _mod_main(root, package); s = f.read_text(encoding="utf8")
    if "ResourceLocation.fromNamespaceAndPath(MOD_ID, path)" not in s:
        raise StateError("ModMain.java does not use ResourceLocation.fromNamespaceAndPath")
    f.write_text(s.replace("ResourceLocation.fromNamespaceAndPath(MOD_ID, path)", "new ResourceLocation(MOD_ID, path)"), encoding="utf8")
    return str(f.relative_to(root)).replace("\\", "/")


def fault_bad_loot_json(root: Path, package: str, mod_id: str) -> str:
    """Valid JSON, compiles, passes static validate — but the loot table drops an item id that does not exist.
    Only the dedicated server (datapack load) reports it: the server-side fault."""
    folder = root / "src/main/resources/data" / mod_id / "loot_table/blocks"
    tables = sorted(folder.glob("*.json")) if folder.is_dir() else []
    if not tables:
        raise StateError("Project has no block loot tables to corrupt (needs at least one block)")
    f = tables[0]
    data = json.loads(f.read_text(encoding="utf8"))
    data["pools"][0]["entries"][0]["name"] = f"{mod_id}:this_item_does_not_exist"
    f.write_text(json.dumps(data, indent=2) + "\n", encoding="utf8")
    return str(f.relative_to(root)).replace("\\", "/")


FAULTS = {
    "missing-import": (fault_missing_import, "build", "javac cannot find symbol Item"),
    "wrong-mapping": (fault_wrong_mapping, "build", "javac: ResourceLocation constructor is private in 1.21.1 (Yarn habit)"),
    "bad-loot-json": (fault_bad_loot_json, "server", "dedicated server logs an error loading the mod's loot_table (unknown item id)"),
}


def inject_fault(store: Store, pid: str, name: str) -> dict:
    if name not in FAULTS:
        raise StateError(f"Unknown fault {name!r}; known: {', '.join(FAULTS)}")
    proj = store.project(pid)
    if proj["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        raise StateError("Generate source before injecting a fault")
    root = Path(proj["root"])
    fn, surfaces_in, expect = FAULTS[name]
    changed = fn(root, proj["spec"]["package"], pid)
    accepted = accept_changes(root, run_id=f"fault:{name}", actor="user", changed=[changed])
    store.add_event(pid, "user", "FAULT_INJECTED", {"fault": name, "file": changed, "surfaces_in": surfaces_in, "expect": expect})
    from .dispatch import _source_changed
    _source_changed(store, pid)
    return {"fault": name, "file": changed, "surfaces_in": surfaces_in, "expect": expect, "accepted": accepted["accepted"]}
