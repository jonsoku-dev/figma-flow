# Screen and action specification — Startup Freshness

This file is a human-readable projection of [graph.json](graph.json); stable IDs and relationships remain canonical there.

## `SCR-UPDATE-01` — Plugin workflow startup check

- **Requirements:** REQ-UPDATE-01–REQ-UPDATE-05
- **Purpose:** Establish whether the selected plugin package and Figma runtime sources are safe and current before a workflow starts.
- **Journey:** Workflow entry → local source/identity/runtime check → safe ensure or explicit exception.
- **First action:** Run the startup `check`; run `ensure` only when the check proves the selected source and target safe.
- **Behavior:** Resolve exact plugin identity and registered authority, preserve private workspace state, replay the pinned startup inputs, and require fresh authenticated loaded-runtime information for native writes.
- **Precondition:** Exact source and workspace are known; Figma access mode is declared. Unknown or forbidden inputs take the exception path.
- **Result:** Either a safe update/current result with pinned inputs, or a named exception/block state. A file/package/server version alone never means Figma loaded that version.
- **Failure:** Keep the current package/runtime unchanged, retain private replay inputs, and report the explicit exception. Reopen the same plugin only if Desktop did not reload it.
- **Action:** `ACT-UPDATE-01` — Check and safely ensure package/runtime freshness
- **Accepted by:** AC-UPDATE-01–AC-UPDATE-07
- **Implementation:** `CODE-UPDATE-01`–`CODE-UPDATE-03` reference [startup check/ensure](../../tools/plugin_startup.py), [workspace identity and replay](../../tools/figma_workspace.py), and [authenticated runtime reporting](../../figma-bridge/workspace_control.js). All remain unverified.
- **Evidence:** `TEST-UPDATE-01`–`TEST-UPDATE-03` reference present local test files; execution is not claimed. Runtime-version coverage uses a mock and is not actual Figma proof. Native Figma access is forbidden; no runtime readback is claimed.
