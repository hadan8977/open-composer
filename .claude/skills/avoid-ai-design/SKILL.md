---
name: avoid-ai-design
description: Diagnose and, when requested, revise generic frontend UI choices using the actual brief, rendered evidence, and preserved product behavior. Use for a focused de-slop audit or rewrite of existing UI. For a new design direction or a general UX review, use impeccable as the lead.
license: MIT
metadata:
  compatibility: HTML/CSS/JS and component-based frontend projects; use available browser or screenshot tools for visual evidence.
  author: ungspirit
  version: 0.2.0
  tags: design ui frontend ai-slop tailwind shadcn react
  agentskills_spec: "1.0"
---

# Avoid AI Design

Find choices that became generic through unexamined repetition, then improve them within the product's direction. Follow the [local skill map](../impeccable/reference/skill-map.md).

A source pattern can prove that a technique is present; it cannot prove poor design or AI authorship. Judge the effect in context.

## Modes

- **Detect:** review, audit, scan, explain, or flag requests are read-only.
- **Rewrite:** a request to fix, improve, or de-slop authorizes relevant edits.
- **New direction:** route an open redesign to [impeccable new-work](../impeccable/reference/new-work.md), then use this skill for focused diagnosis.

Reuse the mode and authorization from the conversation. Do not ask for confirmation merely because a skill was loaded.

## Inspect and diagnose

1. Read the actual target, its brief, selected references, nearby tokens, and relevant behavior.
2. Inspect the render when available. Distinguish source-supported facts, visual observations, and unverified inferences.
3. Use [the pattern catalog](references/ai-tells-catalog.md) as questions, not automatic violations.
4. For each finding, connect the repeated or unsupported choice to lost hierarchy, weaker identity, unnecessary cognitive load, poor readability, or an actual task problem.
5. Merge findings with the lead's review. A clean result is valid; do not manufacture a defect to justify rewriting.

Judge severity by impact: blocking function/access, significant hierarchy or interaction failure, local craft gap, or optional preference. The color purple, Inter, a particular library, a centered container, or a familiar layout has no inherent severity.

## Revise at the right depth

For a component or an established design system, make a focused correction using its structure and tokens. Preserve props, state, routing, data flow, accessibility, and factual copy.

For an authorized standalone redesign, resolve the direction first. [Aesthetic directions](references/aesthetic-directions.md) offer vocabulary; they are not a menu every user must choose from. Real references and the product's goals determine the direction. If judgment is delegated, choose and explain.

Do not trade one reflex for another: replacing every sans with a serif, every cool color with beige, or every grid with asymmetry does not establish identity. Make changes reinforce one coherent idea.

## Judge the result

- **Purpose:** the change serves a design objective or task.
- **Coherence:** composition, type, palette, imagery, and interaction support the selected direction.
- **Specificity:** the result belongs to the actual product and content.
- **Usability:** users can find, understand, and operate the relevant controls.

Inspect the changed render and behavior, address concrete defects, and stop. Source inspection alone is reported as such.

In detect mode, return findings and evidence without a rewrite. In rewrite mode, return meaningful changes and validation. Neither mode requires a score, a persistent audit file, or a second approval of an already authorized correction.
