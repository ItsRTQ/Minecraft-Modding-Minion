---
id: fabric.profile.1.21.1.candidate
status: candidate-unverified
loader: fabric
minecraft: 1.21.1
java: 21
last_reviewed: 2026-10-19
---

# Fabric 1.21.1 — candidate build profile

## Artifact coordinates (individually located in upstream Maven)

- Fabric Loom `1.10.5`: https://maven.fabricmc.net/net/fabricmc/fabric-loom/1.10.5/
- Fabric Loader `0.16.14`: https://maven.fabricmc.net/net/fabricmc/fabric-loader/0.16.14/
- Yarn `1.21.1+build.3`: https://maven.fabricmc.net/net/fabricmc/yarn/1.21.1+build.3/
- Fabric API `0.116.16+1.21.1`: https://maven.fabricmc.net/net/fabricmc/fabric-api/fabric-api/
- Gradle `8.14.3` candidate (distribution URL is pinned in source project). JDK 21.

**Do not mark this profile validated until a full `gradle build`, Minecraft client launch and dedicated server test succeed.** Pin wrapper SHA and upstream example commit during the validation task.

## Authoritative patterns

Official Fabric docs: https://docs.fabricmc.net/1.21.1/develop/
Official example: https://github.com/FabricMC/fabric-example-mod
Fabric 1.21.1 porting: https://docs.fabricmc.net/1.21.1/develop/porting

## Caveat

The project currently generates static block/item source and basic model JSON; it does not install dependencies, create animations, register worldgen, or automatically invoke GameTest. Treat compile/runtime compatibility as an open issue until measured.
