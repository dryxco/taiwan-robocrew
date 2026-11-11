# Night Shift market environment

The shipped environment is **original procedural geometry**, authored in `src/scene/marketEnvironment.ts`. No RoboCasa mesh, texture, code, font, or dataset is redistributed. No network download is needed to construct the scene. `public/market/manifest.json` records provenance and spatial conventions.

## Scene API

```ts
import { buildMarketEnvironment } from './scene/marketEnvironment';
const market = buildMarketEnvironment(scene);
// In your render loop:
market.update(clock.getElapsedTime());
// Before replacing/unmounting the scene:
market.dispose();
```

Requires `three` and, for TypeScript, `@types/three`. It must run in a browser with a canvas 2D context. The factory adds one named group and returns `group`, `stalls`, `update(seconds)`, and idempotent `dispose()`. It does not change camera, renderer, scene background, fog, or global lighting. Provide hemisphere/ambient light and a directional moon light; the factory supplies three local warm point lights and emissive signs. A useful initial eye position is `(0, 1.65, 5.5)`, looking toward `(0, 1.6, -2)`. Suggested fog color: `#161e2e`; suggested fog distance: 12–35 m. No bloom is required.

Coordinates are metres, Y-up, +Z toward the street. Stall centres are `jipai=(-4,0,-3)`, `pepper-bun=(0,0,-3)`, and `bubble-tea=(4,0,-3)`. Returned anchors are world-space `position`, `approach` (eye level), and `counter`. Central walking space is approximately `x=[-6,6], z=[0.6,5.5]`; the pepper oven protrudes to z≈−0.82. The ground reaches x±12 and z±9.5. Keep the walking camera outside counters; this art module supplies no character collision or food simulation. All decorative food is static. Interaction/physics objects should be separate meshes under the coordinator's control.

Includes striped awnings, Traditional Chinese illuminated signage, menu boards, hanging lanterns, animated steam, kitchen props, metal counters, stools, tables, crates, festoon cables, pavement, gutters, puddles, tiled shop aprons, shuttered shophouses, balconies, AC units, and rooftop tanks. Art is deliberately low-poly. CJK text uses system fonts (`PingFang TC`, `Noto Sans TC`, `Microsoft JhengHei`); install a CJK font on screenshot/CI machines to avoid missing glyphs. Canvas sign textures are owned and disposed by the factory. Each geometry/material is also disposed; the factory does not dispose caller-owned assets.

## Optional MuJoCo backdrop

`server/assets/market_backdrop.xml` is an include fragment for **inside `<worldbody>`**, not a standalone simulation. It supplies decorative, non-colliding stall silhouettes and lanterns using `contype="0" conaffinity="0"`. It intentionally supplies no floor, lights, contacts, cameras, or physics food. Coordinates convert Three `(x,y,z)` to MuJoCo `(x,-z,y)` (Z-up). All names have `market_decor_` prefixes. The server worker owns actual simulation fixtures; do not treat this decorative include as collision geometry.

## RoboCasa investigation — primary sources checked 2026-11-11

| Source | Observed facts and reuse relevance |
| --- | --- |
| [Official repository README](https://github.com/robocasa/robocasa#license) | Explicitly separates **MIT** code from **CC BY 4.0** assets and datasets. The install instructions describe roughly 10 GB of assets. |
| [Repository LICENSE](https://github.com/robocasa/robocasa/blob/main/LICENSE) | MIT, copyright 2026 the RoboCasa Team; includes a notice about partial MuJoCo implementation under Apache 2.0. This is a code license, not a blanket replacement for asset licensing. |
| [Official download registry](https://github.com/robocasa/robocasa/blob/main/robocasa/scripts/download_kitchen_assets.py) | Separately downloads textures, generative textures, Lightwheel fixtures, Objaverse objects, AI-generated objects, and Lightwheel objects. It supports selecting categories with `--type`. |
| [Official kitchen object registry](https://github.com/robocasa/robocasa/blob/main/robocasa/models/objects/kitchen_objects.py) | Categories inspected include bowls, cups, coffee cups, condiment bottles, bottled drinks, and bread. These are plausible reusable counter props; the registry contains scale adjustments and exclusions for some defective geometry. |
| [Official stove fixture implementation](https://github.com/robocasa/robocasa/blob/main/robocasa/models/fixtures/stove.py) | The stove fixture points to MJCF and provides burner and knob behavior. This is potentially useful for indoor cooking simulation, but does not establish a Taiwan street-stall asset or cylindrical pepper-bun oven. |
| [Creative Commons CC BY 4.0 deed](https://creativecommons.org/licenses/by/4.0/) | Reuse requires appropriate attribution, a license link, and identification of changes; retain supplied attribution notices. |

The registry and license files were examined; the multi-gigabyte archives were **not downloaded**, and individual archive contents/asset attribution records were not inspected. No claim is made that a particular model is validated, production-ready, or already included here. If adding a model later, retain its individual creator/source metadata and applicable notices, record the exact source revision and asset path, check its actual license, and validate geometry/conversion. MJCF fixtures require mesh/material extraction and axis conversion before browser rendering; a `.xml` fixture is not a GLB.

The current procedural route gives the requested Taiwanese visual identity without an asset-download prerequisite. It does not replace the detailed object physics or existing asset diversity of RoboCasa.

## Verification

Validated with Three.js and strict TypeScript (`ES2022`, bundler resolution). A construction smoke check verified finite geometry and world matrices, all three anchor coordinates/IDs, animation at multiple timestamps, raycasts finding all three stall IDs, and idempotent disposal of every retained geometry, material and canvas texture. The resulting scene has 374 meshes, 37,568 triangles, 107 materials and 12 sign textures. Static meshes are batched by material and stall identity; `userData.stallId` exists on both stall groups and merged stall meshes for raycast selection. Browser appearance, CJK font rendering and frame rate require checking in the integrated preview; the smoke test uses a canvas stub and does not assert rendered pixels. The XML was parsed as XML, not compiled against a local MuJoCo installation.
