---
name: investigator
description: Mod extension, port, bug, or unfamiliar codebase.
---

# Investigator

## Trigger
Mod extension, port, bug, or unfamiliar codebase.

## Procedure
Inspect metadata/entrypoints/registries/mixins/assets/Gradle/Git; attempt baseline build; identify minimal extension point and risks.

## Critical safeguards
- The Fabric MVP is pinned to Minecraft 1.21.1 (Mojang mappings, Loom 1.18.4). Static items/blocks are build- and game-verified (`examples/crystal_example/EVIDENCE.md`); anything beyond that is unverified until it passes the same gates.
- Do not silently download/run external tools; request approval and prefer official sources.
- Keep LLM summaries bounded; attach evidence references, not full raw logs.
- Preserve original user sources, original idea, editable Blockbench `.bbmodel`, and world saves.

## Output contract
REPO_MAP and baseline evidence, no speculative edits.
Include task ID, exact version profile, changed files, checks run, evidence, and next action.

## Authoritative starting points
- https://docs.fabricmc.net/
- https://github.com/FabricMC/fabric-example-mod
- https://github.com/bernie-g/geckolib
- https://www.blockbench.net/wiki/
- `docs/ARCHITECTURE.md`, `knowledge/fabric/profile-1.21.1.md`
