# Plugin API evidence priority

The ranked graph connects each audited API member to its exact owner, compatible receivers, user roles, feasibility, Design scope and evidence. The default command joins the pinned audit and the 0.29, 0.30 and responsive-web observations. A property can be readable even when the SDK also allows writes. Only explicitly mapped methods enter the read-only or owned-write queues. Methods needing a scenario, declaration-only types, unresolved receivers, editor-only rows and permission gates retain distinct classifications.

The score is a work-order hint, not evidence that a method or getter works. Graph status is copied only from a validated `observed member` edge to the exact `member:<hash>` audit key. An unlinked graph node with status `observed` contributes nothing. The builder never converts audit references, declarations, or queue membership into successful runtime observations.

```sh
python3 tools/api_priority.py build --out .figma-flow/api-priority.json
python3 tools/api_priority.py queue --inventory .figma-flow/api-priority.json --format graph > .figma-flow/ranked-graph.json
python3 tools/api_priority.py queue --inventory .figma-flow/api-priority.json --receiver TEXT --limit 30 --feasible-only
python3 tools/api_priority.py queue --inventory .figma-flow/api-priority.json --design-only --feasible-only
python3 tools/api_priority.py build --baseline-only --out .figma-flow/api-priority-029.json
python3 tools/api_priority.py build --observations specs/graph-review/api-observations.json \
  --overlay .figma-flow/new-sanitized-api-observations.json --out .figma-flow/api-priority-updated.json
```

The CLI joins four receipt-validated overlays: editable web, responsive web, Design scene inspection, and Design service inspection. The 0.30 baseline had 150 observed keys and 1,232 unobserved rows. Four 0.31 responsive-web batches added 39 distinct keys, bringing the count to 189 and the remaining queue to 1,193. The 0.32 Design scene and service graphs add 273 distinct keys. The current queue has 920 unobserved rows. Pass `--baseline-only` to reproduce the earlier 0.29 queue with 1,255 unobserved rows. Direct `build()` library calls retain the baseline-only behavior for existing callers. The full queue keeps receiver-unknown, type-only, and editor or permission limited rows so their blockers stay visible. `--feasible-only` filters to readable properties, explicitly approved read-only methods, and purpose-approved owned-write methods.

Every row includes role term matches, a short reason for its feasibility rank, catalogued node receiver types, editor and permission requirements, Design scope, and any validated evidence links. `design_scope` distinguishes `design-node`, `shared-node`, and `design-api` rows from `figjam-only`, `slides-only`, type-only, unresolved runtime objects, and other editor-specific rows. The complete inventory keeps out-of-scope rows for denominator and audit history. `--design-only` filters the work queue to the three Design-compatible scope classes.

The inventory classifies `InstanceNode.mainComponent` as `write-only-in-dynamic-page`. Use the bounded `getMainComponentAsync()` read route for an owned instance. It classifies `ComponentNode.instances` as `unavailable-in-dynamic-page`. Use `getInstancesAsync()` on the owned fixture component, where the result is reduced to a count.

Observation graphs count only when a test evidence node connects to the exact official member node with an `observed member` edge. Graph structure, unique IDs, and all edge endpoints are checked. Each `--overlay` must also carry a timezone-aware non-future `observed_at`, a SHA-256 receipt reference, and at least one successful getter call. Repeat `--overlay` to join more sanitized graphs. This checks the supplied graph record; it does not verify the receipt hash against a raw receipt file or prove that the overlay was produced by the plugin.

The native probe sorts eligible candidates by the same queue score used here, attaches each item's role matches and feasibility reason, and excludes keys already linked to successful observations. It requires exact node IDs and types from a saved native readback, then runs bounded getter batches against those receivers. The Design recipe uses scalar layout, grid, appearance, text-style, page, component, and document reads. It uses static method calls for CSS, text ranges, and async instance relationships. Opaque style identities become assigned/unassigned state. Collection values become bounded counts or small enum summaries. Raw vector paths, text contents, names, style identities, nested variable maps and arbitrary method invocation stay outside the probe. The sanitized Design overlays retain timestamps, aggregate getter counts and receipt hashes, but omit file/page/node IDs and raw readbacks.

For an installed-version regression check, a private API probe selection can add `recheck_member_ids` with 1–16 exact audit member keys already linked to evidence. Use offset zero and select actual nodes that support those members. The read still uses the same static receiver and output allowlists. Omitting this field continues exploration of the unobserved queue.
