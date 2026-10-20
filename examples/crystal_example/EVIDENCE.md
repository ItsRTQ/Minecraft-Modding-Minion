# Verification evidence — crystal_example

Recorded by the project owner (RTQ) on **2026-10-20**, Windows, JDK 25. Source built was `dev @ aa8538d`
(generator output identical to this directory except `loom_version`, then `1.18-SNAPSHOT`, which resolved to 1.18.4 and is now pinned).

| Level | Evidence |
|---|---|
| BUILD_PASS | `gradlew.bat build` → `BUILD SUCCESSFUL in 1m 4s`, `Fabric Loom: 1.18.4`. JAR `build/libs/crystal_example-1.0.0.jar` SHA-256 `6de89b8cebde3bac596c504489d07fad9c6c858eaffa97e99414f24cf4b857f1` (SHA-1 `8469487abcb98fa061fff77df19027a8238cb9dc`). Manifest: Loom 1.18.4, Gradle 9.7.1, Loader 0.19.5, namespace intermediary. JAR contents inspected: `ModMain.class` remapped (`class_1792`, `class_4970`), `data/crystal_example/loot_table/blocks/crystal_stone.json` present. |
| CLIENT_BOOT_PASS | `run/logs/latest.log`: `[FabricLoader] Loading 56 mods: - crystal_example 1.0.0`; `Reloading ResourceManager: vanilla, fabric, crystal_example, …`. Only warnings are vanilla (`goat_horn` sounds, `rendertype_entity_translucent_emissive` sampler). |
| SERVER_BOOT_PASS | `gradlew.bat runServer`: stopped on `eula.txt`, accepted, re-run. Server log: `Env=SERVER`, `Loading Minecraft 1.21.1 with Fabric Loader 0.19.5`, `Loading 44 mods: - crystal_example 1.0.0`, `Starting minecraft server version 1.21.1`, `Done (4.354s)! For help, type "help"`. No warnings or errors. |
| CONTENT_VERIFIED | Sky Crystal and Lunar Gem in the **Ingredients** creative tab; Crystal Stone in **Building Blocks**; block placeable; in survival the block breaks, drops itself and can be re-placed (validates the 1.21 `loot_table/` folder fix). |

Known harmless build warning: `duplicate input class net/fabricmc/fabric/mixin/tag/package-info` (Fabric API `convention-tags-v2` vs `tag-api-v1` packaging).

Not yet verified: multiplayer join, dedicated-server content behaviour, any mechanic beyond static item/block registration.
