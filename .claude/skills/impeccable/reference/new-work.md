# New visual work

Use for a new surface or a substantial redesign. Scale the process to the work; an established component or a precise brief may already settle several stages. The [skill map](skill-map.md) owns routing and conflict resolution.

## 1. Frame the design problem

Read the existing product record, representative screens, real content, relevant constraints, and prior feedback. Establish:

- Who uses this, in what situation, and what they must understand or do.
- The primary task, success criteria, content hierarchy, and important failure or recovery paths.
- The product's distinct character and the evidence, assets, and functionality it actually has.
- The intended deliverable, platforms, accessibility needs, performance budget, and what must remain unchanged.

Separate observed facts, user statements, and working assumptions. A hypothetical persona is not user research. Ask a small set of questions only for gaps that would change the result. When the user delegates decisions, state reasonable assumptions and proceed.

Derive a few concrete design principles that can settle later choices. Prefer "keep the file and its transfer state together" over "make it intuitive."

## 2. Research the task and the visual language

Use two complementary tracks:

- **Interaction references:** comparable tasks, navigation, density, state transitions, recovery, and conventions users already understand.
- **Visual references:** typography, composition, imagery, identity, material, motion, and relevant references beyond software such as editorial design, signage, objects, or the audience's cultural environment.

Start with existing supplied references and available local skills. Browse primary sources when current external examples are needed. Do not install a resource just to inspect it.

Actually view the images or rendered pages. Search summaries, product descriptions, and style names alone do not establish visual research. For each useful reference, note its source, the observed principle, how that principle serves this task, and what should not be copied. Distinguish observed motion from a proposal inferred from a still image.

For an open new direction, assemble a compact, viewable reference board or equivalent side-by-side reference set using available tools. Group by design idea, not just by website. Source references and generated proposals must be labeled separately. If images cannot be inspected, disclose that limit and keep conclusions provisional.

A user's liked reference is evidence of taste, not an instruction to copy every feature. Preserve explicitly pinned attributes; use the rest as material for exploration.

## 3. Explore and choose concepts

Create materially different, feasible directions while the choice is open. Usually two or three clear alternatives communicate the tradeoffs; do not impose a quota on a settled brief or local change.

Each concept connects:

- A thesis tied to this product and audience.
- A primary composition and information sequence.
- A typography, color, imagery, and component language.
- A signature detail or interaction where it adds identity.
- The benefit, tradeoff, and implementation consequence.

Use sketches, wireframes, style studies, or [visual comps](visualize.md) at the fidelity needed to compare the unresolved choices. Keep content and comparison conditions reasonably consistent. Alternatives must differ beyond color and border radius.

Recommend a direction using task clarity, audience fit, visual identity, feasibility, and the user's preferences. Preserve creative ambition: do not turn every direction into a neutral template while checking it. Random prompts or the bundled concept-seed tool may help break a rut when useful; they do not choose the final direction by authority.

Ask for a decision when the user wants to choose or a material uncertainty remains. If the user authorized you to choose, select and explain. Do not repeatedly confirm a decision already made.

## 4. Resolve composition and interaction

Develop the selected concept with real or honestly labeled representative content before polishing surfaces.

Establish the content hierarchy, task path, layout topology, grid, alignment edges, spacing relationships, type roles, image treatment, and control geometry. Give important content appropriate weight; uniform repeated geometry is useful when the information is genuinely comparable.

Consider typography in the actual language and content range. Check line length, line breaks, baseline alignment, labels, long names, and the balance between density and scanning. A narrow screen may need a different arrangement, not just a stack of desktop panels.

Map controls to real actions and states: idle, pending, empty, success, error, interrupted, and recoverable where relevant. Define feedback timing, focus movement, dismissal, disabled behavior, and touch access. Decorative motion never invents progress or delays an action.

Read the [craft floor](craft-floor.md) and only the specialist needed for an open implementation question. Search results propose choices; they do not replace the selected direction or create a second design system.

## 5. Build a reviewable sample, then implement the scope

Render a representative screen or key interaction early enough to judge composition before expanding complex behavior. Use the selected medium honestly: a generated comp tests appearance; an interactive prototype tests behavior.

Translate the concept into semantic, responsive UI. Keep actual text and controls accessible. Preserve factual copy, data ownership, real task state, and existing functionality unless the request changes them. Connect reusable interaction patterns to the application's own state.

Reuse the established product/design record. For a substantial new direction, record the chosen rationale, reference sources, type/color/layout decisions, and meaningful constraints there. Keep one source of truth; do not add parallel token documents. Use a short brief for a small task rather than a new documentation structure.

## 6. Critique, refine, and stop

Use [critique](critique.md) to compare the render and task path against the brief. Inspect relevant wide/narrow layouts, content ranges, state changes, and accessibility preferences. Test performance claims rather than inferring them from appearance.

Record what works as well as defects. Each finding connects a location and observation to the user's goal and a concrete improvement. Separate functional defects, craft gaps, and subjective alternatives. Do not abandon an approved direction because a generic detector flags one of its techniques.

Correct observed issues in a bounded batch, then confirm the affected paths. Stop when the requested scope works, the selected concept is visibly realized, and no known blocking issue remains. Further exploration requires a new unresolved question, not a desire for another pass.

## Method references

- [Design Council: Double Diamond](https://www.designcouncil.org.uk/resources/the-double-diamond/): alternate exploration and convergence; revisit the problem when evidence changes it.
- [NN/g: Design Critiques](https://www.nngroup.com/articles/design-critiques/): ground feedback in shared objectives and scope.
- [Impeccable: Designing](https://impeccable.style/designing/): connect direction, rendered work, and purposeful review.

These sources inform the method; they do not require a fixed artifact count, installation, or a particular visual style.
