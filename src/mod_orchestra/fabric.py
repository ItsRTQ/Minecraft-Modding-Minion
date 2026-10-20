"""Small deterministic Fabric 1.21.1 prototype generator (Mojang mappings, Loom 1.18).

No generated executable is run and no downloaded script is evaluated.
The output is SOURCE ONLY until a separate verified Gradle build occurs.
"""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import struct
import zlib
from pathlib import Path
from .state import StateError
from .config import PROFILE, WRAPPER_DIR, WRAPPER_FILES, GENERATOR_VERSION
from .spec import Spec
from .validation import InputError, safe_inside, ensure_new_directory


def placeholder_png(name: str, size: int = 16) -> bytes:
    """Deterministic pixel art placeholder PNG using only Python stdlib."""
    digest = hashlib.sha256(name.encode()).digest()
    main = (40 + digest[0] % 170, 40 + digest[1] % 170, 40 + digest[2] % 170)
    outline = tuple(max(0, c - 50) for c in main)
    shine = tuple(min(255, c + 50) for c in main)
    rows = []
    for y in range(size):
        pixels = []
        for x in range(size):
            edge = x in (0, size - 1) or y in (0, size - 1)
            alternate = ((x // 4) + (y // 4)) % 2 == 0
            color = outline if edge else shine if alternate else main
            pixels.extend([*color, 255])
        rows.append(b"\x00" + bytes(pixels))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")


def generate(spec: Spec, directory: Path) -> dict:
    """Write an entirely new workspace with a generated/UNVERIFIED status.

    All-or-nothing: if any step fails after the directory was created, the partial
    workspace is removed so a retry does not hit "No overwrite permitted".
    """
    directory = Path(directory).expanduser()
    created = not directory.exists()
    try:
        return _generate_into(spec, directory)
    except Exception:
        if created and directory.is_dir():
            shutil.rmtree(directory, ignore_errors=True)
        raise


def _generate_into(spec: Spec, directory: Path) -> dict:
    if spec.questions:
        raise InputError("Cannot generate until blocking questions are resolved: " + "; ".join(spec.questions))
    if not spec.features:
        raise InputError("At least one deterministic item/block feature required")
    if spec.profile != PROFILE["id"]:
        raise InputError("Unsupported target profile")
    directory = Path(directory).expanduser()
    ensure_new_directory(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    def put(relative: str, content: str | bytes) -> None:
        target = safe_inside(directory, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise InputError("No overwrite permitted: " + relative)
        raw = content.encode("utf-8") if isinstance(content, str) else content
        with target.open("xb") as f:
            f.write(raw)
        written[relative] = hashlib.sha256(raw).hexdigest()

    p = PROFILE
    put("settings.gradle", f"""pluginManagement {{
    repositories {{
        maven {{
            name = 'Fabric'
            url = 'https://maven.fabricmc.net/'
        }}
        mavenCentral()
        gradlePluginPortal()
    }}
}}

rootProject.name = '{spec.mod_id}'
""")
    put("gradle.properties", f"""org.gradle.jvmargs=-Xmx2G
org.gradle.parallel=true
org.gradle.configuration-cache=true

# Fabric Properties (profile {p['id']}; see https://fabricmc.net/develop)
minecraft_version={p['minecraft']}
loader_version={p['fabric_loader']}
loom_version={p['loom']}

# Mod Properties
version=1.0.0
group={spec.package}
archives_base_name={spec.mod_id}

# Dependencies
fabric_api_version={p['fabric_api']}
""")
    put("build.gradle", f"""plugins {{
    id '{p['loom_plugin']}' version "${{loom_version}}"
}}

base {{ archivesName = project.archives_base_name }}

loom {{
    mods {{
        "{spec.mod_id}" {{
            sourceSet sourceSets.main
        }}
    }}
}}

dependencies {{
    // To change the versions see the gradle.properties file
    minecraft "com.mojang:minecraft:${{project.minecraft_version}}"
    mappings loom.officialMojangMappings()
    modImplementation "net.fabricmc:fabric-loader:${{project.loader_version}}"
    modImplementation "net.fabricmc.fabric-api:fabric-api:${{project.fabric_api_version}}"
}}

processResources {{
    def version = project.version
    inputs.property "version", version
    filesMatching("fabric.mod.json") {{
        expand "version": version
    }}
}}

tasks.withType(JavaCompile).configureEach {{
    it.options.release = {p['java_major']}
    it.options.encoding = 'UTF-8'
}}

java {{
    sourceCompatibility = JavaVersion.VERSION_{p['java_major']}
    targetCompatibility = JavaVersion.VERSION_{p['java_major']}
}}
""")
    # Official Gradle wrapper (Apache-2.0), hash-verified against resources/gradle-wrapper/PROVENANCE.md.
    for relative, expected in WRAPPER_FILES.items():
        put(relative, verified_wrapper_file(relative, expected))
    if os.name != "nt":
        gradlew = directory / "gradlew"
        gradlew.chmod(gradlew.stat().st_mode | 0o111)
    put("gradle/wrapper/gradle-wrapper.properties", f"""distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-{p['gradle']}-bin.zip
distributionSha256Sum={p['gradle_dist_sha256']}
networkTimeout=10000
retries=0
retryBackOffMs=500
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""")
    put(".gitignore", ".gradle/\nbuild/\nrun/\n.idea/\n*.class\n")
    put("README.md", f"""# {spec.name}

Generated by Minecraft Mod Orchestra. **SOURCE GENERATED — NOT BUILD VERIFIED.**

Minecraft {p['minecraft']} / Fabric Loader {p['fabric_loader']} / Loom {p['loom']} / Mojang mappings / compile target Java {p['java_major']}.

### Build

1. Review generated source and dependencies.
2. Install JDK {p['gradle_jdk_major']} (required to run Gradle {p['gradle']} + Loom). Sources compile with `--release {p['java_major']}`, so no separate JDK {p['java_major']} is needed.
3. Run `./gradlew build` on Linux/macOS or `gradlew.bat build` on Windows. The wrapper is the official Gradle {p['gradle']} wrapper (hash-verified, Apache-2.0) and checks the distribution download against `distributionSha256Sum`.
4. Review `build/libs/`. Do not call the mod tested until the game loads and the content is exercised.

No existing Minecraft launcher installation is needed to compile, but network access is needed on initial Gradle resolution.

Your idea: {spec.idea}
""")
    put("fabric-profile.lock.json", json.dumps(p, indent=2) + "\n")
    java_dir = "src/main/java/" + spec.package.replace(".", "/")
    # Mojang official mappings (1.21.1). Yarn names differ; keep this table in one place.
    lines = [
        f"package {spec.package};", "",
        "import net.fabricmc.api.ModInitializer;",
        "import net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents;",
        "import net.minecraft.core.Registry;",
        "import net.minecraft.core.registries.BuiltInRegistries;",
        "import net.minecraft.resources.ResourceLocation;",
        "import net.minecraft.world.item.BlockItem;",
        "import net.minecraft.world.item.CreativeModeTabs;",
        "import net.minecraft.world.item.Item;",
        "import net.minecraft.world.level.block.Block;",
        "import net.minecraft.world.level.block.state.BlockBehaviour;",
        "",
        "public class ModMain implements ModInitializer {",
        f'    public static final String MOD_ID = "{spec.mod_id}";',
        "",
        "    private static ResourceLocation id(String path) {",
        "        return ResourceLocation.fromNamespaceAndPath(MOD_ID, path);",
        "    }",
        "",
    ]
    for feature in spec.features:
        varname = feature.identifier.upper()
        if feature.kind == "item":
            lines.append(f'    public static final Item {varname} = Registry.register(BuiltInRegistries.ITEM, id("{feature.identifier}"), new Item(new Item.Properties()));')
        else:
            lines.append(f'    public static final Block {varname} = Registry.register(BuiltInRegistries.BLOCK, id("{feature.identifier}"), new Block(BlockBehaviour.Properties.of().strength(3.0F)));')
            lines.append(f'    public static final Item {varname}_ITEM = Registry.register(BuiltInRegistries.ITEM, id("{feature.identifier}"), new BlockItem({varname}, new Item.Properties()));')
    lines += ["", "    @Override", "    public void onInitialize() {"]
    for feature in spec.features:
        group = "BUILDING_BLOCKS" if feature.kind == "block" else "INGREDIENTS"
        suffix = "_ITEM" if feature.kind == "block" else ""
        lines.append(f"        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.{group}).register(entries -> entries.accept({feature.identifier.upper()}{suffix}));")
    lines += ["    }", "}"]
    put(f"{java_dir}/ModMain.java", "\n".join(lines) + "\n")
    put("src/main/resources/fabric.mod.json", json.dumps({
        "schemaVersion": 1, "id": spec.mod_id, "version": "${version}", "name": spec.name,
        "description": "Generated Fabric starter from a user idea", "environment": "*",
        "entrypoints": {"main": [spec.package + ".ModMain"]},
        "depends": {"fabricloader": ">=" + p["fabric_loader"], "minecraft": "~1.21.1", "java": ">=21", "fabric-api": "*"},
        "license": "ARR",
    }, indent=2) + "\n")
    res = f"src/main/resources/assets/{spec.mod_id}"
    put("src/main/resources/pack.mcmeta", json.dumps({"pack": {"pack_format": 34, "description": spec.name + " assets"}}, indent=2) + "\n")
    lang = {}
    for feature in spec.features:
        key = feature.identifier
        lang[f"{'block' if feature.kind == 'block' else 'item'}.{spec.mod_id}.{key}"] = feature.label
        if feature.kind == "item":
            put(f"{res}/models/item/{key}.json", json.dumps({"parent": "item/generated", "textures": {"layer0": f"{spec.mod_id}:item/{key}"}}, indent=2) + "\n")
            put(f"{res}/textures/item/{key}.png", placeholder_png(spec.mod_id + "/" + key))
        else:
            put(f"{res}/blockstates/{key}.json", json.dumps({"variants": {"": {"model": f"{spec.mod_id}:block/{key}"}}}, indent=2) + "\n")
            put(f"{res}/models/block/{key}.json", json.dumps({"parent": "block/cube_all", "textures": {"all": f"{spec.mod_id}:block/{key}"}}, indent=2) + "\n")
            put(f"{res}/models/item/{key}.json", json.dumps({"parent": f"{spec.mod_id}:block/{key}"}, indent=2) + "\n")
            put(f"{res}/textures/block/{key}.png", placeholder_png(spec.mod_id + "/" + key))
            put(f"src/main/resources/data/{spec.mod_id}/loot_table/blocks/{key}.json", json.dumps({"type": "minecraft:block", "pools": [{"rolls": 1, "entries": [{"type": "minecraft:item", "name": f"{spec.mod_id}:{key}"}], "conditions": [{"condition": "minecraft:survives_explosion"}]}]}, indent=2) + "\n")
    put(f"{res}/lang/en_us.json", json.dumps(lang, indent=2, sort_keys=True) + "\n")
    manifest = {"generator": "mod-orchestra 0.1.0", "generator_version": GENERATOR_VERSION, "status": "GENERATED_UNVERIFIED", "profile": p["id"], "files": written.copy(), "build_verified": False, "runtime_verified": False}
    put(".mod-orchestra/generation-manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"path": str(directory), "files": len(written), "status": "GENERATED_UNVERIFIED", "manifest": str(directory / ".mod-orchestra/generation-manifest.json")}


def verified_wrapper_file(relative: str, expected_sha256: str) -> bytes:
    """Read an embedded wrapper file and refuse it if its bytes drifted from PROVENANCE.md."""
    source = WRAPPER_DIR / relative
    if not source.is_file():
        raise StateError(f"Embedded Gradle wrapper file missing from install: {relative}")
    data = source.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise StateError(f"Embedded Gradle wrapper {relative} hash {actual[:12]} != recorded {expected_sha256[:12]}; refusing to ship it")
    return data


def workspace_generation_info(path: Path) -> dict:
    """Which generator wrote this workspace and whether it ships the wrapper (H3)."""
    manifest_file = path / ".mod-orchestra/generation-manifest.json"
    if not manifest_file.is_file():
        return {"generator_version": None, "has_wrapper": False, "current": GENERATOR_VERSION}
    files = json.loads(manifest_file.read_text(encoding="utf8")).get("files", {})
    version = json.loads(manifest_file.read_text(encoding="utf8")).get("generator_version", 1)
    return {"generator_version": version, "has_wrapper": all(k in files for k in WRAPPER_FILES),
            "current": GENERATOR_VERSION, "outdated": version < GENERATOR_VERSION}


def validate_generated(path: Path) -> dict:
    manifest_file = path / ".mod-orchestra/generation-manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf8"))
    problems = []
    for relative, expected in manifest["files"].items():
        file_path = safe_inside(path, relative)
        if not file_path.is_file():
            problems.append("MISSING: " + relative)
        elif hashlib.sha256(file_path.read_bytes()).hexdigest() != expected:
            problems.append("CHANGED: " + relative)
        if relative.endswith(".json") and file_path.is_file():
            try:
                json.loads(file_path.read_text(encoding="utf8"))
            except (ValueError, UnicodeDecodeError) as exc:
                problems.append("BAD JSON: " + relative + ": " + str(exc))
    return {"status": "PASS" if not problems else "FAIL", "checked": len(manifest["files"]), "problems": problems, "note": "Static generation-only check; not a Minecraft build or runtime test"}
