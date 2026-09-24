---
name: liquid-materials
description: Design fluid-color shaders and glass materials within an established visual direction for web interfaces. Use for liquid glass, iridescence, aurora, refractive surfaces, or choosing between Paper Shaders, React Bits, and shaders.com. Covers visual direction, component selection, and implementation guardrails; not a general UI redesign or automatic dependency installation.
---

# Liquid Materials

Follow the [local skill map](../impeccable/reference/skill-map.md). This specialist implements the selected direction; open product-wide design questions return to impeccable. A scoped component or material request does not restart the full design process.

Make the material distinctive while keeping the interface usable without it. The user's brief decides how expressive the result should be; restraint is a suitable default for task-oriented software, not a rule for every artwork or landing page.

## Establish the scope

Identify the requested deliverable: research, a material proposal, an isolated prototype, or an application change. Research and planning do not authorize changes to the application, package installation, account connections, or deployment. Preserve existing functionality and uncommitted work.

Inspect the target's actual palette, styling system, dependencies, and usage scene. Distinguish a task interface from a showcase. For a targeted material change, preserve navigation, content, message spacing, and interaction contracts rather than redesigning the whole product.

## Choose a material, not just an effect

Separate three decisions:

- **Color source:** a still gradient, procedural flow, or an image supplies variation.
- **Surface:** tint, transmission, blur, and edge highlights establish the glass.
- **Distortion:** an optional filter bends a particular input texture or supported backdrop.

A shader-generated gradient is not automatically refractive glass. An image filter cannot automatically sample arbitrary HTML behind its canvas. A uniform background needs some tonal variation for transmission to become visible, but this does not require a wallpaper or a full-screen animated background.

Compare at most a few materially different directions. Describe where each would appear, which content stays quiet, and the relevant tradeoff. For restrained opalescent glass or a material that feels heavy, read [the material recipe and refinement example](references/smoked-pearl.md). Distinguish exploratory settings from the approved product-specific example; neither is a universal palette.

Read [the component map](references/component-map.md) when selecting a library. Inspect the exact source or registry payload before importing it. Do not infer dependencies, browser support, or production behavior from a demo's appearance or a component count.

## Keep the material subordinate to the task

Before tuning the material, check the surrounding layout, type hierarchy, and control geometry. Fix concrete misalignment, broken label wrapping, or competing emphasis first; stronger blur, color, and motion cannot repair those relationships. For a scoped material change, keep this check local. The interface must retain its structure and usable contrast with the enhancement disabled.

For an operating interface, establish a main expressive area. Secondary controls can share its palette without repeating its shell, glow, or elevation. Keep reading surfaces stable and mostly opaque; place color in soft patches within the chosen surface, not automatically around its entire perimeter. Never distort editable text, filenames, focus indicators, or progress information.

If the request is for a lighter, more integrated feel, inspect the combined border, inset highlights, colored rim, shadow, and focus outline. Individually subtle layers can form a conspicuous frame in dark mode. Remove redundant emphasis before reducing all color or adding motion. Ambiguous feedback such as "not alive enough" needs a check of material weight and actual animation state, not an automatic continuous loop; honor an explicit motion request when one is given.

Describe motion through states: idle, focus/interaction, settled, reduced motion, and unavailable GPU. A bounded response to focus or a drop is often sufficient. Avoid re-triggering a material animation on every keystroke. Decorative motion must not signal completion, invent progress, or delay a real action.

Preserve semantic color. A pearl reflection is not a success state; a colorful rim is not the only keyboard focus indicator. Check text against the brightest plausible composite, not just the dark base token.

## Runtime decisions that matter

- Render the usable DOM and static material before loading the GPU enhancement. In SSR frameworks, initialize GPU resources after mount; a client-component declaration alone does not make arbitrary module-level browser access safe.
- Keep decorative layers non-interactive and hidden from accessibility APIs. Clip them to the complete surface shape, including every rounded corner; keep focus indication outside that decorative clip. They must not intercept selection, scrolling, drops, or controls.
- Prefer one bounded canvas over canvases in repeated message or file rows. Measure a proposed library's actual bundle impact; do not add multiple render engines for one effect.
- Lower animation speed is not a lower frame rate. Setting opacity to zero is not stopping rendering. Stop the animation loop or unmount the enhancement while idle, hidden, or offscreen, using the selected renderer's actual lifecycle.
- Bound physical pixel count. A property called `minPixelRatio` is a lower bound, not a device-pixel-ratio cap. Start with modest resolution for blurred color fields and inspect on the intended devices.
- Use renderer uniforms or refs for animation, not React state on every frame. Clean up observers, listeners, frame requests, and GPU resources, including Strict Mode remounts.
- Keep a visible static fallback for blocked GPU access, initialization failure, context loss, and code-split load failure. Reduced motion freezes or removes the effect; reduced transparency and increased contrast use opaque surfaces.
- Do not use private messages, account information, or remote user files as shader inputs merely to make glass visible. Inspect telemetry and external requests before adopting a runtime.

## Proportional verification and stopping

For research, distinguish inspected source, observed demo behavior, proposed settings, and untested assumptions. Do not claim target-phone performance from a desktop screenshot.

For implementation, verify the changed surface with real content: long filenames or text, focus, actual pending/error states, and the relevant desktop/mobile layouts. Include the static/no-GPU and reduced-motion paths when adding a shader. Inspect dark and light idle/focused views in the surrounding interface, not only a magnified component. Computed styles and passing tests establish technical behavior, not visual balance.

When frost appears absent, inspect the computed `backdrop-filter` in the production build before compensating with more transparency or blur. Declaration ordering and CSS optimization can affect vendor-prefixed fallbacks; do not assume source CSS proves the effect reached the browser. Use one batched visual pass, correct concrete defects, and confirm the affected paths; do not turn refinement into an open-ended gallery exercise.

Report what changed, the selected runtime and why, the evidence obtained, and remaining device limitations. Stop at the requested artifact or verified change. Installing this skill does not install any component library.
