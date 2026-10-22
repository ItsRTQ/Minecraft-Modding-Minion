---
id: blockbench.mcp.audit
status: audited
last_reviewed: 2026-10-22
---

# Blockbench MCP audit (R6 prerequisite, v1 criterion 6)

`docs/DEVELOPMENT_PATH.md` R6: do not build a 3D editor; audit the existing MCPs first. Three candidates
were cloned on 2026-10-22 and inspected; one was exercised end to end in the sandbox.

| | adhi-jp/minecraft-blockbench-mcp | jasonjgardner/blockbench-mcp-plugin | sosadly/blockbench-mcp |
|---|---|---|---|
| Version / last commit | 0.3.1 · 2026-10-18 | 1.10.1 · 2026-10-16 (225 commits) | 0.3.1 · 2026-09-21 (10 commits) |
| License | MIT | **GPL-3.0** | MIT |
| Architecture | stdio adapter ⇄ loopback WebSocket ⇄ Blockbench desktop plugin; every op runs inside Blockbench with undo | **Headless stdio server** that edits `.bbmodel` on disk (no Blockbench needed) **plus** a desktop plugin (HTTP) | stdio server ⇄ live Blockbench desktop plugin |
| Needs Blockbench open | yes (+ GeckoLib plugin) | **no** (headless) / yes (plugin) | yes |
| GeckoLib | `create_geckolib_project`, `open_geckolib_model` (format via GeckoLib plugin) | `geckolib_model` format; GeckoLib rules in `bbmodel_validate` | GeckoLib models, rigs, animations |
| Mob workflow helpers | low-level (groups/cubes/keyframes) | low-level + validation gates (`validate`, `validate_animations`, `sample_pose`), render/contact sheet | **high-level**: `create_rig` (quadruped/humanoid), `generate_animation` (idle/walk/run/attack…), `analyze_animation`, texture painting, review/screenshots, playbooks |
| Export | via Blockbench exporters (GeckoLib plugin) | `bbmodel_export_bedrock_geometry` (= GeckoLib `.geo.json`), Java block, modded entity; **no `.animation.json` export** | via Blockbench exporters |
| Install | npm package + plugin from URL | `npx -y github:jasonjgardner/blockbench-mcp-plugin --root <dir>` (installs its own Bun; Node only) | git clone + plugin |
| Parallel agents / CI | no (one editor) | **yes** (one process per agent; ran in our sandbox) | no |
| Risk | young (0.3.x) | GPL-3.0; renderer needs a GPU | young, 10 commits, single author |

## What was actually verified (sandbox, 2026-10-22)

jasonjgardner headless 1.10.1 via `npx` (installed Bun itself), driven over MCP stdio by a hand-written client:
`bbmodel_create` (format `geckolib_model`, 64×32) → `bbmodel_edit` with 6 groups + 6 cubes + 2 animations
(`animation.critter.walk` with 4 leg animators, `animation.critter.idle`) → `bbmodel_validate` **passed**
(0 errors, 1 warning) → `bbmodel_validate_animations` **passed** → `bbmodel_export_bedrock_geometry` wrote
`critter.geo.json` (`format_version 1.12.0`, `geometry.critter`, 6 bones). `bbmodel_render` failed only because
the sandbox has no GPU (`Dawn did not return a GPU adapter`). Tool count: 23. Schemas are strict and
self-describing (invalid argument names are rejected with the required fields).

Not verified: the two live editors (need Blockbench on the owner's machine).

## Recommendation

1. **Adopt the jasonjgardner headless server as the agent-facing Blockbench tool for v1.** It is the only
   candidate that fits the controller's model: a bounded worker starts its own process, works on files in the
   workspace, can run in CI, and ships validation gates the controller can treat as evidence. The `.bbmodel`
   it writes is Blockbench's native file, so the owner can open, inspect and edit it in Blockbench at any time
   and the agent can continue from the edited file — "judge by looking" stays possible without the agent
   needing the editor.
2. **License handling:** GPL-3.0 does not touch our MIT code as long as it stays a separate process the user
   installs (`npx … github:`); we never vendor or import it. Record the pinned commit in the knowledge base
   and the MCP config; document that the user installs it.
3. **Fill the one gap ourselves:** GeckoLib also needs `<name>.animation.json`. The animation data is in the
   `.bbmodel` (`animations[].animators`), and the Bedrock animation format it maps to is small. The generator
   will convert `.bbmodel` → `geo.json` + `animation.json` deterministically (and we keep `.bbmodel` as the
   editable source, per the designer skill).
4. **Keep sosadly as the optional "designer in the loop" path** for the owner when iterating visually with the
   editor open; its `create_rig` / `generate_animation` are the best mob helpers, but it is young and live-only.
   adhi-jp is the MIT live alternative if GPL ever becomes a problem. Re-audit both in R6 proper with a
   local benchmark (same mob task on each; measure tool calls, turns, cost, in-game result).

## Pinned
- jasonjgardner/blockbench-mcp-plugin: tag v1.10.1 (verify the commit before pinning in `.mcp.json`).
