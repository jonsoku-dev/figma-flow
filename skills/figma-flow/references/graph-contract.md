# Evidence graph contract

Maintain one canonical JSON graph per run and carry stable semantic IDs forward across runs. A Figma file key or node ID is external evidence, not a replacement for the product ID. Keep the graph as the relationship inventory; rendered views and screen specifications refer to its IDs. Use source references that are safe to expose. Do not put secrets or private user data into shared Figma metadata.

```json
{
  "version": 1,
  "nodes": [
    {"id": "REQ-001", "type": "requirement", "title": "Add an idea", "status": "observed", "source": "brief.md#add"},
    {"id": "SCR-001", "type": "screen", "title": "Idea list", "status": "planned"},
    {"id": "FIG-001", "type": "figma", "title": "List frame", "status": "unverified", "source": "Figma file and node URL"}
  ],
  "edges": [
    {"from": "REQ-001", "to": "SCR-001", "type": "appears on"},
    {"from": "SCR-001", "to": "FIG-001", "type": "represented by"}
  ]
}
```

Node types: `reference`, `design-token`, `component`, `requirement`, `screen`, `state`, `action`, `acceptance`, `figma`, `code`, `test`. Use `acceptance` for a product acceptance criterion and `test` for an actual test or verification activity; connect them when a test checks that criterion. `id`, `type`, `title`, and `status` are required; `source` and `detail` are optional strings. Status is `planned`, `observed`, `verified`, `blocked`, or `unverified`. `verified` requires a nonempty `source` reference; the reference still needs human/agent interpretation and is not automatically checked. Each edge requires nonempty `from`, `to`, and `type`, and both IDs must exist. Edge direction should follow the trace: requirement → screen → Figma/code → test when applicable; separate state and action nodes can sit between them.

A `reference` uses the same required fields as other nodes, with no new mandatory metadata. Put the official URL in `source`; put a short supporting excerpt, original context (in-game or browser), source locator and narrow adopted principle in `detail`. Its `informs` edge points toward the precise requirement. Source observation and product runtime verification remain separate.

For an action node, record `source_screen` as its triggering screen ID and `target_ids` as an array of represented destination screen/state/other node IDs when they exist. Connect `source_screen → action` and `action → target` with actual directed edges. When `source_screen` is present, no other screen may point to that action; model separate actions for distinct source screens. When `target_ids` is present, include every outgoing screen/state destination. Other outgoing edges such as implementation or test evidence need not be destinations. Multiple targets are valid. An action with no represented destination node (for example, back or external URL) may use `target_ids: []`. Older graphs without `source_screen` or `target_ids` remain valid but produce warnings. The validator checks consistency with supplied fields, not whether those fields truthfully reflect the brief or Figma; compare each action against the source or observed reaction.

Record assumptions and the scope of each observation in `detail` or a linked screen specification. A `verified` screenshot proves only the visual state actually inspected. A test result, a Figma metadata response, and prototype playback are separate evidence. The graph helper does not inspect Figma, run a browser, validate evidence links, or decide whether the product is done.

### Native draft entries and static controls

`draft_prototype.entry_state` remains the default start. Optional `entry_states` is a nonempty array of unique existing state IDs containing that default. The native draft checks forward reachability and return to any declared entry in both viewports, and verifies every explicit entry as an actual desktop/mobile flow start. Without this field, the legacy desktop-only default start is preserved. Declare extra entries only for real direct-entry routes; they do not create navigation controls. A native NAVIGATE binding must target a different state frame; current-page links stay static. Both packet validation and native preflight reject self-navigation before creating a page.

An unbound `product_buttons[control_id]` may declare `specification_id` pointing to a current graph action on the same screen. The action annotation's `control_id` must identify that actual control; the action ID and control ID may differ. The compiled specification must target that control, and the action cannot also be a prototype binding. Native validation requires an actual COMPONENT-backed INSTANCE, its connected annotation and full-spec link, and an observed empty reactions array. A described web action therefore carries its real specification without claiming to run in Figma. Omitting `specification_id` retains legacy geometry-only validation and supplies no connected-spec evidence.

## Canonical relationship vocabulary

Use these labels consistently in new graphs. They are authoring conventions; `graph.py` accepts other nonempty labels for compatibility and does not enforce the endpoint types in this table.

| From → to | Edge type | Meaning |
| --- | --- | --- |
| reference → requirement | `informs` | Cited source observation informs an adopted product principle; it does not prove implementation. |
| requirement → screen | `appears on` | Screen presents the requirement. |
| requirement → acceptance | `accepted by` | Criterion defines acceptance for this requirement. |
| screen → state | `has state` | Screen owns a named empty/loading/error/content state. |
| screen → action | `triggers` | Action starts on this screen; matches `source_screen`. |
| action → screen/state | `navigates to` | Represented outcome; matches `target_ids`. |
| screen/state/action → figma | `represented by` | Actual frame/node/reaction evidence for that semantic object. |
| screen/state/action → code | `implemented by` | Repository implementation of that object. |
| acceptance/code → test | `checked by` | Specific verification activity, with result evidence. |
| upstream → dependent | `depends-on` | A change upstream requires reviewing this dependent. |

`depends-on` follows the direction of change propagation, despite the English label: `FIG-001 → CODE-001` means code must be reviewed after that Figma evidence changes. Add it only when justified. Trace and navigation edges do not automatically establish version dependencies. `ssot.py` follows only explicitly selected edge types, whereas `graph.py impact` follows all edges. Neither tool proves that a candidate needs an edit. For an external/back action with no represented destination, retain `target_ids: []` and describe its actual behavior in `detail`.

## Strict local coverage gate

Use `graph.py validate GRAPH --strict-local` for a local delivery gate; ordinary validation keeps its legacy warning behavior. Strict local validation requires at least one requirement and checks canonical direct typed edges:

- Every requirement has an `appears on` screen and an `accepted by` acceptance criterion.
- Every screen and acceptance criterion has a direct owning requirement. Requirement and screen status must be `observed` or `verified`.
- Every screen has at least one `implemented by` code node; all linked code nodes are `verified`.
- Every acceptance criterion is `verified`, has at least one direct `checked by` test, and all linked tests are `verified`.
- For each requirement, each acceptance criterion shares at least one verified `checked by` test with code implemented by its direct screens, and each such code shares at least one test with that requirement's criteria. Disconnected test islands do not satisfy this gate.
- Canonical edge labels have the endpoint types in the table above. The ordinary structural and action checks also apply.

Figma nodes are optional for this gate. Existing `verified` → nonempty `source` rules apply, but source existence and evidence meaning are not checked by this command. Include local evidence in SSOT bindings and inspect the real results. Strict success means declared coverage passes, not that the brief is exhaustively interpreted or that the product works.

The screen specification is agent-authored Markdown linked to graph IDs, not a second relationship database. For each screen include its requirement IDs, states, actions/outcomes, acceptance IDs, implementation and evidence links. Correct relationships in graph JSON first, then update the specification and regenerate rendered views. `render` emits `screen-graph.md` and `screen-graph.mmd`; it does not generate the screen specification.

## Authority, evidence and conflicts

Select authority per fact, not by a universal “brief beats Figma beats code” rule. Use the run record for field-level decisions, including the fact key, affected IDs, authority locator, source version/hash, observed value and evidence. Typical defaults:

| Fact | Authority | Separate evidence needed |
| --- | --- | --- |
| Intended policy, flow and acceptance | Brief or explicit approved decision | Exact section and version; assumptions remain labeled. |
| Current layout, tokens and editable hierarchy | Figma selection | File/node IDs, read time and version or saved response hash. |
| Actual prototype reactions | Figma reaction readback | Trigger, action and destinations; playback is a separate result. |
| Implemented behavior | Repository revision and working tree | Actual source diff; runtime checks establish execution. |
| Acceptance result | Observed verification activity | Command/flow, environment, pinned inputs, result and time. |

On contradiction, retain each source value and evidence, mark the affected work blocked and record a specific decision/resolver. After an authorized resolution, update the chosen authority and affected graph/spec/design/code, then rerun relevant checks. The helpers do not detect semantic conflicts or select a winning source. A `verified` graph node can become stale: retain its old evidence in the record, set its current node status to `unverified` (or `blocked` when a decision/access is required), and restore `verified` only after fresh checks. `stale` is a run-record freshness value, not a valid graph node status.

## Local freshness manifests

`scripts/ssot.py` complements graph validation with immutable local content snapshots. It uses Python's standard library. Create a bindings JSON (version 1) next to the referenced project files:

```json
{
  "version": 1,
  "authorities": {
    "intent": "brief.md",
    "visual": "https://www.figma.com/design/FILE/Example?node-id=1-2",
    "implementation": "app.py"
  },
  "dependency_edge_types": ["depends-on"],
  "evidence": {
    "SCR-001": ["screen-spec.md", "https://www.figma.com/design/FILE/Example?node-id=1-2"]
  }
}
```

Paths in bindings resolve relative to the bindings file; graph node `source` paths resolve relative to the graph file; CLI input paths resolve from the working directory. Replace example paths and Figma URLs with actual observed targets. `authorities` contains `intent`, `visual` and `implementation` for the default full scope. With `--scope local-only`, `visual` may be omitted; a local screen specification is a useful visual authority when available. `intent` must resolve to the supplied `--brief`. These are coarse source locators; field-level authority/conflict decisions remain in the run record. `evidence` maps existing graph node IDs to arrays of local evidence files or remote locators. The helper also includes each node's `source`. List every required dependency and evidence file deliberately; unlisted files are outside the snapshot's coverage.

```sh
python3 "$SKILL_DIR/scripts/ssot.py" snapshot --brief ./run/brief.md --graph ./run/graph.json --bindings ./run/bindings.json --out ./run/manifest-001.json
python3 "$SKILL_DIR/scripts/ssot.py" check ./run/manifest-001.json
python3 "$SKILL_DIR/scripts/ssot.py" snapshot --brief ./run/brief.md --graph ./run/graph.json --bindings ./run/bindings.json --previous ./run/manifest-001.json --out ./run/manifest-002.json
```

For a Figma-free run, use `snapshot ... --scope local-only`. Scope defaults to `full`, is inherited with `--previous`, and cannot change within a chain. A local-only check permits an absent or remote-unchecked visual authority; a present missing local visual file still blocks. Remote or missing node evidence still blocks. Optional visual authority is a scope choice, not proof of remote parity.

Snapshot outputs refuse overwrite and retain an integer revision plus a parent hash chain when `--previous` is used. Keep chained manifests in the same output directory. The helper hashes local brief, graph, bindings, authority/evidence files, graph nodes, their adjacent edges and graph metadata. Brief changes conservatively affect requirement nodes; authority/bindings changes affect all nodes. Explicit dependency edges propagate candidates downstream. `snapshot` exits `0` for a successful write, even if its content is stale/unavailable. `check` emits JSON and exits `0` only when every node is `content-current`, required authority refs are current in the declared scope, and inputs are unchanged; `2` means stale/unavailable/changed input. Invalid input or unreadable critical brief/graph/bindings produces exit `1`. Inspect every reported reason. Nodes without evidence remain `unverified`. Remote references are `remote-unchecked`: the helper performs no network read and never proves a live Figma version. Missing local files are also unavailable. A local-only manifest cannot certify remote design parity.

### Project registration and inspection

Resolve `tools/` at the plugin root. For the first baseline of an already prepared local project:

```sh
python3 tools/check_project.py --init --brief ./project/brief.md --graph ./project/graph.json --bindings ./project/bindings.json --out ./first-baseline
python3 tools/check_project.py ./first-baseline/manifest-001.json --previous-graph ./first-baseline/baseline-graph.json --intent inspect --out ./inspection-001
```

Initialization requires an explicit `--init` plus brief, graph and bindings; it validates strict-local coverage and creates a local-only baseline and reports. It preserves the accepted graph's exact bytes as `baseline-graph.json`. Keep that file immutable alongside its manifest. Use init only for an initial baseline; existing stale chains continue through reviewed resumption below. An idea-only graph does not meet this delivery gate: author the spec, implementation and genuine scoped evidence first.

Inspection follows input paths recorded in the manifest and emits `summary.json`, `check.json` and `trace.html` into a new directory. Coverage and freshness are separate outcomes. It reads recorded evidence; it does not run project commands. Exit `0` means declared coverage and registered content checks passed; `2` means stale/unavailable content; `1` means invalid inputs, coverage or report generation. Output directories must be new and separate from declared inputs.

`--previous-graph` compares actual old and current graph content only after checking the old file bytes against the selected manifest's graph hash. Preserve whitespace and encoding too: semantic JSON equivalence alone is insufficient. A mismatching old graph is an input error. Verified comparisons emit `graph-diff.json` and `graph-diff.html` with added/removed nodes, field changes and edge changes. `summary.json` records `graph_diff_status` as `verified` or `not-requested`. Without that file, exact graph changes remain unavailable; manifest content/evidence hashes and explicitly declared dependency propagation still support a bounded explanation. An inherited stale state cannot establish the original historical cause. Dependency explanations follow selected dependency edge types across old/current inventories; a displayed shortest path is one declared review route, not proof of semantic impact or test failure.

### Cross-project idea catalog

```sh
python3 tools/idea_catalog.py --project Personal ./personal/manifest-001.json --project Work ./work/manifest-001.json --out ./catalog-001
python3 tools/idea_catalog.py --idea Draft ./draft/graph.json --project Personal ./personal/manifest-001.json --out ./catalog-002
```

Repeat `--project LABEL MANIFEST` for implemented projects and `--idea LABEL GRAPH_JSON` for proposed graphs without manifests. Labels must be unique. `index.html` supports search by label and requirement/screen ID/title, project filtering and type filtering. Requirements form the feature inventory; screens form the screen inventory. Identity remains `(project label, semantic ID)` so separate projects may reuse IDs. Each source retains its own graph declaration, coverage and freshness; proposed graphs have no manifest-backed freshness or verified implementation merely because they render.

The catalog writes `catalog.json` and manifest-backed per-project reports beneath `projects/001/`, `projects/002/`, and so on. Inspect each project's status and limitations, including invalid or stale sources. For manifest-backed checks the exit is `0` when all are current, `2` when any is stale and none invalid, `1` when any is invalid. Structurally valid ideas have status `draft`, display `기획 초안 · 구현/증거 미검증`, and exit `0` without SSOT checks or a trace report. Their projected nodes are unverified. Idea-only browsing is separate from project acceptance. New textual briefs first need agent-authored structural graphs with proposed requirements/screens; this tool does not extract meaning from prose or fabricate evidence.

### Reviewed resumption

Staleness inherited from a previous snapshot persists. A new snapshot alone is not revalidation. Run `check OLD_MANIFEST` after changes; save its JSON, including `review_target_sha256` and sorted `review_affected_ids` (stale and removed IDs). Reconcile affected brief/spec/code/evidence and execute relevant checks. Then run check again so the review pins the state you actually reviewed.

Create a review JSON with exactly these fields:

```json
{
  "previous_manifest_sha256": "manifest_sha256 field of the exact previous manifest",
  "current_state_sha256": "review_target_sha256 from the latest check",
  "affected_ids": ["exact sorted review_affected_ids from that check"],
  "evidence": "revalidation.md",
  "evidence_sha256": "sha256 of the evidence file bytes at review time",
  "review_note": "What changed, what was reviewed and what the evidence establishes"
}
```

`evidence` is a readable local file resolved relative to the review JSON; `evidence_sha256` must match its bytes when review is admitted. Keep that file and review JSON unchanged after the new snapshot; their pins are checked for drift. The review records human/agent judgment and never establishes that tests ran merely because text says so. Evidence should include actual commands, results, inputs and remaining limitations. Remote references remain unchecked.

```sh
python3 "$SKILL_DIR/scripts/ssot.py" snapshot --brief ./run/brief.md --graph ./run/graph.json --bindings ./run/bindings.json --previous ./run/manifest-001.json --review ./run/review-002.json --out ./run/manifest-002.json
python3 "$SKILL_DIR/scripts/ssot.py" check ./run/manifest-002.json
```

A stale target hash, different affected IDs, wrong previous hash or unreadable evidence fails review admission. Recheck and review the actual new state. Preserve the parent chain and old evidence; do not clear stale results by quietly starting an unrelated baseline.

## Commands

Resolve the actual installed path to this skill and use its `scripts/graph.py`; `SKILL_DIR` below is a shell variable you assign to that path, not an automatically populated environment variable.

```sh
python3 "$SKILL_DIR/scripts/graph.py" validate ./run/graph.json
python3 "$SKILL_DIR/scripts/graph.py" render ./run/graph.json --out-dir ./run/graph-output
```

`validate` exits nonzero on invalid JSON, invalid structure or references. Without `--strict-local`, coverage gaps are warnings even when the structure is valid. Use the strict gate above for declared local completion. `render` writes `screen-graph.md` and `screen-graph.mmd` into the output directory and refuses to overwrite those filenames. The Markdown includes compact overview and navigation views when their selected nodes have direct edges, followed by the complete graph; filtered views never invent missing relationships. Untrusted labels and non-URL source strings are rendered as inert text. A valid HTTPS source is rendered as an explicit clickable link; other schemes and source strings stay inert. No source is rendered as an image. Choose a fresh output directory for every new run. Read the output and report all warnings; a zero exit code never means the workflow passed product acceptance.

Use relative paths or durable links appropriate for the receiving project. Track input version or hash, phase results, Figma node IDs, evidence, unresolved items and output paths in a separate run record alongside the graph. If the user requests only a subset, missing later-stage nodes are expected and must not be promoted to completion.

## Optional impact analysis

When NetworkX is available in the chosen Python environment, use its directed-graph algorithms to inspect downstream nodes and reachable cycles after a change:

```sh
python3 "$SKILL_DIR/scripts/graph.py" impact ./run/graph.json --from REQ-001
```

The JSON result follows existing directed edges and lists **candidate impacts** with shortest graph paths. It does not infer reverse dependencies, prove a node needs changes, or prove a test has passed. Navigation edges can broaden the candidates: inspect edge meaning and evidence before updating any status. For example, if a screen points separately to a Figma node and code node, starting at the Figma node will not infer a path back through the screen to the code; record explicit justified dependencies or inspect the owning screen as well. Interaction graphs can contain legitimate return/retry loops. `cyclic_components` lists reachable strongly connected component members in sorted order; it does not claim that the list itself is a traversable cycle path. Cycles are reported, not rejected. The base `validate` and `render` commands use only Python's standard library and continue to work without NetworkX. If `impact` reports the optional dependency missing, use an existing compatible Python environment or install `requirements-optional.txt` into a task-specific isolated environment when within the requested scope. Never silently modify a global Python environment.

Use `graph.py render graph.json --strict-local --out-dir NEW_DIR` for a completed local graph. It applies the same coverage checks as strict local validation before writing the views.
