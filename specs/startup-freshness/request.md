# Source request excerpt

> At each plugin workflow start, check and safely update both the Codex package and Figma runtime files, with explicit exceptions for pin/dev/offline/auth/claimed-or-uncertain/unknown-source/access-forbidden states.
> Preserve exact plugin authority, stable identity, secrets and workspace/pairing state. Verify the actually loaded Figma version from authenticated runtime information; do not infer it from package/server/files alone.
> Keep startup inputs and private nested source pins replayable. Runtime generation/digest older than 15 seconds or absent blocks writes; reopen the same plugin only if Desktop did not reload.

This excerpt records the requested policy; it is not proof of execution or native Figma access.
