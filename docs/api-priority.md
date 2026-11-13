# Plugin API evidence priority

`tools/api_priority.py` builds a deterministic ranking over every exact-key member in the pinned 0.28 audit and marks keys already present as observed in the 0.29 API observation graph. Ranking estimates usefulness to designers, developers, and planners, then favors runtime owners and feasible read-only properties. Methods require an owned disposable target before they are considered safe queue work. Type-only, unresolved-receiver, editor-gated, and permission-gated rows remain in the complete inventory with their limits visible.

The score is a work-order hint, not evidence that a method or getter works. Graph status is copied only from a validated `observed member` edge to the exact `member:<hash>` audit key. An unlinked graph node with status `observed` contributes nothing. The builder never converts audit references, declarations, or queue membership into successful runtime observations.

```sh
python3 tools/api_priority.py build --out .figma-flow/api-priority.json
python3 tools/api_priority.py queue --inventory .figma-flow/api-priority.json --limit 1255
python3 tools/api_priority.py queue --inventory .figma-flow/api-priority.json --receiver TextNode --limit 30 --feasible-only
python3 tools/api_priority.py build --observations specs/graph-review/api-observations.json \
  --overlay .figma-flow/new-sanitized-api-observations.json --out .figma-flow/api-priority-updated.json
```

The current joined inputs yield 1,382 exact-key rows: 49 have a validated observation graph edge and 78 carry the pinned audit's observed status, leaving 1,255 unobserved rows in the work queue. The full queue includes receiver-unknown, type-only, and editor or permission limited rows so their blockers stay visible. `--feasible-only` filters to classified read-only properties, the four static read-only methods in the native probe policy, and methods requiring an owned disposable target.

Every row includes role term matches, a short reason for its feasibility rank, catalogued node receiver types, editor and permission requirements, and any validated evidence links. Observation graphs count only when a test evidence node connects to the exact official member node with an `observed member` edge. Graph structure, unique IDs, and all edge endpoints are checked. Each `--overlay` must also carry a timezone-aware non-future `observed_at`, a SHA-256 receipt reference, and at least one successful getter call. Repeat `--overlay` to join more sanitized graphs. This checks the supplied graph record; it does not verify the receipt hash against a raw receipt file or prove that the overlay was produced by the plugin.

Use actual node IDs from a saved native readback when preparing a probe. The native probe accepts only its declared field allowlist and safe projections. `GROUP` is available as a receiver when the readback observed it. `VECTOR` candidates are rankable and probeable after a real readback supplies a vector node ID; the current reused board readback contains no `VECTOR` node, so it provides no target for a vector runtime batch. Raw vector paths, vector networks, text contents, names, style identities, and arbitrary method invocation stay outside the probe.
