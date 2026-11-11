# Pre-Figma Quality Review

## Source

See [request.md](request.md) for the task excerpt. Requirements are derived from that request and are marked `observed` in the feature graph as source facts, not implementation proof.

## Requirements

- **REQ-QUALITY-01** — Authoring uses the actual brief/context and applicable design system rather than falling back to a preset genre or canned direction.
- **REQ-QUALITY-02** — Critique is tied to a pinned source/render/preview and gives concrete issue locations plus warning dispositions; it does not invent an aesthetic score.
- **REQ-QUALITY-03** — A single concrete direction or direct user instruction proceeds without requiring A/B alternatives.
- **REQ-QUALITY-04** — Candidate comparison occurs only when the direction remains unresolved or the user explicitly requests comparison.
- **REQ-QUALITY-05** — Direction admission distinguishes an actual user instruction from an invented or synthetic candidate choice.

## Review contract

## Scope and behavior

This feature defines a pre-Figma review of design work authored from its actual brief/context and applicable design system. The review attaches critique to a pinned source/render/preview and records specific locations and warning dispositions. It does not create an aesthetic score.

A concrete direction supplied directly by the user is sufficient to proceed; A/B comparison is only needed when the direction is unresolved or the user asks for it. Admission records the actual user instruction and must not infer approval from generated candidates or a synthetic selection.

## Acceptance status

Acceptance criteria below are derived from the supplied request. This packet contains no generated candidates, design assets, Figma inspection, browser/runtime evidence, or visual-quality certification. Local structural/contrast checks and Pillow demo wiring, if later added, remain separate from visual-quality proof. Native visual acceptance remains **blocked/unverified** under the current restriction.

## Acceptance criteria

- **AC-QUALITY-01** — Show the supplied context and applicable design system as authoring inputs; do not silently substitute a preset direction.
- **AC-QUALITY-02** — Tie each critique item to a location in the pinned source/render/preview and record warning disposition.
- **AC-QUALITY-03** — Do not emit an invented aesthetic score as quality evidence.
- **AC-QUALITY-04** — A concrete direct instruction can proceed without an A/B choice.
- **AC-QUALITY-05** — Only compare candidates when explicitly requested or when direction remains unresolved.
- **AC-QUALITY-06** — Do not treat generated candidates or synthetic selection as actual user direction; structural/contrast checks and demo wiring are not visual-quality certification.

## Evidence boundary

Graph relationships are registered in [graph.json](graph.json). Screen/action prose is keyed by those graph IDs in [screen-spec.md](screen-spec.md). A graph registration or prose excerpt is not evidence that the requested capability has been implemented.

Executed local checks and their visual/native limits are recorded in [text-only verification](../verification.md). They do not certify visual quality.
