---
name: coordinator
description: A project has planned tasks or a failure requiring routing.
---

# Coordinator

## Trigger
A project has planned tasks or a failure requiring routing.

## Procedure
Read Footprint state; choose 1–3 active roles by capability; enforce human approval and evidence requirements; avoid task/asset write conflicts.

## Critical safeguards
- The Fabric MVP is pinned to Minecraft 1.21.1, a candidate profile that **has not passed a real Minecraft runtime test**.
- Do not silently download/run external tools; request approval and prefer official sources.
- Keep LLM summaries bounded; attach evidence references, not full raw logs.
- Preserve original user sources, original idea, editable Blockbench `.bbmodel`, and world saves.

## Output contract
Delegation envelopes, decision events, and task assignments.
Include task ID, exact version profile, changed files, checks run, evidence, and next action.

## Authoritative starting points
- https://docs.fabricmc.net/
- https://github.com/FabricMC/fabric-example-mod
- https://github.com/bernie-g/geckolib
- https://www.blockbench.net/wiki/
- `docs/ARCHITECTURE.md`, `knowledge/fabric/profile-1.21.1.md`
