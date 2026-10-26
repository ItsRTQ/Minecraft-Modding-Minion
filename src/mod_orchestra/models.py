"""R6 slice 2: the designer worker authors a real Blockbench/GeckoLib model for each mob.

Task <project>:MODEL:<mob> (role designer) runs with two MCP servers: minecraft-orchestra and the
vendored zero-dependency `blockbench-mcp-safe` (tools/blockbench-mcp-safe, packaged under resources/),
started by the controller with --root <workspace>/models --allow-write. The worker writes
models/<mob>.bbmodel, exports models/<mob>.geo.json + models/<mob>.animation.json, and leaves a 64x32
(or declared) PNG next to them. The controller validates the trio against the mob and the
DefaultedEntityGeoModel layout, then installs it over the placeholders as a manifest revision.
The .bbmodel stays in models/ as the editable source for the user.
"""
from __future__ import annotations
import json
import re
import shutil
from pathlib import Path

from .fabric import accept_changes
from .state import Store, StateError
from .validation import InputError

SAFE_DIR = Path(__file__).resolve().parent / "resources" / "blockbench-mcp-safe"
SAFE_SERVER = SAFE_DIR / "src" / "server.mjs"
MODEL_DIR = "models"


def blockbench_server_config(workspace: Path) -> dict:
    """MCP server entry for the designer worker. Node only; no npm, no network."""
    root = workspace / MODEL_DIR
    root.mkdir(parents=True, exist_ok=True)
    return {"command": "node", "args": [str(SAFE_SERVER), "--root", str(root), "--allow-write"]}


def model_task_id(pid: str, mob_id: str) -> str:
    return f"{pid}:MODEL:{mob_id}"


MODEL_INSTRUCTIONS = """
## Your job on this task (designer)
Author the Blockbench/GeckoLib model for the mob named in the task using the `blockbench` MCP server (tools
prefixed `mcp__blockbench__bbmodel_*`). Its root is `models/` inside this workspace; only top-level files there.
Deliver, in `models/`: `<mob>.bbmodel` (format geckolib_model, identifier = the mob id, mod id = this mod),
`<mob>.geo.json`, `<mob>.animation.json` and `<mob>.png` (the texture, matching the model resolution).
Required: a readable rig (body/head/limbs as bones with sensible pivots), animations named exactly
`animation.<mob>.idle` and `animation.<mob>.walk` (loop), `bbmodel_geckolib_validate` with
`require_idle_walk: true` passing, `bbmodel_render` used at least once to look at the result (rest + a walk frame),
and both exports written with `overwrite: true` when re-exporting. Keep the texture simple but not noise:
flat colours per body part on the UV layout is enough for v1. Report the four file paths in `changed_files`
(relative to the workspace, e.g. `models/<mob>.geo.json`) and the validator result under `checks_run`.
Never touch `src/` or `assets/` yourself: the controller installs the exports over the placeholders.
"""


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"{path.name}: {exc}")


def validate_model_files(workspace: Path, mob_id: str) -> dict:
    """Check the designer's deliverables against the mob and GeckoLib's expectations."""
    root = workspace / MODEL_DIR
    files = {k: root / f"{mob_id}.{ext}" for k, ext in (("bbmodel", "bbmodel"), ("geo", "geo.json"), ("anim", "animation.json"), ("png", "png"))}
    missing = [f.name for f in files.values() if not f.is_file()]
    if missing:
        raise InputError(f"designer deliverables missing in models/: {', '.join(missing)}")
    geo = _load(files["geo"])
    try:
        g = geo["minecraft:geometry"][0]
        desc = g["description"]
        bones = {b["name"] for b in g["bones"]}
    except (KeyError, IndexError, TypeError):
        raise InputError("geo.json is not Bedrock 1.12.0 geometry with minecraft:geometry[0].bones")
    if desc.get("identifier") != f"geometry.{mob_id}":
        raise InputError(f"geo identifier must be geometry.{mob_id}, got {desc.get('identifier')!r}")
    if not bones:
        raise InputError("geo.json has no bones")
    anim = _load(files["anim"])
    clips = anim.get("animations") or {}
    for req in (f"animation.{mob_id}.idle", f"animation.{mob_id}.walk"):
        if req not in clips:
            raise InputError(f"animation.json lacks {req} (has: {', '.join(clips) or 'none'})")
    unknown = sorted({b for c in clips.values() for b in (c.get("bones") or {}) if b not in bones})
    if unknown:
        raise InputError(f"animation.json animates bones that are not in geo.json: {unknown}")
    png = files["png"].read_bytes()
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise InputError("texture is not a PNG")
    w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    tw, th = desc.get("texture_width"), desc.get("texture_height")
    if (tw, th) != (w, h):
        raise InputError(f"texture is {w}x{h} but geo declares {tw}x{th}")
    cubes = sum(len(b.get("cubes", [])) for b in g["bones"])
    return {"bones": sorted(bones), "cubes": cubes, "animations": sorted(clips), "texture": [w, h],
            "files": {k: str(v.relative_to(workspace)).replace("\\", "/") for k, v in files.items()}}


def install_model(store: Store, pid: str, mob_id: str, *, run_id: str, actor: str) -> dict:
    """Validate and copy the designer's exports over the placeholder assets, as a manifest revision."""
    proj = store.project(pid)
    ws = Path(proj["root"])
    info = validate_model_files(ws, mob_id)
    res = ws / "src" / "main" / "resources" / "assets" / pid
    targets = {
        "geo": res / "geo" / "entity" / f"{mob_id}.geo.json",
        "anim": res / "animations" / "entity" / f"{mob_id}.animation.json",
        "png": res / "textures" / "entity" / f"{mob_id}.png",
    }
    for key, dst in targets.items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ws / info["files"][key], dst)
    changed = [str(t.relative_to(ws)).replace("\\", "/") for t in targets.values()]
    # Keep this run's previews + texture so the UI can show versions after feedback rounds.
    history = ws / ".mod-orchestra" / "previews" / run_id
    history.mkdir(parents=True, exist_ok=True)
    for png in sorted((ws / MODEL_DIR).glob(f"{mob_id}_*.png")) + [ws / info["files"]["png"]]:
        shutil.copyfile(png, history / png.name)
    accepted = accept_changes(ws, run_id=run_id, actor=actor, changed=changed)
    store.add_event(pid, "controller", "MODEL_INSTALLED", {"mob": mob_id, "run": run_id, **{k: v for k, v in info.items() if k != "files"}})
    return info | {"installed": changed, "accepted": accepted["accepted"], "source": info["files"]["bbmodel"]}


# ---------------------------------------------------------------------------------------------
# Adding a mob AFTER generation (UI "Add a mob"). The controller writes the mob's own new files
# deterministically (nothing an agent could have edited), merges lang keys, and hands the only
# shared-file edits (ModMain/ModClient registrations, GeckoLib dependency if this is the first mob)
# to a coder task with the exact reference snippets. Then the designer task and a fresh BUILD.
# ---------------------------------------------------------------------------------------------
import json as _json
from dataclasses import replace as _replace
from .spec import Mob, read_spec, validate_spec_content
from .geckolib import (entity_java, renderer_java, client_init_java, main_registrations, placeholder_geo, placeholder_animation,
                       entity_loot, class_name, gradle_dependency_lines, GECKOLIB_VERSION)
from .fabric import placeholder_png


def add_mob_after_generation(store: Store, pid: str, mob: Mob) -> dict:
    proj = store.project(pid)
    if proj["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        raise StateError("Generate the project first; before generation use `craftctl add-mob`")
    spec = read_spec(proj["spec"])
    if any(m.identifier == mob.identifier for m in spec.mobs):
        raise InputError(f"Mob {mob.identifier!r} already exists")
    new_spec = _replace(spec, mobs=list(spec.mobs) + [mob])
    validate_spec_content(new_spec)
    first_mob = not spec.mobs
    ws = Path(proj["root"])
    java_dir = ws / "src/main/java" / spec.package.replace(".", "/")
    res = ws / "src/main/resources"
    assets = res / "assets" / pid
    written: list[str] = []

    def put(rel: Path, data: bytes):
        if rel.exists():
            raise InputError(f"Refusing to overwrite {rel.relative_to(ws)}")
        rel.parent.mkdir(parents=True, exist_ok=True); rel.write_bytes(data); written.append(str(rel.relative_to(ws)).replace("\\", "/"))

    put(java_dir / "entity" / f"{class_name(mob)}Entity.java", entity_java(new_spec, mob).encode())
    put(java_dir / "client" / f"{class_name(mob)}Renderer.java", renderer_java(new_spec, mob).encode())
    put(assets / "geo/entity" / f"{mob.identifier}.geo.json", (_json.dumps(placeholder_geo(mob), indent=2) + "\n").encode())
    put(assets / "animations/entity" / f"{mob.identifier}.animation.json", (_json.dumps(placeholder_animation(mob), indent=2) + "\n").encode())
    put(assets / "textures/entity" / f"{mob.identifier}.png", placeholder_png(pid + "/entity/" + mob.identifier, 64, 32))
    put(res / "data" / pid / "loot_table/entities" / f"{mob.identifier}.json", (_json.dumps(entity_loot(new_spec, mob), indent=2) + "\n").encode())
    put(assets / "models/item" / f"{mob.identifier}_spawn_egg.json", (_json.dumps({"parent": "minecraft:item/template_spawn_egg"}, indent=2) + "\n").encode())
    lang_file = assets / "lang/en_us.json"
    lang = _json.loads(lang_file.read_text(encoding="utf8")) if lang_file.is_file() else {}
    lang[f"entity.{pid}.{mob.identifier}"] = mob.label
    lang[f"item.{pid}.{mob.identifier}_spawn_egg"] = f"{mob.label} Spawn Egg"
    lang_file.write_text(_json.dumps(lang, indent=2, sort_keys=True) + "\n", encoding="utf8"); written.append(f"src/main/resources/assets/{pid}/lang/en_us.json")

    # spec update (status unchanged; approval stays: adding a mob is an additive, user-initiated change)
    with store.tx() as con:
        con.execute("UPDATE projects SET spec_json=? WHERE id=?", (_json.dumps(new_spec.to_dict(), sort_keys=True), pid))
        store.event(con, pid, "user", "SPEC_CHANGED", {"reason": f"add mob {mob.identifier} after generation"})
    accepted = accept_changes(ws, run_id=f"add-mob:{mob.identifier}", actor="user", changed=written)
    from .dispatch import _source_changed
    _source_changed(store, pid)

    # coder task with the exact registration snippets; MODEL after it; BUILD requeued after MODEL
    imports, fields, init = main_registrations(_replace(spec, mobs=[mob]))
    client_lines = [l for l in client_init_java(new_spec).splitlines() if "EntityRendererRegistry.register" in l and class_name(mob) in l]
    extra = [f"import {i};" for i in imports if class_name(mob) in i or "EntityType" in i or "MobCategory" in i or "SpawnEggItem" in i or "FabricDefaultAttributeRegistry" in i]
    instructions = ["Register the new mob in the shared files (do not touch anything else):",
                    f"1. {java_dir.relative_to(ws)}/ModMain.java — add imports:"] + ["   " + l for l in extra] + \
                   ["   add fields:"] + ["   " + l for l in fields] + ["   in onInitialize():"] + ["   " + l for l in init] + \
                   [f"   and, if the mod has a creative tab (TAB), add `output.accept({mob.identifier.upper()}_SPAWN_EGG);` to its displayItems.",
                    f"2. {java_dir.relative_to(ws)}/client/ModClient.java — add inside onInitializeClient():"] + ["   " + l.strip() for l in client_lines]
    if first_mob:
        repo_block, dep_line = gradle_dependency_lines()
        instructions += ["3. This is the mod's first mob: build.gradle needs the GeckoLib repository block and dependency, gradle.properties needs "
                         f"`geckolib_version={GECKOLIB_VERSION}`, fabric.mod.json needs the client entrypoint `{spec.package}.client.ModClient` "
                         "and `\"geckolib\": \">=4.7\"` under depends, and src/main/java/.../client/ModClient.java must be created (ClientModInitializer).",
                         "   repository block:", *("   " + l for l in repo_block.splitlines()), "   dependency line:", "   " + dep_line.strip()]
    instructions += ["4. Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
    task_add = f"{pid}:ADD_MOB:{mob.identifier}"
    task_model = model_task_id(pid, mob.identifier)
    store.add_task(pid, task_add, "coder", f"Register new mob {mob.label} in ModMain/ModClient" + (" + GeckoLib dependency" if first_mob else ""))
    store.add_task(pid, task_model, "designer", f"Blockbench/GeckoLib model + idle/walk + texture for mob: {mob.label}", after=[task_add])
    store.add_event(pid, "controller", "MOB_ADDED", {"mob": mob.identifier, "files": written, "tasks": [task_add, task_model], "first_mob": first_mob})
    with store.tx() as con:
        con.execute("INSERT OR IGNORE INTO task_instructions(task_id, text) VALUES(?,?)", (task_add, "\n".join(instructions)))
    return {"mob": mob.identifier, "files": written, "accepted": accepted["accepted"], "tasks": [task_add, task_model], "first_mob": first_mob,
            "next": {"action": "dispatch", "payload": {"task": task_add}}}
