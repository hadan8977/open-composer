---
name: stop-slop
description: Make a quick, minimal cleanup of short prose by removing empty setup, repetition, and inflated wording while preserving meaning and voice. Use for a light wording pass; use no-ai-slop for longer or voice-sensitive editing. Does not score writing or determine AI authorship.
metadata:
  trigger: Quick cleanup of short prose
  author: Hardik Pandya (https://hvpandya.com)
---

# Stop Slop

A short editing pass, scoped by the [local skill map](../impeccable/reference/skill-map.md). Use one prose editor for a passage. Do not automatically follow this pass with another anti-slop skill.

## Method

1. Identify the intended point, audience, and tone from the supplied context.
2. Remove empty setup, duplicated meaning, and inflated wording when the edit improves clarity.
3. Preserve supplied facts, attribution, quotations, technical terms, conditions, and degree of certainty. Never replace missing evidence with invented specifics.
4. Read the revision for meaning and voice, then return the requested text.

If the user asks to detect or review only, describe the issue and leave the text unchanged. If there is no justified change, preserve it.

## Contextual guidance

- An adverb may be essential: “automatically” describes behavior; “usually” limits a claim.
- Active voice helps when a known actor's responsibility matters. Passive voice and inanimate subjects can describe real behavior accurately.
- Questions, contrasts, fragments, three-item lists, and em dashes are normal writing devices. Repetition or misuse is the issue.
- Directness should not erase uncertainty, courtesy, context, or a writer's distinctive tone.
- Technical vocabulary and deliberate rhetoric are not defects merely because a word appears in generated prose.

Read the relevant reference only when useful:
[phrases](references/phrases.md), [structures](references/structures.md), or [examples](references/examples.md).

For a substantial rewrite or sensitive voice work, use [no-ai-slop](../no-ai-slop/SKILL.md). For a requested numerical grade or humorous ticket, use [slop-cop](../slop-cop/SKILL.md). Do not add scores, explanations, or report files to an ordinary cleanup.

## License

MIT
