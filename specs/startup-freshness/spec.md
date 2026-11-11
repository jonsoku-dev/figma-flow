# Startup Freshness and Safe Update

## Source

See [request.md](request.md). Requirements are registered as observed source facts; they do not establish implementation or runtime proof.

## Requirements

- **REQ-UPDATE-01** — Check both plugin installations at workflow start
- **REQ-UPDATE-02** — Prove exact plugin source authority
- **REQ-UPDATE-03** — Preserve installation identity and private state
- **REQ-UPDATE-04** — Verify the actual loaded Figma runtime
- **REQ-UPDATE-05** — Replay startup inputs and block uncertain writes
- **REQ-UPDATE-06** — Explicitly retire selected obsolete prepared tasks by exact revision while preserving their artifacts, receipts and recovery metadata.

## Startup contract

At every workflow start, run the local check/ensure path for the Codex package and Figma runtime files. Only update when source authority, workspace, package identity, and applicable runtime freshness are known and verified. Pin/dev/offline/auth/claimed-or-uncertain/unknown-source/access-forbidden states remain explicit exceptions. An installed version that resembles a known release does not prove repository identity.

The local CLI accepts `check` and `ensure` with source, authority, workspace, `--figma-access forbidden|allowed`, and optional pin inputs. Persisted arguments and input pins, including nested source inputs, remain private and replayable. A stale or versionless loaded runtime blocks writes. The actual loaded version must come from authenticated runtime information and include an authenticated generation/digest no older than 15 seconds; filesystem, package, or server version is insufficient. If Desktop did not reload after an update, reopen the same plugin. This does not authorize updating another app, workspace, or plugin.

An accepted result may refresh the liveness timestamp only when its authenticated claim belongs to the same recorded session and current runtime. It never supplies or replaces runtime identity. The 15-second offline expiry remains unchanged.

Changed inputs keep an old prepared task non-executable. When that obsolete task prevents publication of unrelated new work, explicit retirement selects its key and current revision, validates the entire selection, and archives its catalogue metadata before removing it from the active list. Native design, artifacts, generations and receipts remain intact. Retirement neither re-admits stale inputs nor authorizes execution. Claimed work and unresolved uncertain mutations block retirement.

## Acceptance criteria

- **AC-UPDATE-01** — At each workflow start, check and safely ensure both the Codex package and Figma runtime files, unless a recorded exception applies.
- **AC-UPDATE-02** — Keep pin, development, offline, authentication, claimed/uncertain, unknown-source, and forbidden-Figma-access exceptions explicit; do not auto-update through them.
- **AC-UPDATE-03** — Require the exact registered plugin name and Git URI/private provenance; do not infer authority from a public upstream or installed version.
- **AC-UPDATE-04** — Preserve stable manifest/plugin identity, secrets, workspace and pairing state, and unrelated workspaces.
- **AC-UPDATE-05** — Determine the loaded Figma version from authenticated runtime information, with a runtime generation/digest no older than 15 seconds; package/server/filesystem versions alone cannot authorize writes.
- **AC-UPDATE-06** — Provide local `check` and safe `ensure` commands with source, authority, workspace, Figma-access, and pin inputs; `ensure` updates only when identity, provenance, and runtime conditions are verified safe.
- **AC-UPDATE-07** — When Figma access is forbidden, keep native/server/cache/install/deploy state unverified; local checks and mock tests cannot be reported as actual Figma proof.
- **AC-UPDATE-08** — Retire multiple selected stale tasks atomically with exact revision checks; retain their immutable artifacts/receipts and a recovery record; allow remaining valid/new work. Unknown keys, mismatched revisions, active claims, uncertain mutations and corrupted remaining artifacts fail without silently dropping tasks.

## Evidence boundary

The local implementation and test paths are listed in [graph.json](graph.json), but file presence alone does not prove test execution. The initial stage prohibited Figma access. After later authorization, the running development plugin and authenticated local service were observed with matching runtime version/implementation/generation during actual tasks. Package installation/deployment evidence is recorded separately in the tag-scoped Release notes; recovery-failure cases retain their stated source-test scope.

Executed source/native checks and their limits are recorded in [verification](../verification.md). Installation/deployment and recovery results must retain their own evidence; a source test does not substitute for them.
