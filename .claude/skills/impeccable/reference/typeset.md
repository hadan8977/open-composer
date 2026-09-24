Typography carries information, hierarchy, and voice. Improve it inside the established visual world; do not replace the identity unless the user asked to.

---

## Visitor mode

- **Persuade + Experience:** display type may carry the voice. Use decisive contrast and responsive scale when the composition benefits.
- **Operate + Read:** stability, scanability, and measure come first. A single well-tuned family and fixed role scale are often right.
- **Native:** follow [ios.md](ios.md) or [android.md](android.md), including platform scaling and accessibility behavior.

If typography replacement would create a new identity, route through [new-work.md](new-work.md) and update the existing design record. Otherwise preserve confirmed families and improve their use.

## Focused assessment

Follow the [skill map](skill-map.md). Inspect the affected scope yourself; independent agents are not a prerequisite. Select the questions that resolve this task's actual uncertainty.

1. **Typographic assessment:** inspect representative pages and styles. Support the relevant questions with rendered, file, selector, or computed-value evidence:
   - **Authority and fit:** Which faces, weights, and roles are established? Do they fit the product and selected world, or are they unexamined defaults? Is every family necessary?
   - **Hierarchy:** Can heading, body, label, metadata, and data roles be distinguished at a glance? Are adjacent sizes or weights too close to carry different jobs?
   - **Scale and consistency:** Is there a deliberate role scale, or a collection of arbitrary values? Do repeated roles stay identical across screens and states?
   - **Reading:** Does body copy have a comfortable measure for its language, content, and size? Are line height, paragraph rhythm, contrast, and tracking tuned to the actual face, width, language, and surface?
   - **Stress:** What happens with long headings, localization expansion, zoom, narrow containers, missing weights, and font fallback?
   - **Delivery:** Are only used assets loaded? Do fallback metrics, loading strategy, and variable-font settings avoid invisible text and disruptive reflow?
2. **Optional mechanical scan:** use the detector only when it supplies missing evidence or the user requested it. Resolve the launcher from this skill directory (`impeccable.cmd` on Windows):

```bash
<skill-base-dir>/scripts/impeccable detect --json --scope type [target files or dirs]
```

Also inspect dynamic or arbitrary font values the detector cannot interpret. Combine any scan results with the visual assessment before editing. A clean scan does not prove good typography.

## Set the system

Before editing, state:

- the roles the interface needs;
- the intended contrast between those roles;
- the reading measure and density;
- which existing faces and weights are authoritative;
- any performance, localization, or accessibility constraints.

Use the fewest roles and families that make the hierarchy unmistakable. Combine size, weight, space, and tone deliberately instead of asking size alone to do all the work. Role names and tokens should describe purpose rather than values.

## Apply

- Keep body copy comfortably readable and zoomable. Use 1rem / 16px as the ordinary web body floor unless a dense role, platform convention, or user setting justifies otherwise.
- Use roughly 45–75 characters as a starting point for Latin prose, not a universal target. Tune measure and line height to the actual language and text; wider lines often need more leading.
- Compensate light text on dark surfaces on all three perceptual axes: slightly more line height, a touch more tracking, and one step more weight when the face needs it.
- Tune line height to the face, width, language, and contrast, not a universal ratio.
- Keep repeated roles consistent across screens and states.
- Use numeric, tabular, code, and label features when their content benefits.
- Load only used font assets and weights. Provide metric-compatible fallbacks and avoid blocking text.
- Let marketing display type respond to available space when useful; keep dense product and reading surfaces spatially predictable.
- Preserve browser zoom, user font settings, Dynamic Type, and platform text scaling.
- Use paragraph spacing or first-line indentation as the primary paragraph rhythm; combining both usually double-marks the boundary.

Do not make type decorative at the expense of comprehension, or introduce a second family without a clear role it alone can perform.

## Verify

- Primary, secondary, body, and metadata roles are recognizable without reading the copy.
- Long text remains comfortable across relevant widths and languages.
- The typography belongs to the product and its established world.
- Loading does not create disruptive reflow or invisible text.
- Zoom, text scaling, focus, contrast, and reduced viewport paths remain usable.
- If a detector was used, relevant findings are explained or corrected.

Confirm the affected relationships with actual evidence. Repeat a check only after a relevant change or for an unresolved concern; describe untested behavior accurately.

Stop when the requested typography works. Use `polish` only for a remaining refinement within scope.

## Live-mode signature params

Every variant declares a coarse `scale` parameter and authors its type ramp against `var(--p-scale, 1)`.

```json
{"id":"scale","kind":"range","min":0.85,"max":1.3,"step":0.05,"default":1,"label":"Scale"}
```

Add at most one pairing or weight parameter when it represents a real system choice. Follow [live.md](live.md)'s parameter contract.
