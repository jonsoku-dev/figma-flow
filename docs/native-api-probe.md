# Probe selected native API properties

Use the registered discovery task to read bounded, documented Figma Design properties from exact nodes that a prior readback observed. The probe does not scan pages or change document nodes.

## Prepare a selection

Create a JSON file with the file and page IDs from the native readback, plus each selected node's semantic ID, observed node ID, and observed type.

```json
{
  "schema": "figma-flow-native-api-probe-selection-v1",
  "fileKey": "YOUR_FILE_KEY",
  "pageId": "YOUR_PAGE_ID",
  "nodes": [
    {
      "semantic_id": "grid-frame",
      "observed_node_id": "123:456",
      "observed_type": "FRAME"
    }
  ]
}
```

Prepare the first getter batch. The command checks the official local Plugin API declarations and the unresolved member audit. It writes a private, normalized selection request, not a Figma plugin call.

```sh
python3 tools/native_api_probe.py prepare \
  --selection .figma-flow/native-api-selection.json \
  --file-key YOUR_FILE_KEY \
  --page-id YOUR_PAGE_ID \
  --candidate-offset 0 \
  --out .figma-flow/native-api-probe-request-0.json
```

Submit the request through the existing workspace discovery route.

```sh
python3 tools/figma_workspace.py prepare \
  --workspace .figma-flow/plugin-workspace \
  --key native-api-probe-0 \
  --title "Native API probe, batch 0" \
  --kind discover -- \
  --file-key YOUR_FILE_KEY \
  --page-id YOUR_PAGE_ID \
  --api-probe .figma-flow/native-api-probe-request-0.json
```

Run the prepared discovery task from the registered workspace plugin. Save its JSON readback as `.figma-flow/native-api-probe-readback-0.json` before preparing another batch.

## Continue through the eligible properties

Each batch probes up to 16 properties for each selected node type, with a hard limit of 384 getter attempts. Use offsets `0`, `16`, `32`, and so on. Pass the latest saved readback to compare statuses and retain earlier observations in the output graph.

```sh
python3 tools/native_api_probe.py prepare \
  --selection .figma-flow/native-api-selection.json \
  --file-key YOUR_FILE_KEY \
  --page-id YOUR_PAGE_ID \
  --candidate-offset 16 \
  --previous-readback .figma-flow/native-api-probe-readback-0.json \
  --out .figma-flow/native-api-probe-request-16.json
```

Prepare and run a new workspace task for each batch, using a new task key and the generated request file. Save each JSON readback. Stop when `api_probe.eligibleByType` reports `coverage: "complete"` for every type. `coverage: "no-candidate"` means the local audit found no eligible getter. An empty batch does not count as a property read.

The output reports `success`, `unavailable`, `unsupported`, and `blocked` counts for the current batch. It also reports cumulative `mergedCounts`, the next offset for each type, the actual receipt timestamp, and `matched`, `changed`, or `unknown` status deltas. It marks prior statuses unknown when the file, page, exact node selection, API source, unresolved audit, property policy, or receipt timestamp does not match.

The `graph` field uses the shared graph schema. It links selected semantic IDs to node types, official API member IDs, and observation results. It includes safe current values and marks properties from later batches as planned. A selection with no eligible properties remains `no-candidate` and does not imply coverage.

## Bounds and sample result

The probe accepts at most 24 exact nodes, 16 candidate getters per type per batch, 384 getter attempts, 3,000 ms, and 32 parent checks per node to confirm page scope. It supports documented Design scene nodes, pages, and the document root. A document-root target must match `figma.root`; all other targets must remain under the selected page.

The field allowlist covers scalar layout and appearance properties, bounded geometry, text style values, stroke summaries, motion collection counts, node-reference state, and selected page and document values. It summarizes collections as counts, removes style and node identities, and projects only approved fields from nested layout, paint, and vector structures. It never returns node names, text, code, raw vector paths, variable IDs, image bytes, or network data. The probe rejects private or proposed API members.

The owned fixture lab creates a marked page with sample Design nodes and reuses that page on later runs. It restores the page and selection that were active before the run. It does not delete nodes or send document data over the network. Use it only in the file key pinned in the private lab manifest. The lab returns exact node IDs for a local selection file; keep that selection and its readback under `.figma-flow/`.

## Rebuild the private fixture plugin

Create a new plugin directory under `.figma-flow/` from the public fixture source. Pass the private Figma-issued plugin ID and the exact file key for the owned lab file.

```sh
python3 tools/native_api_fixture_project.py \
  --plugin-id FIGMA_ISSUED_PLUGIN_ID \
  --file-key OWNED_LAB_FILE_KEY \
  --out .figma-flow/native-api-lab
```

In Figma Desktop, import `.figma-flow/native-api-lab/manifest.json` as a development plugin. Run the fixture command once, then run the reversible-call command on the generated lab page. The generator limits the plugin to Figma Design, enables private file-key access, and sets network access to `none`. It refuses to overwrite an existing output directory.

The lab's owned-read command calls `getMainComponentAsync()` and `getInstancesAsync()` on fixture-marked nodes. It filters instance results by the same plugin marker that created the fixture and returns only a count or link state. Run these calls from the lab plugin so the marker check uses the same plugin-data namespace.

The lab's reversible-call command can exercise `resize` on the owned frame, text range setters on the owned text, and plugin-data access under one fixed lab key. It saves each prior value, applies a temporary value, checks the result, and restores the saved value before it reports success. The receipt contains only method names, statuses, restoration flags, and aggregate counts.

On one disposable Figma Design page, nine observed nodes produced 141 node–member observations across 37 distinct API member IDs. The two getter batches returned 111 and 30 successful reads, with no unavailable, unsupported, or blocked getters. The merged graph had zero errors under the shared graph validator. This result describes that file, selection, and Plugin API version.

The probe also accepts an exact observed `GROUP` node and, when a real readback supplies one, `VECTOR` nodes. Its separate static method path allows only `getCSSAsync` and text range `getRangeFontName`, `getRangeFontSize`, and `getRangeFills`. It derives text ranges from `characters.length` without returning text. CSS values pass a property-specific numeric, enum, or color projection; font range output keeps family/style and validated variation axes, not text. Arbitrary methods remain blocked. The property allowlist also includes bounded transform matrices, basic stroke alignment/cap/join/dash styling, visibility/mask/clip flags, text auto-resize, and blend mode. Vector paths and vector networks remain excluded because they can expose raw path data or large structures. Use the [API priority queue](api-priority.md) to choose candidates, then inspect each generated bounded request before registering it. The historical sample counts above describe the earlier probe run and do not include the new property and method candidates.
