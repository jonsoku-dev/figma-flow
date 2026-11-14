# Web disclosure observation input

Use this format to join observed single-collapsible disclosure clicks (such as FAQ or accordion items) to an existing canonical web graph. `tools/web_disclosure_capture.mjs` writes it. You can also write it from another browser recorder. The graph must contain one `WEB-...` screen node for each observed state.

## Run the compiler

Put the graph, the observation JSON, and every referenced PNG in one directory. The compiler writes a new graph beside the observation JSON and refuses to overwrite files.

```sh
python3 -B tools/native_edit.py web-disclosure \
  --graph CAPTURE_GRAPH.json \
  --observations OBSERVATIONS.json \
  --out DISCLOSURE_GRAPH.json
python3 -B tools/native_edit.py web-design \
  --graph DISCLOSURE_GRAPH.json --file-key FILE_KEY --page-id PAGE_ID \
  --readback-scope screens --out PLAN.json
```

Neither command calls a browser or Figma. The plan pins the graph hash. The existing native-edit flow applies it in the selected Figma file.

## Observation JSON

The input is a UTF-8 JSON object with `schemaVersion: 1`, `source`, `disclosure`, `states`, and `transitions`. `source` has the same fields as the [carousel input](web-carousel-input.md#observation-json).

```json
{
  "schemaVersion": 1,
  "source": {
    "url": "http://127.0.0.1:8874/",
    "title": "PlanHub",
    "browser": "Chromium",
    "viewport": {"width": 1440, "height": 900},
    "dpr": 1,
    "capturedAt": "2026-11-14T00:00:00Z"
  },
  "disclosure": {
    "frameKey": "faq",
    "mode": "single-collapsible",
    "initialState": "WEB-saas-faq-1",
    "items": ["What is PlanHub?", "How do I create my first workspace?"]
  },
  "states": [
    {
      "id": "WEB-saas-faq-1",
      "label": "All closed",
      "expandedItem": null,
      "answerSha256": null,
      "contentSha256": "<SHA-256 of canonical item state list>",
      "capture": {"path": "state-1.png", "sha256": "<64 lowercase hex characters>"}
    },
    {
      "id": "WEB-saas-faq-2",
      "label": "What is PlanHub?",
      "expandedItem": "What is PlanHub?",
      "answerSha256": "<SHA-256 of visible answer text>",
      "contentSha256": "<SHA-256 of canonical item state list>",
      "capture": {"path": "state-2.png", "sha256": "<64 lowercase hex characters>"}
    }
  ],
  "transitions": [
    {
      "from": "WEB-saas-faq-1",
      "to": "WEB-saas-faq-2",
      "input": "click",
      "action": "open",
      "itemLabel": "What is PlanHub?",
      "autoClosedItem": null,
      "controlElementId": "el-10",
      "observed": true,
      "evidence": {"path": "click-1.png", "sha256": "<64 lowercase hex characters>"}
    }
  ]
}
```

`disclosure.items` lists 2–16 unique bounded question labels. In `single-collapsible` mode, at most one item is expanded in each state: `expandedItem` is `null` (with `answerSha256: null`) when all items are closed, or one of `disclosure.items` (with `label == expandedItem` and a 64-character lowercase hex `answerSha256` of the visible answer text) when that item is open.

Each transition records one observed click (`input: "click"`, `observed: true`) on `itemLabel`:

- `open`: `expandedItem` moves from `null` to `itemLabel`, with `autoClosedItem: null`.
- `close`: `expandedItem` moves from `itemLabel` to `null`, with `autoClosedItem: null`.
- `switch`: `expandedItem` moves from a different open item to `itemLabel`, with `autoClosedItem` naming the previously open item that closed automatically.

`controlElementId` is the captured `frame` element in the source screen whose box matches the local trigger header (not the expanded item container). Element IDs can shift between states as answers mount or unmount, so each source screen resolves its own `controlElementId`. Repeating an already observed click is listed once in `transitions` while every click stays in `inputs.json`.

## Checks

The compiler accepts 2–16 items, 2–16 distinct states, and 1–80 transitions. It refuses unobserved edges, self-loops, duplicate `expandedItem` states, missing or unexpected `answerSha256` digests, `action` or `autoClosedItem` mismatches, clicks on non-frame elements, trigger frames outside the captured screen bounds, duplicate `(from, controlElementId)` or `(from, itemLabel)` edges, and states not reachable from `initialState` by directed traversal across `transitions` (for example, disconnected cycles are rejected). Each screen height must equal the viewport height, and width may be up to 24 px narrower for a scrollbar. Screenshot pins use the same PNG, path, symlink, and 8 MB limits as the carousel and tabs inputs.

In Figma, each transition becomes a transparent top-level hotspot frame over the local trigger header (`Open · <item>`, `Close · <item>`, or `Switch · <item>`) with an instant `ON_CLICK` `NAVIGATE` reaction, while question text, answer text, and chevron vectors remain editable layers.
