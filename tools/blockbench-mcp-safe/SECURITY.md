# Security review — v0.5.1

## Threat model

This project exposes controlled operations on local `*.bbmodel` and exported GeckoLib JSON to an MCP client. The **MCP client and agent may be untrusted**; every call is checked against a workspace basename policy and read-only/write feature flags. This is not a secure OS sandbox and cannot protect against a fully compromised local user account or malware running as the same user.

## Protections reviewed

- stdio-only transport; no network binding, shell, child process, dynamic dependencies or arbitrary-code-evaluation tools.
- `--allow-write` required for new projects, edits, duplication and writing compiled export JSON.
- `--root` absolute path, resolved through `realpath()` at process start. Model names are single, restrictive basenames; `.geo.json` and `.animation.json` outputs enforce distinct basename allowlists.
- Reads reject symlinks, hardlinks (`nlink!==1`), non-regular files, oversized models. Descriptor identity `dev/ino` checked after opening with `O_NOFOLLOW` where supported.
- Writes use unpredictable temp filenames with exclusive creation, fsync, cooperative mkdir lock, SHA-256 expected-revision checks and atomic rename. New models and exports use atomic hardlink creation and reject overwrite. Export overwrite only when `overwrite:true` is explicit, with `--allow-write`, after a same-file lock and symlink/hardlink/nonregular checks, via temp+rename.
- Incoming JSON-RPC lines <=1 MiB, outgoing responses <=1 MiB. Model JSON <=5 MiB, with node/depth bounds. Model traversal has limits. Dangerous `__proto__`, `prototype`, `constructor` object keys are rejected by parsed model guard.
- Restricted GeckoLib authorship: no script expressions, URL imports, UI actions, shell tools, GPU rendering or arbitrary remote asset loading. Optional PNG reads occur only from safe workspace basenames. Numeric keyframes only; missing bones, invalid axes, duplicate names, unsupported geometries and bad loop seams fail closed.
- Compiler uses Blockbench-to-Bedrock X-axis transform for cubes/bones and position/rotation animation channels, not arbitrary user-supplied JavaScript functions.

## Known limitations and residual risks

1. **No live compatibility proof:** project metadata, `.bbmodel` format changes and GeckoLib plugin-specific behavior can differ. Tests verify internal consistency and documented JSON conventions, not Blockbench GUI rendering or actual Minecraft/GeckoLib loading.
2. **Malicious same-user process:** processes with user filesystem privileges can read/change workspace files and may race around lstat/revision checks. These locks only coordinate clients that follow them; not a security boundary.
3. **Workspace exposed to AI:** names, geometries and revisions are returned to the connected MCP client. Only put approved model files in the dedicated workspace.
4. **Read-only is not a filesystem sandbox:** the MCP process inherits the parent user's OS rights. Explicit root and basename policy limit only operations implemented here.
5. **Mod compatibility:** PNG can be embedded into `.bbmodel` but is **not** exported into `.geo.json`; provide texture in mod assets separately. Animation curves support numeric keyframes and allowlisted easings, not Bezier/Molang/effects/controllers or rotated per-face UV. Box UV overflow is now a hard export validation error. GeckoLib Armor template bones are not generated.
6. **Untrusted existing models:** this validator intentionally rejects unsupported structures for GeckoLib exports. For Generic `.bbmodel` editing, only structural validation is available.
7. **No Windows integration test:** `npm test` was executed on Node.js in Linux. Verify in your actual host OS before production use.
8. **No independent third-party pentest, external security audit, or dependency attestation:** Node runtime itself remains part of the trusted computing base. The zero-dependency runtime minimizes but doesn't eliminate supply-chain risk.
9. **No automatic backup:** atomic writes preserve integrity against partial writes, not incorrect authorized edits. Keep version control and backups.
10. **Data loss / unsupported fields:** if a GeckoLib file uses attributes outside this subset, exports reject explicitly for most relevant structures, but do not claim round-trip equivalence with Blockbench's official exporters. Prefer native exports for release builds until a live comparison passes.

## Security tests run

`node --check` syntax validation and `node --test` suite, including real MCP stdio exchange, negative and positive GeckoLib exports, read-only permissions, path traversal, symlink/hardlink refusal, output overwrite refusal/explicit atomic overwrite, revision conflicts, invalid keyframes, corrupted models, fake PNGs, CRC and zlib validation. The real Blockbench 5.x fixture test is SKIPPED until a human supplies it.

## New input constraints

- PNG inputs must be safe flat `.png` filenames inside `--root`, regular files with a single hardlink and size <=2 MiB. PNG container CRC, non-interlaced IHDR, bounded zlib decompression, row filter and texture dimensions are validated; the preview can decode embedded PNG into bounded RGBA memory via Node zlib; invalid filters, CRCs, palettes and dimensions are rejected. Texture sources are never fetched from URLs or disk paths inside `.bbmodel`. PNG files with valid container data can still contain semantically unusual colors. Multi-texture workflows are not supported.
- GeckoLib exported JSON overwrite is opt-in and uses temp+rename; it has no `expected_revision` parameter for the *export target*. Concurrent **cooperating** writers serialize via `*.lock`. A noncooperating same-user process can still race the checks; use a private workspace. The source `.bbmodel` may be modified concurrently during export; use generated `source_revision` and repeat if necessary.
- Embedded PNG data and geometry are exposed to any connected MCP client requesting source data, so the MCP client must be trusted.
- All animation easing behavior is based on documented GeckoLib key names and tested generated JSON; exact render playback requires native verification.

## Usage recommendations

- Keep the MCP server in read-only mode unless editing is necessary.
- Never auto-approve write operations in a client that consumes untrusted content.
- Avoid administrative privileges. Use a model-only workspace, no secrets.
- Limit filesystem permissions at OS level and use backups.
- Pin the delivered ZIP's SHA-256 when distributing across machines and verify its contents before execution.
- Test every exported mob and animations with a real Blockbench + GeckoLib setup and in-game.

**No guarantee:** Test passing does not prove absence of vulnerabilities. Report defects as reproductions with minimal sample models and steps. Do not paste credentials or proprietary models in public issues.

## v0.4.0 threat model extensions

- **CPU rasterizer:** no native graphics runtime, GPU, network or external packages. It now decodes embedded PNG images, samples box/per-face UVs, and applies numeric animation poses. This adds CPU/memory and PNG parsing attack surface; the decoder has bounded inflate size and the renderer limits triangles and image pixels. Exact Blockbench WebGL parity is not claimed. Hard cap of 450 triangles and 320 px per tile, six tiles maximum. Preview PNG is returned as MCP `image` content, which discloses model geometry to the AI client by design.
- **Meshes:** only Generic `.bbmodel` supports authored meshes. 256 vertices and 256 triangle/quad faces per mesh max, finite vertices/UVs and nondegenerate faces. The GeckoLib exporter rejects mesh-bearing models to avoid deprecated Bedrock `poly_mesh` output.
- **Live plugin:** opt-in, separately loaded desktop JavaScript code. It requires the user's manual workspace selection and periodically writes **read-only** snapshots of scene data, a best-effort viewport PNG and status. The MCP process uses `--enable-live` as a separate permission gate, never sends commands to Blockbench, and reads only fixed files under a non-symlink `.bbms-live` folder with bounded sizes, stale-age checks, single-hardlink checks, `O_NOFOLLOW`, and pre/post identity checks. The plugin itself runs inside Blockbench with its app-level permissions: review before loading. The bridge directory shares access controls with `--root`; anyone with write access to it can forge a snapshot. It is not cryptographically authenticated. Do not share this workspace with untrusted local processes or users.
- **Large screens:** viewport screenshots greater than 768 KiB are not published. A missing screenshot is reported as an error rather than returning an old one.
- **Quality gates** are heuristics. Passing them does not prove visual quality, texture packing, native or game compatibility.
- **Testing status:** automated Node tests and mock desktop integration passed; no real Blockbench 5.x + GeckoLib test, GPU-specific screenshot test, Windows test, or external audit was performed.

## v0.5.0 texture and animation preview review

- `src/texture-render.mjs` calls validated PNG container parsing (`src/png.mjs`), bounded `inflateSync`, implements PNG filters 0–4 and copies into a bounded RGBA buffer. It permits common noninterlaced 8-bit/packed PNGs but refuses unsupported 16-bit formats rather than silently misrendering. Does not invoke native image libraries, external image fetchers, or subprocesses.
- `src/render.mjs` maps box/per-face UV, renders with a software Z-buffer, applies cube Euler rotation and hierarchical parent/child bone transforms using `samplePose`. Depth sorting of semitransparent triangles is approximate. Rendering can be resource intensive for dense scenes despite the 450-triangle and maximum tile-size constraints.
- `bbmodel_render` exposes `animation`, `time`, `wrap`, and `textures`. Output PNG saves still require `--allow-write`; rendering in memory remains read-only. MCP image delivery enforces a ~600 KiB PNG budget to leave room below the 1 MiB JSON response cap; large renders require `output_file`.
- Threat model: an untrusted MCP agent can invoke rendering repeatedly and consume local CPU; MCP alone is not an OS resource sandbox. Enforce limits externally for hostile clients. Embedded textures and generated previews reveal private geometry/skins to the AI client.
- New tests verify actual UV pixel sampling, per-face rotation, invalid embedded texture rejection, distinct animated renders, read-only restrictions, and saved PNG validity. Native Blockbench + GeckoLib parity remains **untested**.
