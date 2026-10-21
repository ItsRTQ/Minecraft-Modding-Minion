# v1 — definition of done

Agreed 2026-10-21. This is the contract that ends the develop-improve-develop loop: when every criterion
below passes, the same day we tag `v1.0.0`. Nothing is added to v1 after this file is merged; new ideas go
to `docs/V2_BACKLOG.md`.

## The sentence

> A user with no modding experience writes a mod idea in plain language (English or Spanish), answers at
> most three questions, approves a readable spec, and receives a Fabric 1.21.1 mod that compiles, loads on
> client and dedicated server, and whose content — items, blocks, recipes, loot, and at least one
> Blockbench-modelled, GeckoLib-animated mob — behaves as described. Agents do the work; the user only
> approves and verifies.

## Acceptance criteria (each is pass/fail)

| # | Criterion | Proof | Roadmap |
|---|---|---|---|
| 1 | **Idea → spec.** Ten prewritten varied prompts (vague, EN/ES, new mod and extension) produce a correct spec with at most three questions and no file changes before approval. | `tests/v1/prompts/*.md` + recorded specs in the repo | R3 |
| 2 | **Static content.** Items, blocks, recipes, loot tables, creative tabs, lang, placeholder textures. | One example per type with a complete `EVIDENCE.md` | R5 |
| 3 | **Controller dispatches agents.** Interpreter → Planner → Scrum → Coordinator → Coder → QA run from the controller (UI or CLI), with tasks, leases, handoffs and evidence in the Footprint. The user never opens Claude Code by hand. | A full run recorded in the Footprint and visible in the UI | R2 |
| 4 | **Repair loop.** Three deliberately injected build failures; the Debugger fixes at least two without human intervention. | The three failure fixtures and their Footprint runs | R5 |
| 5 | **Extend an existing mod.** Add an item to a known-good project without breaking it. | Known-good project + one change + evidence | R8 |
| 6 | **Simple mob.** New entity with a Blockbench model and texture, GeckoLib idle + walk animations, basic AI (wanders; hostile or passive), spawn egg, loot on death. Spawns, moves, animates, dies, drops. Model either user-supplied `.bbmodel` or agent-generated via the audited Blockbench MCP. **Excluded:** bosses, phases, custom AI, custom sounds, variants, natural biome spawning. | `EVIDENCE.md` with `CONTENT_VERIFIED` and a short in-game clip or screenshots | R6 |
| 7 | **Descriptive UI.** The user sees who is working on what, what changed, what failed and why, and what needs approval — without reading code or a terminal. | RTQ completes criteria 3 and 4 using only the UI | U7 |
| 8 | **Clean-machine install** from `SETUP.md` alone, Windows and Linux. | CI (Linux) + one manual Windows install | R9-lite |
| 9 | **Stability.** Seven consecutive days with no High finding in `TESTING_LOG.md`. | TESTING_LOG | — |

## In scope: R2, R3, R4, R5, R6, R8, U7. Out of scope (v2): R7 worldgen, R9 wizard, R10 distribution, R11.

## Anti-loop rules

1. Every feature branch names the criterion it advances in its commit message (`[v1:#3]`). A change that
   advances none goes to `docs/V2_BACKLOG.md` instead of being built.
2. Bugs are always fixed. Unplanned features are never built before v1.
3. Criteria are not reinterpreted mid-way. If one proves wrong, it is changed here, in a reviewed commit,
   with the reason.
4. When all nine pass, tag `v1.0.0` that day. No "one more thing".

## Progress

Updated by hand at each `dev → prod` promotion.

| Date | Tag | Criteria passing | Notes |
|---|---|---|---|
| 2026-10-21 | v0.4.0-prealpha | 0 / 9 | R0–R1 done. R2 ≈ 35 % (adapter files + proof that a subagent works under gates; controller-side dispatch, statuses, activity feed not built). Estimated ~8–10 % of v1. |
| 2026-10-21 | dev (`claude-feature/r2-dispatch`, before host run 4) | 0 / 9 | R2 ≈ 75 %: controller-driven dispatch, Claude Code provider, handoff schema, task states, runs table, orchestrate loop with budgets, restart reconciliation, UI activity feed + verification + evidence panels. Unit-tested with a fake provider only; **criterion 3 needs one real `craftctl dispatch` run on the owner's machine**, criterion 7 needs the UI seen in a browser. Not built: cancel of a running worker, concurrent workers. |
| 2026-10-21 | `claude-feature/r2-dispatch` @ host run 4 | **1 / 9** (#3) | #3 observed on the owner's machine: controller dispatched a real Claude Code coder (4 runs, ~$2.63), accepted its edits, rebuilt through the trusted path, BUILD_PASS #2. #5 at build level (in-game pending). #7 UI built, not yet seen in a browser. 8 controller bugs (D1–D8) found and fixed by the live run. |
| 2026-10-21 | dev @ 09b8694 | **2 / 9** (#3, #5) | #5 observed: `wrap_test3` (ruby + ruby ore, known-good) extended with `sapphire` by a controller-dispatched coder; edits accepted as a manifest revision; trusted rebuild BUILD_PASS #2 (`7debfd3d…`); owner saw Sapphire in the Ingredients tab next to Ruby (`CLIENT_BOOT_PASS`, `CONTENT_VERIFIED`, 56 mods loaded). SERVER_BOOT_PASS for the revised source not yet recorded. |
