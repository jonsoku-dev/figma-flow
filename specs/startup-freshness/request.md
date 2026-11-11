# Source request excerpt

> At each plugin workflow start, check and safely update both the Codex package and Figma runtime files, with explicit exceptions for pin/dev/offline/auth/claimed-or-uncertain/unknown-source/access-forbidden states.
> Preserve exact plugin authority, stable identity, secrets and workspace/pairing state. Verify the actually loaded Figma version from authenticated runtime information; do not infer it from package/server/files alone.
> Keep startup inputs and private nested source pins replayable. Runtime generation/digest older than 15 seconds or absent blocks writes; reopen the same plugin only if Desktop did not reload.

This excerpt records the requested policy; it is not proof of execution or native Figma access.

## Stale prepared tasks · 2026-11-12

The user authorized safe consolidation and cleanup, preserving backups and existing work, and allowed plugin changes when the workflow was broken. During actual verification, the normal review verifier updated its manifest; a later graph specification correction also changed a pinned source. Those obsolete tasks then blocked publication of unrelated fresh tasks. Explicit revision-checked task retirement is the bounded implementation requirement derived from that observed failure. It preserves the original artifacts and does not waive source freshness.
