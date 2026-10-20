---
id: fabric.profile.1.21.1.candidate
status: candidate-template-verified
loader: fabric
minecraft: 1.21.1
mappings: mojang
java_compile: 21
java_runtime: 25
last_reviewed: 2026-10-19
---

# Fabric 1.21.1 — candidate build profile (Mojang mappings)

## Source of truth

The profile mirrors the official template: https://github.com/FabricMC/fabric-example-mod/tree/1.21.1 (commit `684b581`, 2026-09-26). Upstream moved from Yarn to **Mojang official mappings** and to Loom 1.18 with the `net.fabricmc.fabric-loom-remap` plugin id (used for obfuscated Minecraft versions before 26.1; newer versions use `net.fabricmc.fabric-loom`).

## Pinned coordinates

- Loom plugin `net.fabricmc.fabric-loom-remap` version `1.18-SNAPSHOT` (upstream pins the snapshot; pin a release once one is confirmed to resolve)
- Fabric Loader `0.19.5`
- Fabric API `0.116.17+1.21.1`
- Mappings: `loom.officialMojangMappings()` (no Yarn artifact)
- Gradle `9.7.1` via wrapper. **JDK 25 runs Gradle/Loom**; sources compile with `--release 21`.

## Evidence

- 2026-10-19: the unmodified upstream template compiled successfully (`gradlew build`) on Windows with JDK 25. This verifies the *toolchain*, not the generator output.
- Generator output (`examples/crystal_example`) has **not** yet been compiled. Do not promote the profile until it builds, launches a client and a dedicated server.

## Mojmap vs Yarn cheat sheet (1.21.1)

| Concept | Yarn (old generator) | Mojmap (current) |
|---|---|---|
| Identifier | `net.minecraft.util.Identifier` / `Identifier.of(ns, path)` | `net.minecraft.resources.ResourceLocation` / `ResourceLocation.fromNamespaceAndPath(ns, path)` |
| Registries | `net.minecraft.registry.Registries` | `net.minecraft.core.registries.BuiltInRegistries` |
| Register | `net.minecraft.registry.Registry.register` | `net.minecraft.core.Registry.register` |
| Block | `net.minecraft.block.Block` + `AbstractBlock.Settings.create()` | `net.minecraft.world.level.block.Block` + `BlockBehaviour.Properties.of()` |
| Item | `net.minecraft.item.Item` + `Item.Settings()` | `net.minecraft.world.item.Item` + `Item.Properties()` |
| Creative tabs | `ItemGroups.INGREDIENTS`, `entries.add(x)` | `CreativeModeTabs.INGREDIENTS`, `entries.accept(x)` |

`ItemGroupEvents` (Fabric API) keeps the same package under both mappings. In 1.21.2+ `Item.Properties`/`BlockBehaviour.Properties` require a registry key via `.setId(...)`; 1.21.1 does not.

## 1.21 datapack folder rename

Since 1.21 (pack format 48) datapack folders are singular: `loot_table/`, `recipe/`, `advancement/`, `predicate/`, `item_modifier/`, `function/`, `structure/`, `tags/block`, `tags/item`, etc. The generator previously wrote `loot_tables/` (silently ignored by the game: block dropped nothing). Resource pack `pack_format` for 1.21.1 is 34.

## Authoritative patterns

- Official Fabric docs: https://docs.fabricmc.net/1.21.1/develop/
- Loom plugin ids and mappings DSL: https://docs.fabricmc.net/develop/loom/
- Fabric 1.21.1 porting notes: https://docs.fabricmc.net/1.21.1/develop/porting

## Caveat

The generator still only emits static item/block source and basic model JSON; no datagen, recipes, worldgen, GeckoLib or GameTest. Treat compile/runtime compatibility of generated output as open until measured.
