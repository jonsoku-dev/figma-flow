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

Each batch probes up to 16 properties for each selected node type, with a hard limit of 192 getter attempts. Use offsets `0`, `16`, `32`, and so on. Pass the latest saved readback to compare statuses and retain earlier observations in the output graph.

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

The probe accepts at most 12 exact nodes, 16 candidate getters per type per batch, 192 getter attempts, 1,500 ms, and 32 parent checks per node to confirm page scope. It reads numeric, boolean, enum, bounded geometry, arc geometry, and solid paint values. It excludes node names and text, component and variable identities, hierarchy collections, code, images, bytes, network calls, and private or proposed API members.

On one disposable Figma Design page, nine observed nodes produced 141 node–member observations across 37 distinct API member IDs. The two getter batches returned 111 and 30 successful reads, with no unavailable, unsupported, or blocked getters. The merged graph had zero errors under the shared graph validator. This result describes that file, selection, and Plugin API version.
