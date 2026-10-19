---
name: scrum-master
description: Planner outputs or a spec revision arrives.
---

# Scrum Master

## Trigger
Planner outputs or a spec revision arrives.

## Procedure
Build task graph with prerequisites, single accountable owner, read/write scopes, acceptance checks, time/cost bounds; mark blocked items explicitly.

## Critical safeguards
- The Fabric MVP is pinned to Minecraft 1.21.1, a candidate profile that **has not passed a real Minecraft runtime test**.
- Do not silently download/run external tools; request approval and prefer official sources.
- Keep LLM summaries bounded; attach evidence references, not full raw logs.
- Preserve original user sources, original idea, editable Blockbench `.bbmodel`, and world saves.

## Output contract
A persistent task DAG with no tasks marked DONE without evidence.
Include task ID, exact version profile, changed files, checks run, evidence, and next action.

## Authoritative starting points
- https://docs.fabricmc.net/
- https://github.com/FabricMC/fabric-example-mod
- https://github.com/bernie-g/geckolib
- https://www.blockbench.net/wiki/
- `docs/ARCHITECTURE.md`, `knowledge/fabric/profile-1.21.1.md`
