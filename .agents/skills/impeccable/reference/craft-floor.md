# Craft floor

Inspect these relationships in the requested scope. The brief determines the visual language; this reference checks whether that language is executed well. Use [antislop](../../antislop/SKILL.md) only when a choice needs the purpose test.

## Composition before effects

- Establish container and column relationships. Align titles, toolbars, rows, and reading insets deliberately rather than assigning unrelated margins.
- Define type roles, scale, line height, measure, and emphasis using the real language and content. Check short labels, long names, and wrapping.
- Use spacing to express grouping: related items closer, separate groups farther apart. Vary rhythm when the content warrants it.
- Align control heights, padding, icon weight, and baselines. Preserve usable touch targets and keyboard focus when removing wrappers.
- Build the narrow layout around the task. Reflow groups, simplify navigation, and contain local scrolling rather than squeezing every control.
- Keep the intended focal point legible. Rich visual expression belongs where it supports identity or the task; repeated effects should not compete with content.

For a local refinement, preserve the established system and inspect only the affected relationships. An attractive isolated component can become heavy when repeated.

## Functional and perceptual checks

- Check normal text against its actual composite background; use WCAG AA contrast criteria, including the applicable large-text definition. A color name or a token value alone does not prove contrast over moving material.
- Expose meaningful empty, pending, error, success, and recovery states. Completion follows the real operation.
- Verify accessible names, keyboard operation, logical focus, and visible focus treatment. Keep touch actions available without hover.
- Use motion to clarify transition or support the concept. Keep state changes responsive, provide reduced-motion behavior, and measure expensive effects when performance is uncertain.
- Make controls describe their real action; make errors identify a useful recovery. Preserve product facts and the writer's intended tone.
- Check real content ranges and the relevant themes and viewport sizes. Avoid implying all-device coverage from one browser or emulator.

## Contextual style decisions

Typography, radius, color, gradients, borders, shadows, cards, eyebrows, illustration, and motion have no global aesthetic ban here. A single font can form a strong type system; repeated cards can make comparable records easier to scan; an eyebrow can carry meaningful category context.

Ask whether the technique supports hierarchy, identity, navigation, state, or the user's explicit art direction. Refine or remove it when it introduces noise, ambiguity, repetition without purpose, or a demonstrated usability problem.

Use the existing design system for refinements. For new work, derive the system from the selected references and content. Never replace one stock aesthetic with another merely to avoid a familiar font or color.

## Evidence and stopping

Inspect rendered pixels and actual interaction where available. CSS values, code inspection, detector scores, and passing unit tests answer different questions; none alone proves visual quality.

Combine related observations in one review pass, correct concrete defects, and confirm the changed paths. Stop when the requested outcome is met. A source-only review states its limits rather than inventing a visual pass.
