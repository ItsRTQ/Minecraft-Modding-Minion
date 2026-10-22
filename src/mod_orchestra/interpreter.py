"""R3: conversational interpreter (v1 criterion 1).

The interpreter role turns free text into a validated schema-2 spec. It runs as an ordinary
bounded worker on the <project>:SPEC task; its handoff carries a `spec` proposal and up to
three `questions`. The controller validates the proposal with the same rules as
`craftctl add-recipe/add-drop/set-tab`, stores it as the DRAFT spec, and waits for the user:
answers are appended to the idea (`craftctl answer`), approval is `craftctl approve-spec`.
The worker never writes the database and never widens scope on its own.
"""
from __future__ import annotations
import json
from .spec import Spec, read_spec, SCHEMA_VERSION, RECIPE_KINDS
from .state import Store, StateError
from .validation import InputError

MAX_QUESTIONS = 3

SPEC_INSTRUCTIONS = f"""
## Your job on this task (interpreter)
Turn the user's idea into a complete, concrete spec for a Fabric 1.21.1 mod using ONLY what the generator
supports: items, blocks, a creative tab, crafting/smelting recipes, and block drops. Preserve the user's
intent and wording; do not add content they did not ask for; do not drop content they did ask for.
If the idea mentions things the generator cannot build (mobs, biomes, dimensions, animations, armor stats,
tools with custom durability, GUIs, commands), keep the user's wish in `unknowns` and ask about it only
if it blocks the rest; never fake it as an item.

Ask at most {MAX_QUESTIONS} questions, and only when the answer changes files: ambiguous counts, missing
ingredients for a recipe the user implied, or which block an ore should drop from. Prefer sensible vanilla
defaults (ore → 1 gem, Fortune, Silk Touch; 9 gems ↔ 1 block; smelting 0.7 xp / 200 ticks) and state them
in `assumptions` instead of asking. Write everything in English identifiers (snake_case) even if the user
wrote in Spanish; keep labels in the user's language.

Put the proposal in the handoff under `spec` with EXACTLY this shape (schema_version {SCHEMA_VERSION}):
```json
{{"features": [{{"kind": "item|block", "identifier": "snake_case", "label": "Display Name"}}],
  "tab": "Tab Label or null", "tab_icon": "identifier of one feature or null",
  "recipes": [{{"id": "snake_case", "kind": "{'|'.join(RECIPE_KINDS)}", "result": "identifier or minecraft:id",
               "count": 1, "pattern": ["RRR"," S "," S "], "key": {{"R": "identifier", "S": "minecraft:stick"}},
               "ingredients": ["identifier", "minecraft:id", "#minecraft:tag"], "experience": 0.7, "cooking_time": 200}}],
  "drops": [{{"block": "identifier", "item": "identifier or minecraft:id", "count_min": 1, "count_max": 1, "fortune": true, "silk_touch": true}}],
  "assumptions": ["..."]}}
```
Rules the controller enforces (a violation fails your handoff): identifiers unique and snake_case (2-50 chars);
recipe ingredients/results must be features of this mod, `minecraft:` ids or `#minecraft:` tags; shaped patterns
1-3 rows of equal width (1-3 chars, space = empty) and every symbol in `key`; cooking recipes have exactly one
ingredient; one drop rule per block, and the block must be one of the features; the tab icon must be a feature.
Also put the questions (if any) under `questions`, as a list of plain sentences addressed to the user.
Use status WAITING_USER (the user must answer or approve); never DONE. Do not create or edit any files.
"""


def spec_from_proposal(current: dict, proposal: dict) -> Spec:
    """Merge a worker's proposal onto the project's identity fields and validate it as a real spec."""
    if not isinstance(proposal, dict):
        raise InputError("spec proposal must be an object")
    raw = {
        "schema_version": SCHEMA_VERSION, "name": current["name"], "mod_id": current["mod_id"], "package": current["package"],
        "idea": current["idea"], "profile": current["profile"],
        "features": proposal.get("features", []), "recipes": proposal.get("recipes", []), "drops": proposal.get("drops", []),
        "tab": proposal.get("tab"), "tab_icon": proposal.get("tab_icon"),
        "questions": [], "assumptions": [str(a) for a in proposal.get("assumptions", [])][:12],
    }
    spec = read_spec(raw)
    if not spec.features:
        raise InputError("spec proposal has no items or blocks")
    from .spec import check_java_name_collisions
    check_java_name_collisions(spec.features)
    return spec


def apply_interpretation(store: Store, pid: str, handoff: dict, run_id: str) -> dict:
    """Validate and store the interpreter's proposal; return what the user must do next."""
    questions = [str(q).strip() for q in (handoff.get("questions") or []) if str(q).strip()]
    if len(questions) > MAX_QUESTIONS:
        raise InputError(f"interpreter asked {len(questions)} questions; the limit is {MAX_QUESTIONS}")
    proposal = handoff.get("spec")
    if proposal is None:
        raise InputError("interpreter handoff has no `spec` proposal")
    current = store.project(pid)["spec"]
    spec = spec_from_proposal(current, proposal)
    stored = spec.to_dict() | {"questions": questions}
    store.replace_spec(pid, stored, actor=f"run:{run_id}", reason="interpreter proposal")
    summary = {"features": [f"{f.kind}:{f.identifier}" for f in spec.features], "recipes": [r.id for r in spec.recipes],
               "drops": [f"{d.block}->{d.item}" for d in spec.drops], "tab": spec.tab, "questions": questions,
               "assumptions": spec.assumptions}
    store.add_event(pid, "controller", "SPEC_PROPOSED", {"run": run_id, **summary})
    next_steps = ([f'craftctl answer {pid} "<your answer to: {q}>"' for q in questions] or []) + [f"craftctl approve-spec {pid}"]
    return summary | {"needs_user": next_steps}


def answer(store: Store, pid: str, text: str) -> dict:
    """USER-ONLY: append an answer to the idea and reopen the SPEC task for another interpreter pass."""
    text = text.strip()
    if not text:
        raise InputError("Answer is empty")
    proj = store.project(pid)
    if proj["status"] not in ("IDEA", "PLAN_READY"):
        raise StateError("The idea cannot change once source is generated")
    spec = dict(proj["spec"])
    questions = spec.get("questions") or []
    spec["idea"] = spec["idea"].rstrip() + "\n\n[user answer] " + text
    spec["questions"] = []
    store.replace_spec(pid, spec, actor="user", reason="answer")
    store.add_event(pid, "user", "ANSWER", {"text": text[:300], "answered": questions[:3]})
    task_id = f"{pid}:SPEC"
    state = next((t["state"] for t in store.tasks(pid) if t["id"] == task_id), None)
    if state in ("WAITING_USER", "FAILED", "BLOCKED", "DONE"):
        if state == "DONE":
            with store.tx() as con:
                con.execute("UPDATE tasks SET state='READY',version=version+1,lease_owner=NULL,lease_expiry=NULL WHERE id=?", (task_id,))
        else:
            store.requeue(task_id, "answer given")
    return {"project": pid, "idea_appended": True, "spec_task": task_id, "next": f"craftctl dispatch {pid} --task {task_id}"}
