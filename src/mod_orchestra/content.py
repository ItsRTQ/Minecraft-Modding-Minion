"""Items and blocks after generation (UI "Features → Items"): add, rename, list.

Same pattern as adding a mob: the controller writes the feature's own new files deterministically
(exactly what the generator would have produced), merges the lang file, updates the spec, and
hands the one shared-file edit (ModMain constant + creative-tab line) to a coder task with the
exact snippet. Removal after generation is not offered (it would need code surgery across files);
before generation the spec is simply edited.
"""
from __future__ import annotations
import json
from dataclasses import replace
from pathlib import Path

from .fabric import accept_changes, loot_table_json, placeholder_png
from .spec import Feature, check_java_name_collisions, read_spec, validate_spec_content
from .state import Store, StateError
from .validation import InputError, normalize_id

GENERATED_STATUSES = ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED")


def list_features(store: Store, pid: str) -> list[dict]:
    proj = store.project(pid)
    ws = Path(proj["root"]); assets = ws / "src/main/resources/assets" / pid
    spec = proj["spec"]
    out = []
    for f in spec.get("features", []):
        kind = f["kind"]; key = f["identifier"]
        tex = f"src/main/resources/assets/{pid}/textures/{'block' if kind == 'block' else 'item'}/{key}.png"
        out.append({"kind": kind, "identifier": key, "label": f["label"], "texture": tex if (ws / tex).is_file() else None,
                    "recipes": [r["id"] for r in spec.get("recipes", []) if r["result"] == key or key in json.dumps(r)],
                    "drop": next((d for d in spec.get("drops", []) if d["block"] == key), None)})
    return out


def _save_spec(store: Store, pid: str, spec, reason: str) -> None:
    validate_spec_content(spec)
    with store.tx() as con:
        con.execute("UPDATE projects SET spec_json=? WHERE id=?", (json.dumps(spec.to_dict(), sort_keys=True), pid))
        store.event(con, pid, "user", "SPEC_CHANGED", {"reason": reason})


def add_feature(store: Store, pid: str, *, kind: str, label: str, identifier: str | None = None) -> dict:
    """Before generation: spec edit (approval reset). After generation: files + coder task."""
    if kind not in ("item", "block"):
        raise InputError("kind must be item or block")
    proj = store.project(pid)
    spec = read_spec(proj["spec"])
    ident = normalize_id(identifier or label, content=True)
    if ident in spec.local_ids() or any(m.identifier == ident for m in spec.mobs):
        raise InputError(f"{ident!r} already exists in this mod")
    feature = Feature(kind=kind, identifier=ident, label=label.strip() or ident)
    new_spec = replace(spec, features=list(spec.features) + [feature])
    check_java_name_collisions(new_spec.features)
    if proj["status"] not in GENERATED_STATUSES:
        from .specedit import _save
        return _save(store, pid, new_spec, f"add {kind} {ident}") | {"identifier": ident, "generated": False}
    ws = Path(proj["root"]); res = ws / "src/main/resources"; assets = res / "assets" / pid
    written: list[str] = []

    def put(rel: Path, data: bytes):
        if rel.exists():
            raise InputError(f"Refusing to overwrite {rel.relative_to(ws)}")
        rel.parent.mkdir(parents=True, exist_ok=True); rel.write_bytes(data); written.append(str(rel.relative_to(ws)).replace("\\", "/"))

    if kind == "item":
        put(assets / "models/item" / f"{ident}.json", (json.dumps({"parent": "item/generated", "textures": {"layer0": f"{pid}:item/{ident}"}}, indent=2) + "\n").encode())
        put(assets / "textures/item" / f"{ident}.png", placeholder_png(pid + "/" + ident))
    else:
        put(assets / "blockstates" / f"{ident}.json", (json.dumps({"variants": {"": {"model": f"{pid}:block/{ident}"}}}, indent=2) + "\n").encode())
        put(assets / "models/block" / f"{ident}.json", (json.dumps({"parent": "block/cube_all", "textures": {"all": f"{pid}:block/{ident}"}}, indent=2) + "\n").encode())
        put(assets / "models/item" / f"{ident}.json", (json.dumps({"parent": f"{pid}:block/{ident}"}, indent=2) + "\n").encode())
        put(assets / "textures/block" / f"{ident}.png", placeholder_png(pid + "/" + ident))
        put(res / "data" / pid / "loot_table/blocks" / f"{ident}.json", (json.dumps(loot_table_json(new_spec, ident, None), indent=2) + "\n").encode())
    lang_file = assets / "lang/en_us.json"
    lang = json.loads(lang_file.read_text(encoding="utf8")) if lang_file.is_file() else {}
    lang[f"{'block' if kind == 'block' else 'item'}.{pid}.{ident}"] = feature.label
    lang_file.write_text(json.dumps(lang, indent=2, sort_keys=True) + "\n", encoding="utf8"); written.append(f"src/main/resources/assets/{pid}/lang/en_us.json")
    _save_spec(store, pid, new_spec, f"add {kind} {ident} after generation")
    accepted = accept_changes(ws, run_id=f"add-{kind}:{ident}", actor="user", changed=written)
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid)
    const = ident.upper()
    if kind == "item":
        lines = [f'    public static final Item {const} = Registry.register(BuiltInRegistries.ITEM, id("{ident}"), new Item(new Item.Properties()));']
        tab_line = f"            output.accept({const});"; group = "INGREDIENTS"; accept_const = const
    else:
        lines = [f'    public static final Block {const} = Registry.register(BuiltInRegistries.BLOCK, id("{ident}"), new Block(BlockBehaviour.Properties.of().strength(3.0F)));',
                 f'    public static final Item {const}_ITEM = Registry.register(BuiltInRegistries.ITEM, id("{ident}"), new BlockItem({const}, new Item.Properties()));']
        tab_line = f"            output.accept({const}_ITEM);"; group = "BUILDING_BLOCKS"; accept_const = const + "_ITEM"
    java_dir = f"src/main/java/{spec.package.replace('.', '/')}"
    instructions = [f"Register the new {kind} in {java_dir}/ModMain.java (do not touch anything else):",
                    "1. Add the static field(s) next to the other content fields:"] + ["   " + l for l in lines] + [
                    "2. In onInitialize(), add the vanilla creative-tab line:",
                    f"   ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.{group}).register(entries -> entries.accept({accept_const}));",
                    "3. If the mod has its own creative tab (a TAB field with displayItems), also add inside displayItems:", "   " + tab_line.strip(),
                    "4. Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
    task_id = f"{pid}:ADD_{kind.upper()}:{ident}"
    store.add_task(pid, task_id, "coder", f"Register new {kind} {feature.label} in ModMain")
    with store.tx() as con:
        con.execute("INSERT OR IGNORE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(instructions)))
    _reopen_build(store, pid)
    store.add_event(pid, "controller", "FEATURE_ADDED", {"kind": kind, "identifier": ident, "files": written, "task": task_id})
    return {"identifier": ident, "kind": kind, "generated": True, "files": written, "accepted": accepted["accepted"], "task": task_id,
            "next": {"action": "dispatch", "payload": {"task": task_id}}}


def rename_feature(store: Store, pid: str, identifier: str, label: str) -> dict:
    """Display name only (lang). The identifier never changes."""
    label = label.strip()
    if not (1 <= len(label) <= 60):
        raise InputError("Label must be 1-60 characters")
    proj = store.project(pid); spec = read_spec(proj["spec"])
    f = next((x for x in spec.features if x.identifier == identifier), None)
    if f is None:
        raise InputError(f"Unknown feature {identifier!r}")
    new_spec = replace(spec, features=[replace(x, label=label) if x.identifier == identifier else x for x in spec.features])
    out = {"identifier": identifier, "label": label}
    if proj["status"] in GENERATED_STATUSES:
        ws = Path(proj["root"]); lang_file = ws / "src/main/resources/assets" / pid / "lang/en_us.json"
        lang = json.loads(lang_file.read_text(encoding="utf8")) if lang_file.is_file() else {}
        lang[f"{'block' if f.kind == 'block' else 'item'}.{pid}.{identifier}"] = label
        lang_file.write_text(json.dumps(lang, indent=2, sort_keys=True) + "\n", encoding="utf8")
        rel = f"src/main/resources/assets/{pid}/lang/en_us.json"
        accept_changes(ws, run_id=f"rename:{identifier}", actor="user", changed=[rel])
        _save_spec(store, pid, new_spec, f"rename {identifier}")
        from .dispatch import _source_changed, _reopen_build
        _source_changed(store, pid); _reopen_build(store, pid)
        out |= {"file": rel, "note": "Lang updated; rebuild to apply."}
    else:
        from .specedit import _save
        _save(store, pid, new_spec, f"rename {identifier}")
    return out


def remove_feature(store: Store, pid: str, identifier: str) -> dict:
    proj = store.project(pid)
    if proj["status"] in GENERATED_STATUSES:
        raise StateError("Removing content after generation is not supported yet; ask a coder task to remove it, or create a new project")
    spec = read_spec(proj["spec"])
    if identifier not in spec.local_ids():
        raise InputError(f"Unknown feature {identifier!r}")
    used = [r.id for r in spec.recipes if r.result == identifier or identifier in r.key.values() or identifier in r.ingredients] + \
           [f"drop:{d.block}" for d in spec.drops if identifier in (d.block, d.item)] + \
           [f"tab icon" for _ in [0] if spec.tab_icon == identifier] + [f"mob drop:{m.identifier}" for m in spec.mobs for d in m.drops if getattr(d, "item", d) == identifier]
    if used:
        raise InputError(f"{identifier} is used by: {', '.join(used)} — remove those first")
    from .specedit import _save
    return _save(store, pid, replace(spec, features=[x for x in spec.features if x.identifier != identifier]), f"remove {identifier}") | {"removed": identifier}
