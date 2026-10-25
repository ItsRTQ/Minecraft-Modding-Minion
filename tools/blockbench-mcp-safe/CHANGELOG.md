# Changelog

## 0.5.1

- Made `bbmodel_sample_pose` accept `animation` (required) instead of `name`, consistently with `bbmodel_render`. Existing MCP clients must update the call field; `name` is intentionally rejected.
- Removed the obsolete generic texture warning. `bbmodel_validate` now warns only about external/unsupported texture sources and multiple textures; it does not claim embedded PNGs cannot be rendered.
- Added regression tests for the exposed MCP schema, invocation, and texture warning behavior. Security model unchanged.

## 0.5.0

- Upgraded CPU `bbmodel_render` to sample embedded PNG texture colors with box UV and per-face UV, mirroring and 90-degree face rotation.
- Added animation pose rendering (`animation`, `time`, `wrap`) with hierarchical bones, pivots, position/rotation/scale and cube rotations.
- Added a bounded, dependency-free PNG RGBA decoder (common PNG color formats) with CRC validation inherited from the existing PNG parser.
- Exposed `texture_applied`, `sampled_time`, and triangle counts; oversized MCP images require opt-in `output_file`.
- Added visual examples and tests that inspect rendered RGB pixels and verify different animation frames produce different PNGs.
- No external dependencies, HTTP listener, runtime code execution or shell tool added. Real Blockbench/GeckoLib compatibility remains unverified.

## 0.4.0

- Added CPU-rendered PNG contact sheets with MCP image content and opt-in atomic save. Flat shading (not texture/pose accurate).
- Added `bbmodel_sample_pose` with numeric keyframe sampling, Catmull-Rom and allowlisted GeckoLib easing.
- Added Generic `.bbmodel` triangular and quadrilateral mesh authoring; intentionally no deprecated GeckoLib `poly_mesh` export.
- Added per-face UV input and Bedrock per-face `uv_size`, with UV rotation geometry format upgrade.
- Added configurable model proportion, bounds, geometry and hierarchy quality gates.
- Added opt-in local read-only desktop Blockbench bridge, with `app_status`, `app_read_scene`, and best-effort `app_capture_screenshot`. No listener/network.
- Added tests for all new features and a mocked desktop bridge; real Blockbench integration remains unverified.


## 0.3.0
- Added atomic opt-in overwrites for both export tools, returning `path`, `overwritten` and `sha256`.
- Added MCP initialize instructions documenting workflow, revisions and X-axis mirroring.
- Added PNG texture embedding with workspace policy, CRC, zlib and dimensions checks; every cube face references texture UUID.
- Added animation removal, single-track removal and partial track updates.
- Added allowlisted linear, catmullrom and GeckoLib easing support, plus per-cube mirror.
- Tightened GeckoLib UV validation, zero-scale and empty-bone warnings, and over-length keyframe errors.
- Added compact GeckoLib rig scene overview, actionable errors, reproducible checksum script and a textured example.
- Added Blockbench 5.x human-exported fixture test (skipped until real fixture supplied); no claim of native verification.
- Preserved zero NPM dependencies, stdio-only, revision checks, workspace flat-basename policy and read-only defaults.

## 0.2.0
- Added GeckoLib model authoring, bone transforms and nested groups.
- Added numeric linear animation authoring for bone rotation/position/scale.
- Added independent `.geo.json` and `.animation.json` exporters with opt-in file writing.
- Added GeckoLib validation and an example 7-bone mob with idle/walk clips.
- Kept stdio-only, zero-dependency, read-only by default and revision-protected writes.
- Added GeckoLib integration and negative tests.

## 0.1.0
- Initial Generic/free `.bbmodel` headless MCP subset.
