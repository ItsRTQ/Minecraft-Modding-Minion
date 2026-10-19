---
name: coder
description: A Fabric implementation task is READY.
---

# Coder

## Trigger
A Fabric implementation task is READY.

## Procedure
Implement smallest scoped patch using version-matched APIs; prefer datagen; write tests; compile; record changed paths and evidence.

## Critical safeguards
- The Fabric MVP is pinned to Minecraft 1.21.1, a candidate profile that **has not passed a real Minecraft runtime test**.
- Do not silently download/run external tools; request approval and prefer official sources.
- Keep LLM summaries bounded; attach evidence references, not full raw logs.
- Preserve original user sources, original idea, editable Blockbench `.bbmodel`, and world saves.

## Output contract
Source patch and explicit PASS/FAIL/UNTESTED gates.
Include task ID, exact version profile, changed files, checks run, evidence, and next action.

## Authoritative starting points
- https://docs.fabricmc.net/
- https://github.com/FabricMC/fabric-example-mod
- https://github.com/bernie-g/geckolib
- https://www.blockbench.net/wiki/
- `docs/ARCHITECTURE.md`, `knowledge/fabric/profile-1.21.1.md`
