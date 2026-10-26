# Provenance — tools/blockbench-mcp-safe

Independent, dependency-free MCP stdio server for `.bbmodel` / GeckoLib authoring, written by the project
owner with LLM assistance as a security-first alternative to jasonjgardner/blockbench-mcp-plugin (GPL-3.0).
No upstream source is included. License: MIT (see LICENSE).

Vendored here at **v0.5.1** (2026-10-25). Integrity: `SHA256SUMS.txt` (run `npm run sums` after any change).

Verified by the controller maintainer before vendoring (sandbox, Node 22):
- zero npm dependencies; no `fetch`/`child_process`/`eval`; stdio only; writes only with `--allow-write`;
  live bridge opt-in (`--enable-live`) and file-based (no sockets).
- 51 tests pass (1 skipped: the Blockbench-exported fixture still needs a human with Blockbench).
- A six-bone quadruped with idle+walk built through the tools passes `bbmodel_validate` and
  `bbmodel_validate_animations` of jasonjgardner/blockbench-mcp-plugin 1.10.1, and the exported
  `.geo.json` is identical bone-by-bone to that project's exporter output (CI keeps this oracle check on Linux).
- CPU render with texture and animation pose works without a GPU.

Still unverified: opening the produced `.bbmodel` in Blockbench 5 with the GeckoLib plugin (owner task).
