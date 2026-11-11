# Implementation verification · 2026-11-11

## Source and scope

Source checkout: `feat/readable-graph-specs`, based on `f64d9a9e592343a0910cec236d358cd841b8e207`, origin `https://github.com/jonsoku-dev/figma-flow.git`. Work is uncommitted and unreleased. The handoff's corporate installation/SHA is historical evidence from another installation, not this checkout's authority. Existing package version, stable plugin ID and registered manifest path are preserved.

The initial no-Figma instruction was later superseded by explicit user authorization for actual testing. Follow-up used the existing registered Figma Flow plugin, authenticated local-control receipts, Desktop observation and an independent read-only web viewer. Official Figma MCP, global Codex package replacement, release, merge and deployment were not used.

## Requirements and graph authority

| Feature | Requirements / acceptance | Relationship graph and specification |
| --- | --- | --- |
| [Readable specifications](readable-specifications/spec.md) | REQ-SPEC-01–05 / AC-SPEC-01–07 | [graph](readable-specifications/graph.json), [screen/action spec](readable-specifications/screen-spec.md) |
| [Pre-Figma quality](pre-figma-quality/spec.md) | REQ-QUALITY-01–05 / AC-QUALITY-01–06 | [graph](pre-figma-quality/graph.json), [screen/action spec](pre-figma-quality/screen-spec.md) |
| [Startup freshness](startup-freshness/spec.md) | REQ-UPDATE-01–05 / AC-UPDATE-01–07 | [graph](startup-freshness/graph.json), [screen/action spec](startup-freshness/screen-spec.md) |

Graph relationships remain canonical. Fact-specific external sources carry their location/version. Acceptance statuses remain unverified for broader native, user-note or visual cases not exercised here; a graph registration or fixture pass does not close them.

## Connected human specifications

[The compiler](../tools/specification_contract.py) projects graph meaning into concise native summaries and labeled full sections: purpose, conditions, behavior, result, recovery, journey and Figma/web scope, only where supported by source. `summary`, `platform_scope` and the brief's `specification_locale` are graph-owned. Additive `connected-spec-v2` presentation keeps the existing v1 schemas and legacy inputs.

Actual screen/control nodes retain short human Markdown annotations linked to the exact full-spec TEXT. The outside-artwork Design board links back to the exact target. Technical prefixes/hashes, exact indexed legacy objects and ownership remain private metadata; unrelated user annotations are preserved. [Planning/verification](../tools/specifications.py) recompiles current graph bytes and checks actual annotations, exact board/text IDs, both links, meaning hash and source revision. Duplicate Markdown with a different category also fails. No metadata value is fabricated as an actual native annotation.

[Annotation authoring](../figma-bridge/native_annotations.js), [board layout](../figma-bridge/design_note_board.js), [updates](../figma-bridge/native_specifications.js), [native readback](../figma-bridge/native_semantic_read.js) and [native-edit](../tools/native_edit.py) preserve IDs and check before-state across awaits. Rich board expansion reflows only the owned board when needed; conditional rollback preserves concurrent edits. [General import](../tools/figma_bridge.py), [review/selected production](../tools/figma_draft.py), [annotation validation](../tools/annotation_contract.py) and [handoff](../tools/native_handoff.py) consume the same contract. Actual getter variable-font settings and instance override lists remain observations.

The earlier metadata-only solution removed human native annotations as well as technical callouts. This follow-up restores the human connection and replaces generic repeated notes with source-backed detail. The private local `outputs/figma-flow-connected-specs/verification.md` records exact product graph hashes, targets, receipts, screenshots and readbacks. Personal paths/account IDs stay outside the shared guide.

## Other implemented paths

Direct/compare routing, managed instruction/selection authority and artifact-linked critique retain their existing gates. Comparison requires current visible material and a real post-presentation choice; a concrete direct request uses one draft. Symlink/concurrent receipt replacement and revoked authority are rejected. The explicit-mode regression executes actual compilation/preparation with synthetic sources, not native or aesthetic acceptance.

Startup checks exact registered package/source and safely updates eligible installations with independent recovery snapshots. Pins, active work, unknown source and offline/auth failures remain explicit exceptions. Native writes require current loaded runtime identity. Package installation/recovery tests use modeled hosts; a real global package replacement was not performed. User instructions remain in the [integrated guide](../docs/guide.md).

## Final source checks

Python 3.13.3 and repository-pinned Node 26.13.0 were used. The temporary Node archive checksum was verified against [official checksums](https://nodejs.org/dist/v26.13.0/SHASUMS256.txt); the global installation was unchanged.

- Python: 960 tests, 958 passed, 2 skipped, exit 0.
- Node: 188 tests, 187 passed, 1 skipped, exit 0.
- Demo: 2 passed. Bundled dependency check, generated workflow and all three feature graph validators exited 0.
- All 8 planned commands passed. 276 source/test/configuration files were fingerprinted before and after; none changed. Fingerprint: `bc8d6706d29199218cc4d7620ed0e550143ffd339922a59529f448c8b8bddeee`.
- Final logs and exact command/exit records: private local `outputs/figma-flow-connected-specs/final-current-code-audit`. Documentation reconciliation checked 138 local links with none broken; `git diff --check` exited 0.

Skipped fixtures: external Shadow Troupe calibration layout, optional operator-supplied live readback fixture (“Optional operator evidence not supplied”), and external saved initial Moss tint packet. These skips are not passes or a prohibition on the separate authorized native run.

Independent read-only review found a duplicate-canonical-Markdown gap; the reader/checker and negative regression were corrected. Other admission, source-update recovery, legacy ownership and board-identity findings were resolved and retested. A temporary binding-restoration experiment was removed from the final source after delayed actual getters contradicted immediate success.

## Actual Figma evidence and limits

Sixteen existing map/list × desktop/mobile screen/action targets passed the normal graph specification validators with actual native annotations and reciprocal links. A fresh final-source repeat changed zero objects; all 1,126 IDs and previously exported fields, variables/collections, source marker and legacy archives were preserved. Added actual override data matched independent post-recovery reads. Desktop and anonymous cloud screenshots show structured readable content; the earlier native verification folder retains graph-change/stale rejection and overlap rollback evidence.

During Desktop inspection the root changed one button's alignment. Immediate setter receipts were insufficient: subsequent reads reverted. Figma Undo reversed only the root's test operations and restored original inherited alignment/gap binding. Delayed reads and the final-source no-op repeat matched the post-description baseline. No reset-all-overrides operation or design recreation was used.

The current Free account gated Dev Mode behind an upgrade, so native annotation-link click-through was not observed. Normal Design board content was observed, and both link directions were verified as actual getter data. No upgrade was made. The public [Annotation API](https://developers.figma.com/docs/plugins/api/Annotation/) supports Markdown; no supported global View → Annotations visibility control was found. The plugin does not promise automatic global hiding.

No new candidate page, real unowned user-note case, new prototype click-through, complete reaction-payload preservation proof, new aesthetic direction or real global Codex package update is claimed. Runtime identity/receipts are authenticated plugin self-report, not independent cryptographic origin attestation.
