# v0.5.1 implementation review — textured, pose-aware CPU previews

**Scope delivered:** PNG decoding (bounded Node zlib, 0-4 PNG row filters, common color formats), box and per-face UV sampling, 90-degree UV rotation, cube origin/rotation and hierarchical bone animation sampling. `bbmodel_render` now accepts `animation`, `time`, `wrap`, `textures`. Output reports `texture_applied`, `sampled_time`, `triangles`. Six-view contact sheets and atomic PNG writes remain available.

**Security controls preserved:** zero external NPM dependencies, stdio-only, no network fetching, shell or arbitrary JavaScript execution, flat workspace allowlist, `--allow-write` for files, SHA-256 revision checks on edits, symlink/hardlink defenses and cooperative locks. Decoder never follows texture paths in source files. Output image response size is bounded separately from disk save.

**Automated validation:** `npm run check` and `npm test` (48 passed, 1 skipped), additional pixel-level RGB/UV tests and MCP end-to-end animation tests in `test/features-v05.test.mjs`. PNG examples rendered and visually inspected. The skipped test awaits an authentic Blockbench 5.x GeckoLib native fixture.

**Not claimed:** exact WebGL/Blockbench texture filtering or lighting, animation playback equivalence, Bezier/Molang, PBR/materials, native GPU rendering, Windows integration, independent security audit or an in-game correctness guarantee. Local Euler XYZ composition is an approximation pending native fixture comparison.

---

# v0.4.0 supplementary review

**Added surface:** fixed file snapshot bridge (opt-in), CPU-generated PNG images, Basic mesh authoring, per-face UVs, numeric pose sampling, configurable geometry gates.

**Security retained:** no external dependencies, no HTTP/TCP, no subprocess, no shell, no JS evaluation, flat workspace, SHA-256 edits, cooperative locks, PNG writes atomic, live bridge read-only.

**Compatibility unverified:** real Blockbench desktop integration, GeckoLib native fixture, animation runtime and GPU screenshots; mesh exports intentionally disabled to prevent deprecated Bedrock `poly_mesh`.

**Evidence:** `npm test`; `npm run check`; `SHA256SUMS.txt`; `test/features-v04.test.mjs` and `test/live-plugin.test.mjs`. Review and approval for tool writes remains necessary.

---

# v0.3.0 feature acceptance (historical) / review

This is a **self-review of the independent implementation**, not an outside security audit or native Blockbench compatibility certification.

| Requested item | Result | Evidence / constraints |
|---|---|---|
| 1. Iterative re-export | Implemented | `overwrite` defaults false; explicit opt-in overwrite through a temp file + rename; `path`, `overwritten`, `sha256`; `test/improvements.test.mjs`. |
| 2. MCP initialize instructions | Implemented | `src/server.mjs`, initialize integration test; full workflow, revision, X-axis export convention. |
| 3. Embedded PNG texture | Implemented with validation | `src/png.mjs`, `readWorkspacePng`, `bbmodel_geckolib_set_texture`; safe basename, CRC, bounded inflate, dimension match, texture UUID on all cube faces. PNG file for GeckoLib assets still distributed separately. |
| 4. Native Blockbench 5 fixture | **Pending real fixture** | `test/fixture-compat.test.mjs` is skipped until `test/fixtures/blockbench5_geckolib_min.bbmodel` is supplied by a person using Blockbench 5.x + GeckoLib. Do not claim compatible on native app yet. |
| 5. Clip/track controls | Implemented | `remove_animation`, `remove_track`, `replace_tracks:false` merge, require expected revision; tests. |
| 6. Keyframe interpolation | Implemented subset | Allowlist of linear, catmullrom and GeckoLib ease presets. JSON format tested; playback not verified in Blockbench/GeckoLib. No Molang/Bezier. |
| 7. Cube mirror | Implemented | `mirror` on add/update cube, `mirror:true` only for mirrored cubes; X-coordinate export unchanged. |
| 8. Stricter GeckoLib validation | Implemented | UV overflow error, empty bone warning, zero scale warning, keyframe-after-end error; tests. |
| 9. Compact scene | Implemented | `bbmodel_geckolib_read_scene`: hierarchical bones with compact cube coordinates. |
| 10. Actionable errors | Improved | Unknown operations and unexpected arguments enumerate valid entries. Additional validation messages include offending bone or clip. |
| 11. Checksums/version | Implemented | `npm run sums` generates `SHA256SUMS.txt`; `serverInfo.version=0.3.0`; `CHANGELOG.md`. |
| 12. Security architecture | Preserved | stdio only, no user-provided JS execution, no HTTP listener, no runtime NPM deps, no network downloads, workspace basenames, symlink/hardlink checks, revision-based edits, locks. |

## Tests actually executed

- `npm run check` using Node.js syntax checker.
- `npm test` via built-in `node:test`: 33 pass / 1 skip / 0 fail on Linux.
- Additional final release verification: extract the ZIP, run `sha256sum -c SHA256SUMS.txt`, `npm run check` and `npm test` from the extracted directory.

## Limits that remain

- Human-produced Blockbench 5.x file fixture and an actual Blockbench + GeckoLib roundtrip are **not available**. Pixel textures, animation easing playback and native plugin metadata may need adjustments when a fixture is supplied.
- No live Windows test, no external penetration test, no third-party dependency attestation.
- Lock files are cooperative and filesystem protections are not a Windows/Linux OS-level sandbox. Malicious processes running with the same user can potentially interfere with files under the workspace.
- Prior versions tested PNG metadata only; v0.5.0 adds actual raster pixel tests. Native parity is still unknown.
- The private workspace should contain only approved asset files, and the agent/client must be treated as a sensitive trust boundary.
