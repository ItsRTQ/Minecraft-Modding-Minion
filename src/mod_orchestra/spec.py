"""Conservative deterministic intake; unsupported ideas remain questions, not fake output."""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
import re
from .validation import normalize_id, project_id, validate_package, InputError

@dataclass(frozen=True)
class Feature:
    kind: str
    identifier: str
    label: str

@dataclass(frozen=True)
class Recipe:
    """One vanilla recipe. Ingredients/results are local ids (a feature of this mod), namespaced ids
    (minecraft:stick) or tags (#minecraft:planks)."""
    id: str                       # recipe file name, e.g. ruby_block
    kind: str                     # shaped | shapeless | smelting | blasting | campfire_cooking | smoking
    result: str
    count: int = 1
    pattern: tuple[str, ...] = ()           # shaped: 1-3 rows of 1-3 chars; " " = empty
    key: dict = field(default_factory=dict)  # shaped: symbol -> ingredient
    ingredients: tuple[str, ...] = ()       # shapeless (1-9) / cooking (exactly 1)
    experience: float = 0.0                 # cooking
    cooking_time: int = 200                 # cooking, ticks
    group: str = ""


@dataclass(frozen=True)
class Drop:
    """Block loot beyond drop-self: ore -> item, with the vanilla ore conventions."""
    block: str
    item: str
    count_min: int = 1
    count_max: int = 1
    fortune: bool = False
    silk_touch: bool = False


@dataclass(frozen=True)
class Mob:
    """v1 criterion 6 'simple mob': GeckoLib-rendered entity with idle + walk, basic AI, spawn egg, loot."""
    identifier: str
    label: str
    behavior: str = "passive"          # passive | hostile
    health: float = 10.0
    speed: float = 0.25
    width: float = 0.8
    height: float = 0.9
    attack_damage: float = 3.0         # hostile only
    drops: tuple[str, ...] = ()        # local ids or minecraft:ids dropped on death (1 each)
    egg_colors: tuple[int, int] = (0x8A6DD1, 0xE6D8FF)


@dataclass(frozen=True)
class Spec:
    schema_version: int
    name: str
    mod_id: str
    package: str
    idea: str
    profile: str
    features: list[Feature]
    questions: list[str]
    assumptions: list[str]
    recipes: list[Recipe] = field(default_factory=list)
    drops: list[Drop] = field(default_factory=list)
    tab: str | None = None        # creative tab label; id is derived (<mod_id>_tab)
    tab_icon: str | None = None   # local item id shown as the tab icon
    mobs: list[Mob] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def local_ids(self) -> set[str]:
        return {f.identifier for f in self.features}


SCHEMA_VERSION = 2
RECIPE_KINDS = ("shaped", "shapeless", "smelting", "blasting", "smoking", "campfire_cooking")
INGREDIENT_RE = re.compile(r"^#?[a-z0-9_.-]+:[a-z0-9_./-]+$")


def resolve_ingredient(spec_ids: set[str], mod_id: str, value: str) -> dict:
    """Return the vanilla JSON ingredient object for a local id, a namespaced id or a tag."""
    v = value.strip()
    if v.startswith("#"):
        if not INGREDIENT_RE.match(v):
            raise InputError(f"Bad tag ingredient: {value!r} (expected #namespace:path)")
        return {"tag": v[1:]}
    if ":" in v:
        if not INGREDIENT_RE.match(v):
            raise InputError(f"Bad namespaced ingredient: {value!r}")
        return {"item": v}
    if v not in spec_ids:
        raise InputError(f"Unknown local ingredient {value!r}; it must be an item or block of this mod, or namespaced like minecraft:stick")
    return {"item": f"{mod_id}:{v}"}


def resolve_result(spec_ids: set[str], mod_id: str, value: str) -> str:
    v = value.strip()
    if ":" in v:
        if v.startswith("#") or not INGREDIENT_RE.match(v):
            raise InputError(f"Bad result id: {value!r}")
        return v
    if v not in spec_ids:
        raise InputError(f"Unknown result {value!r}; recipes can only produce items/blocks of this mod or namespaced ids")
    return f"{mod_id}:{v}"


def validate_recipe(spec_ids: set[str], mod_id: str, r: Recipe) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", r.id):
        raise InputError(f"Recipe id must be snake_case (2-50 chars): {r.id!r}")
    if r.kind not in RECIPE_KINDS:
        raise InputError(f"Recipe kind must be one of {RECIPE_KINDS}: {r.kind!r}")
    if not (1 <= r.count <= 64):
        raise InputError("Recipe result count must be 1-64")
    resolve_result(spec_ids, mod_id, r.result)
    if r.kind == "shaped":
        if not (1 <= len(r.pattern) <= 3) or any(not (1 <= len(row) <= 3) for row in r.pattern):
            raise InputError("Shaped pattern needs 1-3 rows of 1-3 characters")
        if len({len(row) for row in r.pattern}) != 1:
            raise InputError("Shaped pattern rows must all have the same width")
        used = {c for row in r.pattern for c in row if c != " "}
        if not used:
            raise InputError("Shaped pattern is empty")
        missing = used - set(r.key)
        if missing:
            raise InputError(f"Shaped pattern uses symbols without a key: {sorted(missing)}")
        for sym, ing in r.key.items():
            if len(sym) != 1 or sym == " ":
                raise InputError(f"Shaped key symbols must be single non-space characters: {sym!r}")
            resolve_ingredient(spec_ids, mod_id, ing)
    elif r.kind == "shapeless":
        if not (1 <= len(r.ingredients) <= 9):
            raise InputError("Shapeless recipes take 1-9 ingredients")
        for ing in r.ingredients:
            resolve_ingredient(spec_ids, mod_id, ing)
    else:
        if len(r.ingredients) != 1:
            raise InputError(f"{r.kind} recipes take exactly one ingredient")
        resolve_ingredient(spec_ids, mod_id, r.ingredients[0])
        if not (0 <= r.experience <= 100) or not (1 <= r.cooking_time <= 72000):
            raise InputError("Cooking experience must be 0-100 and cooking_time 1-72000 ticks")


def validate_drop(spec: "Spec", d: Drop) -> None:
    blocks = {f.identifier for f in spec.features if f.kind == "block"}
    if d.block not in blocks:
        raise InputError(f"Drop block {d.block!r} is not a block of this mod")
    resolve_result(spec.local_ids(), spec.mod_id, d.item)
    if not (0 <= d.count_min <= d.count_max <= 64):
        raise InputError("Drop counts must satisfy 0 <= min <= max <= 64")


MOB_BEHAVIORS = ("passive", "hostile")


def validate_mob(spec: "Spec", m: Mob) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", m.identifier):
        raise InputError(f"Mob identifier must be snake_case (2-50 chars): {m.identifier!r}")
    if m.identifier in spec.local_ids() or f"{m.identifier}_spawn_egg" in spec.local_ids():
        raise InputError(f"Mob identifier {m.identifier!r} collides with an item/block (its spawn egg is <id>_spawn_egg)")
    if m.behavior not in MOB_BEHAVIORS:
        raise InputError(f"Mob behavior must be one of {MOB_BEHAVIORS}")
    if not (1 <= m.health <= 1024) or not (0.05 <= m.speed <= 1.5) or not (0.1 <= m.width <= 4) or not (0.1 <= m.height <= 4):
        raise InputError("Mob health 1-1024, speed 0.05-1.5, width/height 0.1-4")
    if not (0 <= m.attack_damage <= 100):
        raise InputError("Mob attack_damage 0-100")
    for d in m.drops:
        resolve_result(spec.local_ids(), spec.mod_id, d)
    if len(m.egg_colors) != 2 or any(not (0 <= c <= 0xFFFFFF) for c in m.egg_colors):
        raise InputError("egg_colors must be two 24-bit RGB ints")


def validate_spec_content(spec: "Spec") -> None:
    ids = spec.local_ids()
    seen_mobs: set[str] = set()
    for m in spec.mobs:
        if m.identifier in seen_mobs:
            raise InputError(f"Duplicate mob: {m.identifier}")
        seen_mobs.add(m.identifier)
        validate_mob(spec, m)
    seen: set[str] = set()
    for r in spec.recipes:
        if r.id in seen:
            raise InputError(f"Duplicate recipe id: {r.id}")
        seen.add(r.id)
        validate_recipe(ids, spec.mod_id, r)
    seen_blocks: set[str] = set()
    for d in spec.drops:
        if d.block in seen_blocks:
            raise InputError(f"Only one drop rule per block: {d.block}")
        seen_blocks.add(d.block)
        validate_drop(spec, d)
    if spec.tab is not None and not (1 <= len(spec.tab.strip()) <= 40):
        raise InputError("Creative tab label must be 1-40 chars")
    if spec.tab_icon is not None and spec.tab_icon not in ids:
        raise InputError(f"Tab icon {spec.tab_icon!r} must be an item or block of this mod")

# Deterministic supported syntax; natural language is preserved, not silently hallucinated.
PATTERNS = [
    ("item", re.compile(r"\b(?:item|items)\s*:\s*([^;\n]+)", re.I)),
    ("block", re.compile(r"\b(?:block|blocks)\s*:\s*([^;\n]+)", re.I)),
]
TAB_PATTERN = re.compile(r"\btab\s*:\s*([^;\n]+)", re.I)
MOB_PATTERNS = [("hostile", re.compile(r"\bhostile\s+(?:mob|mobs)\s*:\s*([^;\n]+)", re.I)),
                ("passive", re.compile(r"(?<!hostile )\b(?:mob|mobs)\s*:\s*([^;\n]+)", re.I))]
# Java constant names the generator reserves inside ModMain; user content may not shadow them.
RESERVED_JAVA_NAMES = {"MOD_ID"}


def java_constant_names(feature: Feature) -> list[str]:
    """Constant names ModMain.java will declare for a feature (mirrors fabric.py)."""
    base = feature.identifier.upper()
    return [base, base + "_ITEM"] if feature.kind == "block" else [base]


def check_java_name_collisions(features: list[Feature]) -> None:
    owners: dict[str, str] = {name: "generator reserved" for name in RESERVED_JAVA_NAMES}
    for feature in features:
        for name in java_constant_names(feature):
            if name in owners:
                raise InputError(
                    f"{feature.kind} '{feature.identifier}' would declare Java constant {name}, "
                    f"which collides with {owners[name]}. Rename one of them.")
            owners[name] = f"{feature.kind} '{feature.identifier}'"


UNSUPPORTED = re.compile(r"\b(?:mob|entity|boss|biome|dimension|structure|worldgen|geckolib|animate|animation|portal|spell|GUI|HUD|multiplayer)\b", re.I)

def interpret(*, name: str, mod_id: str, package: str, idea: str, profile: str) -> Spec:
    from .config import SUPPORTED_PROFILE
    mid = project_id(mod_id)
    pkg = validate_package(package)
    if profile != SUPPORTED_PROFILE:
        raise InputError(f"Only {SUPPORTED_PROFILE!r} is implemented; other versions require a verified adapter")
    if not (1 <= len(name.strip()) <= 80 and 4 <= len(idea.strip()) <= 8000):
        raise InputError("Name (1–80 chars) and idea (4–8000 chars) are required")
    found: list[Feature] = []
    seen: set[str] = set()
    for kind, pattern in PATTERNS:
        for match in pattern.finditer(idea):
            for raw in match.group(1).split(","):
                label = raw.strip().strip(". ")
                if not label:
                    continue
                identifier = normalize_id(label, content=True)
                if identifier in seen:
                    raise InputError("Item and block identifiers must be unique: " + identifier)
                seen.add(identifier)
                found.append(Feature(kind=kind, identifier=identifier, label=label))
    check_java_name_collisions(found)
    questions = []
    if not found and not any(p.search(idea) for _, p in MOB_PATTERNS):
        questions.append("For the deterministic starter, specify content as 'items: copper coin, ruby; blocks: ruby ore'. Other ideas can be retained for a human/agent implementation plan.")
    if UNSUPPORTED.search(idea):
        questions.append("Advanced mechanics/entities/worldgen are not generated by the current deterministic backend. Should they be planned as manually implemented future work?")
    if len(found) > 24:
        raise InputError("Prototype supports at most 24 item/block entries per generation")
    tab = None
    m = TAB_PATTERN.search(idea)
    if m:
        tab = m.group(1).strip().strip(". ")[:40] or None
    mobs: list[Mob] = []
    for behavior, pattern in MOB_PATTERNS:
        for match in pattern.finditer(idea):
            for raw in match.group(1).split(","):
                label = raw.strip().strip(". ")
                if label:
                    mobs.append(Mob(identifier=normalize_id(label, content=True), label=label, behavior=behavior))
    if (mobs or found) and not questions:
        pass
    if mobs and not found:
        questions = [q for q in questions if "specify content" not in q]
    spec = Spec(SCHEMA_VERSION, name.strip(), mid, pkg, idea.strip(), profile, found, questions,
                ["Vanilla-inspired generated placeholder textures; visual assets require review", "New local Fabric project, not an edit to an existing mod"],
                tab=tab, tab_icon=(found[0].identifier if (tab and found) else None), mobs=mobs)
    validate_spec_content(spec)
    return spec

def read_spec(raw: dict) -> Spec:
    """Reads schema 1 (items/blocks only) and 2 (recipes, drops, tab). Older specs upgrade in memory."""
    if raw.get("schema_version") not in (1, 2):
        raise InputError("Unsupported spec revision")
    spec = Spec(
        schema_version=SCHEMA_VERSION, name=str(raw["name"]), mod_id=normalize_id(raw["mod_id"]),
        package=validate_package(raw["package"]), idea=str(raw["idea"]),
        profile=str(raw["profile"]),
        features=[Feature(**f) for f in raw.get("features", [])],
        questions=list(raw.get("questions", [])), assumptions=list(raw.get("assumptions", [])),
        recipes=[Recipe(**{**r, "pattern": tuple(r.get("pattern", ())), "ingredients": tuple(r.get("ingredients", ()))}) for r in raw.get("recipes", [])],
        drops=[Drop(**d) for d in raw.get("drops", [])],
        tab=raw.get("tab"), tab_icon=raw.get("tab_icon"),
        mobs=[Mob(**{**m, "drops": tuple(m.get("drops", ())), "egg_colors": tuple(m.get("egg_colors", (0x8A6DD1, 0xE6D8FF)))}) for m in raw.get("mobs", [])],
    )
    validate_spec_content(spec)
    return spec
