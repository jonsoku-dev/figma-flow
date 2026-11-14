# Feature specifications

[제품 헌법](../CONSTITUTION.md) · [Figma Design 전용 설계 및 인수 계약](design-specialization/spec.md)

These feature folders register versioned requirements and acceptance relationships in the repository’s existing evidence graph format. Each folder contains a concise source excerpt, human requirements, a canonical `graph.json`, and a screen/action prose projection keyed by graph IDs. The graph is per feature/run and remains the only relationship inventory.

| Feature | Requirements | Acceptance criteria | Status boundary |
| --- | --- | --- | --- |
| [Design native inspection](../docs/design-runtime-verification.md) | Scoped Design operations, CSS and canvas fidelity | Real browser, Figma and independent cloud evidence | [Runtime observations](design-inspection/service-observations.json) |
| [Responsive route imports](responsive-web/graph.json) | Each route and measured viewport | Editable native frames, CSS/media fidelity and ranked API observations | [54 real screen comparisons](../docs/responsive-web-verification.md) |
| [Editable web screens](editable-web/graph.json) | Browser observation, graph-bound local assets and native import | Four captured templates, edit preservation and stable reapply | [Browser and Figma acceptance](../docs/editable-web-verification.md) · [0.30 API observations](editable-web/api-observations.json) · [0.31 responsive-web API observations](responsive-web/api-observations.json) |
| [Graph review surfaces](graph-review/spec.md) | Planner, designer and developer review from one source | Design review board and Plugin API evidence | Actual sample and limits in linked graph |
| [Design API observations](design-inspection/scene-observations.json) | Figma Design scene, page, and document receivers | Sanitized exact-member getter and owned-write evidence | Owned fixture receipts: 265 read attempts, 8 restored writes, 79 successful-member edges, 9 deduplicated edges, and 5 attempt-only edges |
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

- [웹 캐러셀의 Design 프로토타입 변환](interactive-web/carousel.md) · [정본 그래프](interactive-web/graph.json)
- [웹 탭 전환의 Design 프로토타입 변환](interactive-web/tabs.md) · [정본 그래프](interactive-web/graph.json)
- [웹 SaaS FAQ 아코디언의 Design 프로토타입 변환](interactive-web/disclosure.md) · [정본 그래프](interactive-web/graph.json)
- [G1 소스 재생성 계약](../docs/STARTER_ROLE_FEATURE_SPEC.md#g1--기존-생성기와-id-보존) · [작은손 실제 빌드 경로](../apps/little-hands/design/README.md) (`v0.34.0` 이후 `main` 통합, `0.35.0` 배포 버전 연결; G0~G5 전체 직군 인수는 별도)
