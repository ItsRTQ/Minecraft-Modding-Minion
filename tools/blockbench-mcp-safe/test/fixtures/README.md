# Real Blockbench 5 / GeckoLib compatibility fixture (pending)

A **human** must create and save `blockbench5_geckolib_min.bbmodel` using
Blockbench 5.x with the GeckoLib Animation Utils plugin installed.

Minimum: GeckoLib Entity format, one named bone `body` with origin `[0,0,0]`,
one 2x2x2 cube parented to the bone, a single animation clip named
`animation.fixture.idle` with numeric rotation keyframes, 64x64 resolution.

The test `test/fixture-compat.test.mjs` runs if the file is present, and
otherwise reports SKIP. **Do not label an artificially generated file as a real fixture.**

Export native `geo.json` and `animation.json` from Blockbench for optional
byte-independent comparison in subsequent compatibility tests. Confirm exact
Blockbench version and plugin version in a separate text file.
