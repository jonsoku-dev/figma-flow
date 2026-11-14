# Web tab observation input

Use this format to join observed tab clicks to an existing canonical web graph. `tools/web_tabs_capture.mjs` writes it. You can also write it from another browser recorder. The graph must contain one `WEB-...` screen node for each observed panel state.

## Run the compiler

Put the graph, the observation JSON, and every referenced PNG in one directory. The compiler writes a new graph beside the observation JSON and refuses to overwrite files.

```sh
python3 -B tools/native_edit.py web-tabs \
  --graph CAPTURE_GRAPH.json \
  --observations OBSERVATIONS.json \
  --out TABS_GRAPH.json
python3 -B tools/native_edit.py web-design \
  --graph TABS_GRAPH.json --file-key FILE_KEY --page-id PAGE_ID \
  --readback-scope screens --out PLAN.json
```

Neither command calls a browser or Figma. The plan pins the graph hash. The existing native-edit flow applies it in the selected Figma file.

## Observation JSON

The input is a UTF-8 JSON object with `schemaVersion: 1`, `source`, `tabs`, `states`, and `transitions`. `source` has the same fields as the [carousel input](web-carousel-input.md#observation-json).

```json
{
  "tabs": {"frameKey": "devtool-examples", "initialState": "WEB-devtool-tabs-1"},
  "states": [
    {"id": "WEB-devtool-tabs-1", "label": "Single Queue Pipeline",
     "contentSha256": "<SHA-256 of the panel text>", "capture": {"path": "state-1.png", "sha256": "<hex>"}}
  ],
  "transitions": [
    {"from": "WEB-devtool-tabs-1", "to": "WEB-devtool-tabs-2", "input": "click",
     "controlElementId": "el-46", "observed": true, "evidence": {"path": "click-1.png", "sha256": "<hex>"}}
  ]
}
```

Each state needs a distinct screen and a distinct panel content hash. The panel text, not a CSS class, identifies the state. Each transition is one observed click from one state to a different state. `controlElementId` is the captured `frame` element in the source screen whose box matches the clicked tab. Element IDs can differ between screens, so the recorder resolves the ID separately in each source screen.

## Checks

The compiler accepts 2–16 states and 1–80 transitions. It refuses unobserved edges, clicks that stay on the same state, clicks on text or other non-frame elements, a clicked frame that is not fully inside the captured screen, and one control leading to two destinations. Every state must be the initial state or an observed destination. Each screen height must equal the viewport height. The width may be up to 24 px narrower for a scrollbar. Screenshot pins use the same PNG, path, and 8 MB limits as the carousel.

In Figma, each transition becomes a transparent top-level frame over the clicked tab box, named `Click · <destination label>`. It holds an `ON_CLICK` reaction with `NAVIGATE` and no animation, because the observed browser swaps the panel without one. The tab layers stay editable and carry no reaction. A reaction set directly on a tab nested deep in a captured page timed out in Figma Desktop, so the click uses the same top-level hotspot as carousel drags. Content outside the panel, such as a looping logo strip, is captured as it appeared at that moment and can differ between state frames.
