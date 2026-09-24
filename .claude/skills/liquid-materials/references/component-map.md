# Shader and glass component map

Inspected on 2026-09-22. These are selection notes, not installed dependencies. Verify the exact version or registry item before implementation; upstream defaults and APIs can change.

## Shortlist by visual job

| Component | Visual job | Runtime/input | Suitable use | Main constraint |
| --- | --- | --- | --- | --- |
| [Paper Warp](https://shaders.paper.design/warp) | Continuous liquid folds and marbling | WebGL2, procedural color | A bounded fluid-color layer beneath glass | Default presets are much more saturated and intricate than most tools need |
| [Paper MeshGradient](https://shaders.paper.design/mesh-gradient) | Slow, soft movement between color fields | WebGL2, procedural color | Softer atmospheric alternative | Blur-like softness alone does not communicate refraction |
| [Paper FlutedGlass](https://shaders.paper.design/fluted-glass) | Ribbed optical distortion | An image texture | Image treatments and material studies | Not a drop-in filter for arbitrary HTML behind a canvas |
| [React Bits Aurora](https://reactbits.dev/backgrounds/aurora) | Broad luminous curtains | OGL/WebGL | A cropped lighting accent, or a hero when requested | Review its lifecycle before embedding in an always-open tool |
| [React Bits Iridescence](https://reactbits.dev/backgrounds/iridescence) | Pearlescent spectral interference | OGL/WebGL | Small highlights and material studies | Its oscillating colors require containment and a static alternative |
| [React Bits GlassSurface](https://reactbits.dev/components/glass-surface) | Edge displacement and color separation | SVG displacement + CSS backdrop filtering | Optional enhancement for supported browsers | Inspected implementation deliberately falls back on Safari and Firefox |
| [React Bits LiquidEther](https://reactbits.dev/backgrounds/liquid-ether) | Pointer-driven ink/fluid simulation | Three.js, multi-pass simulation | An expressive interactive scene when justified | More simulation and integration work than a procedural color field |
| [Shaders Glass](https://shaders.com/docs/components/glass) and generators | Composed generator/filter scenes | WebGPU; filters sample rendered scene layers | Rich shader compositions on a verified browser fleet | Needs GPU-unavailable fallback; review telemetry and filter-pass cost |

## Paper: primary candidate for a small product enhancement

The inspected [React package manifest](https://github.com/paper-design/shaders/blob/main/packages/shaders-react/package.json) lists version `0.0.81`, React 18/19 support, and the matching core package. This is source evidence, not confirmation of the latest npm release. The [repository](https://github.com/paper-design/shaders) advises exact version pinning while using `0.0.x` releases.

Read the selected component's props and the installed implementation. The inspected [ShaderMount](https://github.com/paper-design/shaders/blob/main/packages/shaders/src/shader-mount.ts) uses WebGL2, stops its frame loop at zero speed, and accounts for document/element visibility. Initialization can throw when WebGL2 is unavailable. Supply an application-owned static fallback rather than assuming the runtime will render one.

`minPixelRatio` defaults to 2 and is not a cap. Use `maxPixelCount` to constrain the rendering workload. Neither low speed nor a CSS mask by itself limits the number of pixels evaluated by the fragment shader.

## React Bits: copy a selected component, not a whole stack

The user-supplied Aurora registry endpoint was fetched successfully. At inspection:

| Registry item | Files | Dependency |
| --- | --- | --- |
| [Aurora-TS-TW](https://reactbits.dev/r/Aurora-TS-TW) | One TSX component | `ogl@^1.0.11` |
| [Aurora-TS-CSS](https://reactbits.dev/r/Aurora-TS-CSS) | TSX and CSS | `ogl@^1.0.11` |

Select the variant matching the application. A plain-CSS project does not need Tailwind or shadcn initialization to adopt the visual idea. Registry commands can write files and dependencies; inspect before executing and do not install during a planning task.

The inspected [Aurora source](https://github.com/DavidHDev/react-bits/blob/main/src/ts-default/Backgrounds/Aurora/Aurora.tsx) requests animation frames continuously; its `speed` changes shader time rather than stopping the loop. The source does not implement a reduced-motion policy or element-visibility pause. Add those policies if adopting that version. Its window resize listener also deserves attention in containers that resize without a window resize.

[Iridescence](https://github.com/DavidHDev/react-bits/blob/main/src/ts-default/Backgrounds/Iridescence/Iridescence.tsx) similarly needs lifecycle review. [LiquidEther](https://github.com/DavidHDev/react-bits/blob/main/src/ts-default/Backgrounds/LiquidEther/LiquidEther.tsx) imports Three.js and includes iterative fluid passes; this supports an expectation of higher integration/workload complexity, not a measured performance comparison.

[GlassSurface](https://github.com/DavidHDev/react-bits/blob/main/src/ts-default/Components/GlassSurface/GlassSurface.tsx) generates a displacement map and applies a backdrop SVG filter when its support test permits it. Keep a deliberate CSS fallback and test real target browsers; successful CSS parsing is not proof of identical rendering.

## shaders.com: composition toolkit, not the default compatibility baseline

The [React integration](https://shaders.com/react) documents a transparent canvas and `onUnavailable` when WebGPU cannot initialize. This is a fallback hook, not an automatic WebGL renderer. Do not treat broad browser-support marketing as confirmation for a managed work computer or a particular phone.

The [performance guide](https://shaders.com/docs/guide/performance) distinguishes procedural generators from filters requiring render-to-texture passes. Avoid stacking Glass, Blur, and other filters without a visual reason and measurement. The guide also notes that zero opacity still renders a layer; its `visible` control excludes layers. Its published timing estimates are not benchmarks for the target product.

The [telemetry guide](https://shaders.com/docs/guide/telemetry) documents collection of installation domain and runtime FPS, disabled in local development. For a private utility, explicitly review this behavior; the documented production opt-out is `disableTelemetry={true}` on `Shader`.

## Design guidance, not runtime code

[Anthropic frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) informed the emphasis on a product-specific direction, sparse purposeful copy, and concentrating visual expression rather than spreading it over every component. It is not a shader implementation or a requirement to add landing-page typography to a tool. The user's pinned visual brief takes precedence over stylistic defaults.

## Reuse notes

No upstream component source is bundled in this skill. Paper's inspected package is Apache-2.0; React Bits identifies MIT plus Commons Clause in its repository. Preserve applicable upstream notices if copying code and check the selected version's terms when redistributing a library. Using a visual reference does not require installing or copying its implementation.
