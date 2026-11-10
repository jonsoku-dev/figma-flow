# Run record

Keep a small record in the user's chosen run directory. This is an agent-maintained record, not an automatic state machine. Update it after a meaningful phase transition and before stopping; do not put credentials or private content in shared metadata. Paths or links in examples below are placeholders.

```yaml
run_id: short-stable-run-id
objective: requested-outcome
scope: [brief, screen_spec, frontend] # local-only example
ssot_scope: local-only # full when Figma is included
source:
  location: brief.md
  version_or_hash: sha256-or-source-version
figma:
  file_url: accessible-file-link-or-null
  version_or_snapshot: observed-version-or-unknown
  nodes: [] # semantic ID, file key, node ID, role
artifacts:
  graph: run/graph.json
  screen_spec: run/screen-spec.md
  repository: local-project-or-null
  bindings: run/bindings.json
  manifest: run/manifest-001.json
  previous_manifest: null
authorities: # fact-level choices; bindings contain coarse source locators
  - fact: add.validation
    affected_ids: [REQ-001, ACT-001]
    source: brief.md#add
    version_or_hash: observed-source-version
    value: specified-value
    basis: specified # specified, inferred, unknown
evidence: [] # id, affected IDs, source/version, captured_at, scope, result, freshness
conflicts: [] # fact, affected IDs, competing values/sources, resolver, status, decision evidence
phases:
  brief: {status: pending, evidence: [], blockers: []}
  screen_spec: {status: pending, evidence: [], blockers: []}
  wireframe: {status: pending, evidence: [], blockers: []}
  design: {status: pending, evidence: [], blockers: []}
  notes: {status: pending, evidence: [], blockers: []}
  prototype: {status: pending, evidence: [], blockers: []}
  extraction: {status: pending, evidence: [], blockers: []}
  frontend: {status: pending, evidence: [], blockers: []}
unknowns: []
next_step: first-eligible-action
```

Use `pending`, `in_progress`, `blocked`, `verified`, `failed`, or `not_requested` for phases. `verified` applies only to the specific phase and evidence described in [figma-workflow.md](figma-workflow.md), not overall product acceptance. Track evidence freshness separately as `current`, `stale`, or `unknown`, scoped to its pinned inputs. Record error category, affected IDs, last successful read/write and safe retry conditions. For an uncertain write, reconcile current Figma nodes and graph identity before retrying; do not create duplicates. If source or target changed, mark affected evidence `stale`, set dependent phases to `pending` or `blocked`, and rerun affected checks. A record is a reminder to verify current state, not proof of it.

For unavailable Figma access, the blocker must include the observed failure, affected file/node/semantic IDs, dependent phases, and the concrete resume condition (for example, an authorized tool read succeeding after quota resets). Record the unavailable tool/operation without inventing a file URL or node ID. Preserve any prior Figma evidence as historical, with its capture time. Local graph validation or an example app can finish independently; keep Figma creation/extraction/parity phases blocked until their own evidence exists.

At each handoff, list changed authorities, stale IDs and propagation candidates, unresolved conflicts, validation results, and the first runnable next action. Include the actual interpreter, working directory, command/flow, result and evidence path for executed checks. Report structure validation, local content freshness, actual Figma reads/playback and browser/runtime validation separately. A snapshot or source file is not a passed runtime check.

For a local-only run, set Figma phases to `not_requested` rather than `blocked`. Record the strict-local validator and local-only snapshot/check independently from actual tests and browser evidence. Include every relevant local source/spec/evidence file in bindings; an unregistered file is outside freshness coverage.

For a reviewed resume, retain the old manifest and check JSON, new check's `review_target_sha256`/`review_affected_ids`, review JSON, its local evidence file and new manifest. Record what was rerun and the exact remaining assumptions. Changes after review require another check and review of the new target state.
