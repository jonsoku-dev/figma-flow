# Screen and action specification — Readable Specifications

This file is a human-readable projection of [graph.json](graph.json); graph relationships and stable IDs remain canonical there.

## `SCR-SPEC-01` — Specification display and annotation controls

- **Requirements:** REQ-SPEC-01–REQ-SPEC-05, with ownership relationships recorded in `graph.json`
- **States:** The native specification wrapper records pending, applied or conflict state; a successful update requires a fresh exact-target readback. Scoped existing-page execution is recorded in [verification](../verification.md).
- **Action:** `ACT-SPEC-01` — Update and read back target annotations
- **Accepted by:** AC-SPEC-01, AC-SPEC-02, AC-SPEC-03, AC-SPEC-04, AC-SPEC-05, AC-SPEC-06, AC-SPEC-07
- **Implementation:** `CODE-SPEC-01`–`CODE-SPEC-07` reference [the specification contract](../../tools/specification_contract.py), [graph export/update](../../tools/specifications.py), [native edit boundary](../../tools/native_edit.py), and [Figma annotation and board/readback modules](../../figma-bridge/native_annotations.js), [design-note board](../../figma-bridge/design_note_board.js), [semantic readback](../../figma-bridge/native_semantic_read.js), and [specification display](../../figma-bridge/native_specifications.js). All code nodes remain unverified.
- **Evidence:** `TEST-SPEC-01`–`TEST-SPEC-05` reference existing [contract](../../tests/test_specification_contract.py), [update](../../tests/test_specification_update.py), [readable native spec](../../tests/test_readable_spec_native.cjs), [native update](../../tests/test_native_specification_update.cjs), and [specification rendering](../../tests/test_specification_rendering.py) test files. Execution results are recorded in [verification](../verification.md). Existing-page native checks were later authorized and performed; new-page and real unowned-user-note acceptance remain unverified.

### Action meaning

Compile the current graph, pin the exact native target and owned description entry, update its structured full text and concise attached annotation, then verify fresh getter data and both link directions. A changed before-state is a conflict. Repeating the same input adds no duplicate annotations; rollback preserves concurrent user edits.

### Annotation fields

- **Summary:** Provide a concise source-backed native annotation linking to the full specification.
- **Figma/web scope:** Explain the implemented differences and static or functional limits for each medium.
- **Purpose:** Explain why this screen or action exists, in human-readable body copy.
- **Journey:** Describe the user's place in the flow.
- **First action:** Name the first meaningful action available to the user.
- **Behavior:** State what the action does and what visibly changes.
- **Precondition:** State what must be true before the action is available.
- **Result:** State the intended outcome.
- **Failure:** State the visible failure and recovery path.

These are optional field definitions, not observed product values. Populate only values supported by the actual feature brief, implementation, or fresh target readback. Leave unknown preconditions, outcomes, and failures unknown rather than inventing them. Keep technical IDs, hashes, ownership, and verification state in their separate technical record.
