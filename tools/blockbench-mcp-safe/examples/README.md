# GeckoLib reference mob

Three primary files were created with `node scripts/create-demo.mjs` using the MCP implementation itself:

- `gecko_test_mob.bbmodel`
- `gecko_test_mob.geo.json`
- `gecko_test_mob.animation.json`

The example intentionally uses a simple seven-bone mob (`root`, `body`, `head`, two arms, two legs) with looping `idle` and `walk` keyframes. The geometry includes example box UV offsets, **but no texture PNG**. You must supply your own 64x64 texture and validate the UV layout in Blockbench.

**Warning:** This is an internally validated static fixture. It has not been opened or played in a live Blockbench/GeckoLib session. Do not treat it as visual QA or a finished production asset.

`contact_sheet_cpu.png`: v0.4.0 4-view flat-shaded diagnostic render (front, left, back, iso). No texture sampling or bone/cube rotations.

## v0.5.0 software renderer demos

- `textured_rest.png`: 4-view embedded PNG textured model at rest.
- `textured_walk_025.png`: same texture and geometry with a sampled walk animation at 0.25 seconds.
- `textured_walk_050.png`: sampled walk at 0.5 seconds (the example animation returns to rest at this time).
- `flat_rest.png`: same model with `textures:false` (flat diagnostic shading).

These were rendered by the included CPU renderer, not captured inside a native Blockbench installation.
