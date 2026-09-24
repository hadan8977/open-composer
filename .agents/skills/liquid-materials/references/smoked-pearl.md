# Smoked pearl material recipe

A reference direction for a restrained liquid-color utility interface. The starting values below are exploratory, not a validated drop-in preset. The refinement example records a separately tested, user-approved implementation. Preserve another palette or material when the user's brief chooses it.

## Appearance

Use graphite and smoke as the structure. Put a small amount of champagne, celadon, and mauve in the material rather than tinting every surface blue. The material should read as transparent depth and a moving reflection, not a glowing outline around every card.

| Role | Starting value | Treatment |
| --- | --- | --- |
| Main canvas | `#171717` | Neutral charcoal, no animated wallpaper |
| Secondary surface | `#202020` | Navigation and quiet surfaces |
| Elevated surface | `#2B2B2B` | Clear separation without a colored wash |
| Primary text | `#F3F1ED` | Slightly warm near-white |
| Secondary text | `#B5B1AA` | Independent of animated reflections |
| Champagne reflection | `#D6BBA6` | Color field only, not small text |
| Celadon reflection | `#A6C4B3` | Color field only, not a success code |
| Mauve reflection | `#BCAFCE` | A small counterpoint, not the page tint |

These are role proposals, not complete accessibility tokens. Measure composited text, links, icons, and focus indicators separately. Keep an existing brand color in its genuine brand/action role unless the user asks to change it. Removing a blue surface cast does not require repainting the brand mark.

## Composition

For a messenger or transfer utility, make the composer the material's focal area. Keep messages and filenames on calm, readable surfaces. The transfer queue can share a subtle fill without another canvas or illuminated frame. Search, navigation, and utility actions need not each sit inside their own glass enclosure.

Think in layers:

1. Neutral application surface.
2. Bounded procedural color field inside the selected material area.
3. Translucent surface tint and restrained highlight shaping.
4. Unfiltered DOM text, controls, and focus indication.

Use a mask to place soft reflections near selected corners while keeping the reading center quiet. A corner reflection is not a continuous outline tracing the control. Masking is composition, not a guarantee of reduced GPU work. Use an optical distortion layer only if there is a defined texture to bend and its result survives browser testing.

## Refinement example: GropBox

The user approved [the lighter GropBox revision](https://github.com/hadan8977/GropBox/commit/7cef5de) after rejecting the previous version's heavy framing, especially in dark mode. The useful change was subtracting repeated structural emphasis while retaining liquid color and the existing brief shader response:

- Remove the composer's border, inset highlights, and colored rim rather than stacking them beneath a focus outline.
- Remove surrounding glass shells from the toolbar and mobile navigation. Keep selection, labels, and touch geometry visible.
- Let the send control become a filled primary action when available; its disabled state need not remain a bright disc.
- Keep reading panels opaque. Reducing visual weight does not mean allowing background text to show through.

That implementation used a single 1px inset field-focus outline, a material-layer opacity of 0.24, and stronger indicators for increased contrast. These are case details, not defaults: choose focus treatment from contrast, clipping, keyboard visibility, and platform requirements. Do not turn this result into a ban on borders or expressive glass elsewhere.

Evidence was user approval plus 14 targeted desktop/mobile-emulation browser tests covering the affected presentation and behavior. Those tests did not establish real-phone performance or prove this recipe works unchanged in other products.

## Motion proposal

| State | Proposed material response |
| --- | --- |
| Idle | A composed still frame with visible depth |
| Focus or drag entry | One brief, low-amplitude flow that settles; no caret-following effect |
| Typing | Stable center; do not restart an animation for each key |
| Uploading | Existing real progress remains authoritative; no decorative loop is required |
| Success or failure | Existing functional feedback; do not wait for the material |
| Hidden/offscreen | Renderer paused or unmounted |
| Reduced motion / no GPU | Still CSS material or static shader frame without a recurring loop |
| Reduced transparency / more contrast | Opaque neutral surface and clear focus ring |

Start with approximately 1–2 seconds for the material's interaction response. This is a design proposal, not an upload duration or a required animation delay. Longer continuous decorative motion needs a justified usage scene and an appropriate pause/reduced-motion strategy.

## Runtime candidate

Try Paper `Warp` before introducing a fluid simulator. The [Warp controls](https://shaders.paper.design/warp) support edge patterns and configurable distortion. These are exploratory settings to tune at the actual composer aspect ratio, not a verified drop-in preset:

```json
{
  "colors": ["#171717", "#D6BBA6", "#A6C4B3", "#BCAFCE"],
  "shape": "edge",
  "proportion": 0.3,
  "softness": 0.9,
  "distortion": 0.15,
  "swirl": 0.25,
  "swirlIterations": 3,
  "speed": 0.12,
  "minPixelRatio": 1,
  "maxPixelCount": 180000
}
```

In an implementation, idle/reduced-motion policy overrides `speed` to zero or skips the shader. The pixel budget is a prototype starting limit for a small blurred surface, not a guarantee of phone performance. Use a stable CSS fallback under the enhancement, and keep it available when loading or initialization fails.

If the folds compete with text, first reduce their visible area or contrast; switching to `MeshGradient` is the softer alternative. Avoid solving every issue by increasing blur, which can erase the liquid structure while retaining its rendering cost.

## Compare against the brief

| Direction | Character | Tradeoff |
| --- | --- | --- |
| Smoked pearl + low-strength Warp | Liquid folds, restrained color, neutral frame | Needs careful edge masking and real-size tuning |
| Soft aurora / MeshGradient | Airy light and a quieter atmosphere | Less obviously liquid or refractive |
| Polished metal / strong fluid simulation | More dramatic depth and movement | More distracting in a reading/transfer tool; reserve for an explicit expressive brief |

Do not add a fake operating-system window or wallpaper to demonstrate the glass. The browser application is the surface.
