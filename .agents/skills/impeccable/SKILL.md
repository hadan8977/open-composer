---
name: impeccable
description: Lead interface design from product goals and visual-reference research through distinct concepts, composition, interaction, implementation, and evidence-based critique. Use for new interfaces, substantial redesigns, UX planning, or design reviews; scale down to the affected component for local refinements. Coordinate specialist skills when needed. Not for backend-only work or standalone prose editing.
metadata:
  version: 4.3.1
  local_profile: integrated-design
---

# Impeccable

Own the design process and its outcome: a recognizable visual language, deliberate composition, clear information, and usable interaction grounded in this product.

Use the [local skill map](reference/skill-map.md) to select supporting skills and resolve conflicts. This is the lead for broad UI work, not an instruction to run every command or specialist.

## Start at the requested scope

Read the relevant product context, existing design decisions, target code, assets, and available renders. Reuse facts already in the conversation. A missing PRODUCT.md or DESIGN.md does not erase context that exists elsewhere or block a local edit.

- **New surface or substantial redesign:** [new-work](reference/new-work.md).
- **Planning without implementation:** [shape](reference/shape.md).
- **Review without changes:** [critique](reference/critique.md).
- **Focused refinement:** preserve the established identity, inspect the affected relationships, and use the relevant command below.
- **A named tool workflow:** read its reference and follow its technical requirements within the user's scope.

Before UI edits, read the [craft floor](reference/craft-floor.md). Use the actual rendered target when available. Existing screenshots are useful only after checking their target and freshness against current code.

## Design principles

- Start with the intended user's task, context, and desired outcome. Distinguish evidence from assumptions.
- Study actual visual references, explain what makes them work, and transform those principles into an original direction.
- Let alternatives differ in composition, information structure, typography, imagery, or interaction. A palette swap alone is not a new concept.
- Choose the direction using product fit, usability, identity, and feasibility. Make a recommendation when the user delegates judgment.
- Set hierarchy and geometry before effects. A restrained interface still needs character; expressive work still needs legibility and usable controls.
- Review against the brief and the observed result. Preserve strong choices, fix concrete defects, and stop when the requested outcome and relevant checks are satisfied.

## Visitor modes

Choose per surface rather than per product:

- **Persuade:** understand an offer and decide; landing pages, campaigns, pricing.
- **Operate:** complete a task; workspaces, editors, dashboards, settings.
- **Read:** understand information; documentation, articles, guides.
- **Experience:** explore the work itself; portfolios, galleries, showcases.

Modes change emphasis, not permission to use a fixed palette or layout. The same product can have several modes.

## Commands

| Command | Category | Description | Reference |
|---|---|---|---|
| `craft [feature]` | Build | Deprecated alias for an ordinary new-work request | [reference/craft.md](reference/craft.md) |
| `shape [feature]` | Build | Plan UX/UI before writing code | [reference/shape.md](reference/shape.md) |
| `init` | Build | Capture durable product context in PRODUCT.md | [reference/init.md](reference/init.md) |
| `document` | Build | Generate DESIGN.md from existing project code | [reference/document.md](reference/document.md) |
| `extract [target]` | Build | Pull reusable tokens and components into design system | [reference/extract.md](reference/extract.md) |
| `critique [target]` | Evaluate | Goal-led design review with observable evidence | [reference/critique.md](reference/critique.md) |
| `audit [target]` | Evaluate | Technical quality checks (a11y, perf, responsive) | [reference/audit.md](reference/audit.md) · native: [reference/audit.native.md](reference/audit.native.md) |
| `polish [target]` | Refine | Final quality pass before shipping | [reference/polish.md](reference/polish.md) |
| `bolder [target]` | Refine | Amplify safe or bland designs | [reference/bolder.md](reference/bolder.md) |
| `quieter [target]` | Refine | Tone down aggressive or overstimulating designs | [reference/quieter.md](reference/quieter.md) |
| `distill [target]` | Refine | Strip to essence, remove complexity | [reference/distill.md](reference/distill.md) |
| `harden [target]` | Refine | Production-ready: errors, i18n, edge cases | [reference/harden.md](reference/harden.md) |
| `onboard [target]` | Refine | Design first-run flows, empty states, activation | [reference/onboard.md](reference/onboard.md) |
| `animate [target]` | Enhance | Add purposeful animations and motion | [reference/animate.md](reference/animate.md) |
| `colorize [target]` | Enhance | Add strategic color to monochromatic UIs | [reference/colorize.md](reference/colorize.md) |
| `typeset [target]` | Enhance | Improve typography hierarchy and fonts | [reference/typeset.md](reference/typeset.md) |
| `layout [target]` | Enhance | Fix spacing, rhythm, and visual hierarchy | [reference/layout.md](reference/layout.md) |
| `delight [target]` | Enhance | Add personality and memorable touches | [reference/delight.md](reference/delight.md) |
| `overdrive [target]` | Enhance | Push past conventional limits | [reference/overdrive.md](reference/overdrive.md) |
| `clarify [target]` | Fix | Improve UX copy, labels, and error messages | [reference/clarify.md](reference/clarify.md) |
| `adapt [target]` | Fix | Adapt for different devices and screen sizes | [reference/adapt.md](reference/adapt.md) · native: [reference/adapt.native.md](reference/adapt.native.md) |
| `optimize [target]` | Fix | Diagnose and fix UI performance | [reference/optimize.md](reference/optimize.md) |
| `live` | Iterate | Visual variant mode: pick elements in the browser, iterate on alternatives | [reference/live.md](reference/live.md) |
| `generate [n] [action] [element]` | Iterate | Variants, versions, or alternatives of a named element to choose from in the live browser; no manual picking | [reference/generate.md](reference/generate.md) |

## Routing and tools

A clear request selects its command without an extra menu. With no task or target, ask one useful question. Workflow questions use the map above and the smallest applicable playbook.

The bundled launcher is optional for ordinary discovery and manual design review. For live iteration, detector output, artifact management, or other requested CLI capabilities, resolve scripts from this skill directory and read the matching tool reference. On Windows use `scripts/impeccable.cmd`. If the engine needs downloading, treat that as an installation decision rather than silently bootstrapping during a review.

When using the context command, run it once per session with the project cwd and the relevant target. If unavailable, read project context directly and report only the evidence that is missing. An unavailable launcher alone does not prevent planning, implementation, or visual inspection through other available tools.

Random concept seeds and image-first mockups are optional exploration methods. User-selected references or a delegated design choice do not require a second approval ceremony. Use [visualize](reference/visualize.md) when a comp or asset will resolve a visual question.

`init` records missing durable context when requested. `document` records an established system. `doctor`, hooks, and pin/unpin remain explicit maintenance operations; consult their bundled references before changing their state. Do not repair installation drift during an unrelated design task.

## Finish

Inspect the relevant composition and task path, correct observed defects together, and confirm the affected paths. Stop polishing once the brief is met and no known blocking issue remains. Report the design decision, meaningful changes, validation, and actual limits. Planning and review do not claim implementation.
