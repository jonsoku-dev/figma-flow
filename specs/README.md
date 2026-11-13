# Feature specifications

These feature folders register versioned requirements and acceptance relationships in the repository’s existing evidence graph format. Each folder contains a concise source excerpt, human requirements, a canonical `graph.json`, and a screen/action prose projection keyed by graph IDs. The graph is per feature/run and remains the only relationship inventory.

| Feature | Requirements | Acceptance criteria | Status boundary |
| --- | --- | --- | --- |
| [Graph review surfaces](graph-review/spec.md) | Planner, designer and developer review from one source | Design, FigJam, Slides and API evidence | Actual sample and limits in linked graph |
| [Readable Specifications](readable-specifications/spec.md) | `REQ-SPEC-01`–`REQ-SPEC-05` | `AC-SPEC-01`–`AC-SPEC-07` | Existing-page 16-target migration plus three new apps and a focused copy cover 636 connected targets; unrelated user-note and gated Dev Mode click cases remain unverified. |
| [Pre-Figma Quality Review](pre-figma-quality/spec.md) | `REQ-QUALITY-01`–`REQ-QUALITY-05` | `AC-QUALITY-01`–`AC-QUALITY-06` | Three controlled fixture apps passed source/native geometry checks; utility warnings were reviewed and aesthetic production approval remains separate. |
| [Workspace Activity](workspace-activity/spec.md) | `REQ-ACTIVITY-01`–`REQ-ACTIVITY-04` | `AC-ACTIVITY-01`–`AC-ACTIVITY-06` | Current-revision distribution and execution-linked history; automated checks, actual browser and installed-native observations have separate scope. |
| [Startup Freshness and Safe Update](startup-freshness/spec.md) | `REQ-UPDATE-01`–`REQ-UPDATE-06` | `AC-UPDATE-01`–`AC-UPDATE-08` | Loaded-runtime identity and explicit revision-checked retirement are covered separately from package installation/update/recovery. See executed verification. |

The graphs follow the repository’s [evidence graph contract](../skills/figma-flow/references/graph-contract.md). The supplied request is the source for observed requirement nodes. No implementation, local test, browser, or Figma result is asserted by registration alone.

Actual source/test scope and remaining native limits: [verification](verification.md). Feature acceptance statuses are not promoted by mock checks.

## Test execution plans

[Multi-page app and input regression program](regression-program/plan.md) defines three new apps, input combinations, real web/Figma checks and the defect-fix-retest procedure. Its [case inventory](regression-program/cases.json) records planned coverage and scoped execution witnesses. Complete-case status stays unverified until all applicable requirements are met; owner-local receipts are not shipped proof for a new fork. It is not a product relationship graph.

## Proposed development

[Development roadmap](../docs/development-roadmap/README.md) contains separate functional, design and Cursor task documents for eight proposed features, optimizations and architecture changes. They are not implemented feature registrations or evidence of acceptance.
