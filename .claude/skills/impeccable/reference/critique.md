# Design critique

Evaluate whether the requested surface achieves its goals with a coherent identity and usable interaction. Use the [skill map](skill-map.md) for scope and supporting skills. Review is read-only unless the user asked for fixes.

## Establish the basis

Read the brief, important user tasks, selected references, relevant implementation, and any existing feedback. Use the smallest representative scope. Clarify a missing goal only when different answers would materially change the assessment.

Preserve the approved direction while judging its execution. For a redesign proposal, distinguish findings about the present design from proposed replacement directions.

## Inspect evidence

View the real interface when available and exercise its main task and relevant states. Inspect the assembled page, not only isolated controls. Select device sizes and themes based on the actual request and risk.

When the app cannot run, use existing screenshots after checking target and freshness, then inspect code. Mark which observations are visible, code-supported, or unverified. Do not claim that a control was clicked or that a current build passed from a static image or old result.

Use existing tests, browser tooling, or the detector when they resolve a concrete uncertainty. A detector match is a candidate observation requiring context, not a design verdict. A numeric score, overlay server, independent agent, or archived report is optional unless explicitly requested.

## Assess the design

| Lens | Questions |
| --- | --- |
| Goal and identity | Does this serve the intended task and audience? Do the form and details belong to this product? |
| Information and hierarchy | Can someone find the primary action, read the sequence, and compare related content? |
| Composition and typography | Are alignment, scale, spacing, rhythm, line breaks, density, and imagery deliberate and coherent? |
| Interaction | Are actions discoverable, states honest, feedback timely, and mistakes recoverable? |
| Accessibility and adaptation | Do keyboard use, focus, touch, contrast, content ranges, and the relevant narrow layout work? |
| Motion and performance | Does motion explain state or support the concept? Is the interface responsive under actual interaction? |

For complex task UI, consult familiar usability heuristics as diagnostic questions: system status, users' language, control and undo, consistency, error prevention, recognition, efficiency, relevant information, error recovery, and help. Do not turn choice counts or a preferred aesthetic into universal limits.

Expert walkthroughs with plausible user scenarios are useful; label them as simulations, not real-user testing.

## Report actionable findings

First note the successful choices worth preserving. Then report the most consequential issues, merging duplicate causes:

- **Where and what:** the element, state, and observed problem.
- **Why it matters:** the affected task, design objective, or accessibility need.
- **Evidence and confidence:** visible behavior, screenshot, source, measurement, or a stated assumption.
- **Change:** the smallest complete correction consistent with the direction.

Distinguish blocking functionality/access issues, substantial hierarchy or interaction problems, local craft gaps, and optional aesthetic alternatives. A normal font, rounded control, grid, gradient, or conventional layout alone is not an issue.

Do not invent a fixed number of findings. A clean review is a valid result. If scoring was requested, state the rubric and evidence, mark unobserved dimensions unassessed, and avoid presenting subjective scores as measured usability.

## Fix and finish

When fixes are authorized, address the relevant causes together and confirm the affected paths. Preserve successful design decisions. Further review needs a remaining question or new evidence; do not run a loop to maximize a score.

Return findings, important strengths, evidence and limitations, and changes only if actually made. Save a report only when requested or already part of the project's workflow. Do not require a question or new approval after a completed review.
