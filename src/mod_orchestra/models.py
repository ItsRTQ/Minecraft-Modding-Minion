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
    accepted = accept_changes(ws, run_id=run_id, actor=actor, changed=changed)
    store.add_event(pid, "controller", "MODEL_INSTALLED", {"mob": mob_id, "run": run_id, **{k: v for k, v in info.items() if k != "files"}})
    return info | {"installed": changed, "accepted": accepted["accepted"], "source": info["files"]["bbmodel"]}
