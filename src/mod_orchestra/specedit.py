"""USER-ONLY spec editing before generation: recipes, drops, creative tab.

These exist so v1 criterion 2 can be exercised today; in R3 the interpreter agent fills the
same spec fields from the user's words. Every edit returns the spec to DRAFT.
"""
from __future__ import annotations
from dataclasses import replace
from .spec import Drop, Recipe, read_spec, validate_spec_content
from .state import Store


def _load(store: Store, pid: str):
    return read_spec(store.project(pid)["spec"])


def _save(store: Store, pid: str, spec, reason: str) -> dict:
    validate_spec_content(spec)
    store.replace_spec(pid, spec.to_dict(), actor="user", reason=reason)
    return {"project": pid, "spec_state": "DRAFT", "recipes": [r.id for r in spec.recipes], "drops": [d.block for d in spec.drops], "tab": spec.tab}


def add_recipe(store: Store, pid: str, *, recipe_id: str, kind: str, result: str, count: int = 1,
               pattern: list[str] | None = None, key: dict | None = None, ingredients: list[str] | None = None,
               experience: float = 0.0, cooking_time: int = 200, group: str = "") -> dict:
    spec = _load(store, pid)
    recipe = Recipe(id=recipe_id, kind=kind, result=result, count=count, pattern=tuple(pattern or ()),
                    key=dict(key or {}), ingredients=tuple(ingredients or ()), experience=experience,
                    cooking_time=cooking_time, group=group)
    recipes = [r for r in spec.recipes if r.id != recipe_id] + [recipe]
    return _save(store, pid, replace(spec, recipes=recipes), f"add recipe {recipe_id}")


def remove_recipe(store: Store, pid: str, recipe_id: str) -> dict:
    spec = _load(store, pid)
    return _save(store, pid, replace(spec, recipes=[r for r in spec.recipes if r.id != recipe_id]), f"remove recipe {recipe_id}")


def add_drop(store: Store, pid: str, *, block: str, item: str, count_min: int = 1, count_max: int = 1,
             fortune: bool = False, silk_touch: bool = False) -> dict:
    spec = _load(store, pid)
    drop = Drop(block=block, item=item, count_min=count_min, count_max=count_max, fortune=fortune, silk_touch=silk_touch)
    drops = [d for d in spec.drops if d.block != block] + [drop]
    return _save(store, pid, replace(spec, drops=drops), f"drop {block} -> {item}")


def set_tab(store: Store, pid: str, *, label: str | None, icon: str | None) -> dict:
    spec = _load(store, pid)
    return _save(store, pid, replace(spec, tab=label, tab_icon=(icon if label else None)), f"tab {label!r}")
