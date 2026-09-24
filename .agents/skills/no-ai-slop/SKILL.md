---
name: no-ai-slop
description: Edit a prose draft for clarity while preserving its facts, uncertainty, and personal voice, or identify formulaic writing without rewriting. The default local prose editor; use stop-slop for a short cleanup, avoid-ai-writing for its explicitly requested detailed rulebook, and slop-cop for requested grades or tickets. Does not determine AI authorship.
---

# No AI Slop

Make the minimum effective edit. Distinctive writing should still sound like the same person afterwards. Follow the [local skill map](../impeccable/reference/skill-map.md); do not run multiple prose editors over the same passage by default.

## Scope and mode

- **Edit:** revise the supplied draft or the file the user asked to change.
- **Detect:** identify observable problems with a short excerpt, its effect, and a concrete improvement. Keep the source unchanged. Do not score it or infer who wrote it.
- If the draft is already clear, preserve it and say so briefly.

Use the audience, format, and goal already present in the conversation or source. Ask only for missing information that materially changes the edit; bundle those questions. If there is no draft or identifiable target, request it.

For UI copy, inherit the product's terminology, user task, and design direction. This skill edits language; broader interface decisions belong to [impeccable](../impeccable/SKILL.md).

## Preserve meaning and voice

- Keep facts, names, numbers, units, attribution, negation, conditions, causal relationships, and degree of certainty. Never turn “most” into “all” or remove a hedge that expresses a real limit.
- Protect quotations, code, identifiers, URLs, and required technical or legal language unless the user specifically asks to edit those regions.
- Do not invent statistics, experiences, examples, sources, or opinions to make an abstract sentence concrete. Use supporting detail already available; otherwise flag the gap or keep the accurate general statement.
- Notice vocabulary, cadence, humor, bluntness, uncertainty, and deliberate roughness. Keep these traits unless a tone change is requested.
- Preserve the argument and structure unless they obstruct the reader or the user requested a structural edit. A distinctive sentence does not need changing merely for consistency.

## Improve clarity

1. Lead with what the reader needs when the setup adds nothing. Keep stories, asides, and background that supply useful context or character.
2. Prefer direct verbs and precise words. “Made a decision” can become “decided”; accurate domain terminology should remain.
3. Name an actor when responsibility matters and the source identifies one. Passive voice and inanimate subjects are valid when they describe the situation more accurately: “The file was deleted” or “The token expires automatically.”
4. Remove repetition and empty qualifiers. Keep “I think,” “usually,” or “may” when they express voice, evidence limits, or uncertainty.
5. Untangle difficult sentences without forcing every paragraph into the same short rhythm. Fragments, long sentences, questions, and lists can serve the writer's purpose.
6. Use formatting for navigation and comparison. Do not impose punctuation, sentence-length, paragraph-length, or list-size quotas.

## Patterns worth checking

These are candidates, not forbidden words or structures. Flag the effect in this passage; do not count matches as proof of a defect.

| Candidate | Check | Useful edit |
| --- | --- | --- |
| Throat-clearing: “Here's the thing,” “it's worth noting” | Does it delay the point or carry recognizable voice? | Cut an empty setup; keep useful context. |
| Inflated claims: “transformative,” “game changer,” “robust” | Is the claim supported or the term technically precise? | Use the supported result or a more accurate claim. |
| Abstract praise: “plays a vital role,” “highlights our commitment” | Does it explain anything beyond importance? | State the available action, consequence, or mechanism. |
| Unsupported authority: “experts agree,” “research shows” | Is a relevant source supplied? | Preserve attribution, request support, or flag the unsupported claim. |
| Repeated contrasts, rhetorical questions, or colon reveals | Are they doing useful rhetorical work or scaffolding every paragraph? | Vary or remove the repeated frame while keeping the distinction. |
| Synonym cycling | Do changing terms obscure a stable concept? | Repeat the correct term. |
| Fragment stacks, punchlines, or repeated paragraph shapes | Does the cadence fit the writer and genre? | Repair monotonous scaffolding without flattening intentional rhythm. |
| Recaps and “deep” endings | Do they add closure, a useful takeaway, or only repeat? | End where the content has done its job. |
| Dense dashes, bold, headings, or bullets | Do they help the reader follow the content? | Reduce distracting density; retain useful structure. |

Words such as “leverage,” “facilitate,” “quietly,” and “actually” deserve the same context check. Technical meanings, literal descriptions, quotations, and deliberate voice survive. A request for a specific house style can impose narrower mechanics within editable prose.

## Finish

Read the whole target, make the authorized edit, then use [eval.md](eval.md) for a brief fidelity and clarity check. Correct any concrete regression before returning the result; stop when no justified change remains.

Return the edited text in the requested format. Add a short explanation only when requested or when a material structural choice or unresolved factual gap needs explanation. For detect mode, return findings only. Do not create a scorecard, report file, or extra editing pass by default.
