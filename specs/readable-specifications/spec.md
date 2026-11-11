# Readable Specifications

## Source

See [request.md](request.md) for the task excerpt. Requirements are derived from that request and are marked `observed` in the feature graph as source facts, not implementation proof.

## Requirements

- **REQ-SPEC-01** — Keep stable graph screen/action meaning canonical and record source authority by fact. Annotations extend existing meaning; they do not replace graph relationships or impose one global authority for every fact.
- **REQ-SPEC-02** — Human-readable purpose, journey, first action, behavior, precondition, result, and failure/limits may be recorded only when supported by the source. Do not invent missing conditions or outcomes.
- **REQ-SPEC-03** — Keep technical prefixes, hashes, target ownership, and verification state separate from human-readable body copy and artwork, with no overlap.
- **REQ-SPEC-04** — Trace each graph specification through display update to actual target readback, pinning graph hash/revision, target identity, and freshness. Stale getters cannot count as current.
- **REQ-SPEC-05** — Preserve semantic IDs, paths, design/user annotations, replay inputs, legacy-prefix identity, idempotent updates, conflict handling, and rollback behavior.

## Scope and behavior

The existing graph remains the canonical relationship inventory for each run. This feature annotates its stable screen and action nodes with readable intent and behavior, then presents that meaning in a specification view. `spec.md` owns requirements and acceptance prose; `graph.json` owns relationships and status; `screen-spec.md` is a projection keyed by graph IDs, not another relationship store.

The annotation fields may describe purpose, journey, first action, behavior, precondition, result, and failure/limits when those facts are present in the source. Omit unsupported or unknown conditions instead of making them up. Preserve technical identifiers and hashes in a separate technical record. Full human body copy carries meaning without requiring those identifiers and remains outside Figma artwork. A concise native annotation stays attached to the actual screen/control and links to its exact full-spec text node. That text links back to the exact target. The graph `summary` and `platform_scope` fields supply source-grounded summaries and medium-specific limits; `specification_locale` follows the actual brief. Full text uses labeled sections rather than a repeated generic paragraph. Legacy compiled v1 documents remain readable; the additive `connected-spec-v2` presentation retains the existing schema, semantic IDs and ownership archives.

A successful update requires a fresh readback from the exact target, pinned to the graph hash/revision and target identity, and evidence that the target still represents the intended meaning. A text-only match, a generated proposal, or a local unit test is not target proof. When the graph behavior changes, update the intended target, preserve unrelated targets, and mark old getters stale until fresh readback. Updates must be repeatable without duplicates; conflicts and rollback outcomes must be explicit.

## Acceptance status

Acceptance criteria below are derived from the supplied request. Implementation and test files are registered in the graph. Executed local tests are recorded in [verification](../verification.md), separately from native acceptance. The initial text-only stage prohibited Figma access. Later user authorization enabled existing-page migration/update across 16 native targets, graph-change freshness checks, repeat no-op, overlap rollback and actual annotation on/off observation. Evidence and limits are recorded in [verification](../verification.md). Global acceptance statuses remain unverified where new-page or unowned-user-note coverage is still absent.

## Acceptance criteria

- **AC-SPEC-01** — Trace requirement through actual screen/action, acceptance, and evidence.
- **AC-SPEC-02** — Keep the full human-readable body outside Figma artwork, with source-backed conditions/results/recovery and a concise native annotation linked to the exact full-spec entry; verify the reciprocal target link.
- **AC-SPEC-03** — On graph behavior change, update and read back the exact target while preserving other targets; mark old getters stale.
- **AC-SPEC-04** — Retain technical/user notes for old and new prefixes.
- **AC-SPEC-05** — Repeated updates add no duplicates; rollback and conflicts are explicit.
- **AC-SPEC-06** — Missing target, wrong target, changed meaning, or stale readback fails or stays unverified.
- **AC-SPEC-07** — Verify annotations both enabled and disabled in the actual UI.

## Evidence boundary

The graph registers the local [specification rendering test](../../tests/test_specification_rendering.py); execution evidence is recorded separately in [verification](../verification.md). Registration alone is not execution proof. Graph relationships are registered in [graph.json](graph.json). Screen/action prose is keyed by those graph IDs in [screen-spec.md](screen-spec.md). A graph registration or prose excerpt is not evidence that the requested capability has been implemented.
