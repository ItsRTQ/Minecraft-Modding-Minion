# GeckoLib — version pin for the Fabric 1.21.1 profile

Pinned: `software.bernie.geckolib:geckolib-fabric-1.21.1:4.7.3` from the official Cloudsmith Maven
(`https://dl.cloudsmith.io/public/geckolib3/geckolib/maven/`, `content { includeGroup 'software.bernie.geckolib' }`),
declared in `gradle.properties` as `geckolib_version` by `src/mod_orchestra/geckolib.py` only when the spec has mobs.
`fabric.mod.json` depends on `geckolib >= 4.7`.

Evidence (2026-10-24, Round 4 in `docs/TESTING_LOG.md`): the POM for 4.7.3 resolves (HTTP 200), a generated
project with two mobs compiles (`BUILD SUCCESSFUL`, Loom 1.18.4, JDK 25 host, `--release 21`) and the dedicated
server boots with `geckolib 4.7.3` in the mod list. The same `maven-metadata.xml` listed newer 1.21.1 builds up to
`4.9.3`; the pin stays at 4.7.3 until a build + game run with a newer version is recorded here.

API surface used (4.7.x package names; 4.5 moved them out of `core.*`, do not copy older snippets):
`software.bernie.geckolib.animatable.GeoEntity`, `animatable.instance.AnimatableInstanceCache`,
`animation.{AnimatableManager, AnimationController, AnimationState#isMoving, RawAnimation, PlayState}`,
`util.GeckoLibUtil#createInstanceCache`, `model.DefaultedEntityGeoModel` (assets at `geo/entity/<id>.geo.json`,
`animations/entity/<id>.animation.json`, `textures/entity/<id>.png`), `renderer.GeoEntityRenderer`.

Sources: [GeckoLib repository](https://github.com/bernie-g/geckolib), [wiki](https://github.com/bernie-g/geckolib/wiki),
[examples](https://github.com/bernie-g/geckolib-examples), [Cloudsmith listing](https://cloudsmith.io/~geckolib3/repos/geckolib/packages/).
`.bbmodel` is editable source; GeckoLib `.geo.json`, animation JSON, PNG and renderer/controller Java must agree. Model
source, rig, UV coverage, animation names and in-game rendering are separate QA gates.
