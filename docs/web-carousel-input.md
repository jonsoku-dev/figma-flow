# Web carousel observation input

Use this format to join browser screenshots and observed transitions to an existing canonical web graph. The graph must contain one `WEB-...` screen node for each carousel state. Each screen keeps its captured layout and elements.

## Run the compiler

Put the graph, the observation JSON, and every referenced PNG in one directory. The compiler writes a new graph beside the observation JSON and refuses to overwrite files.

```sh
python3 -B tools/native_edit.py web-carousel \
  --graph CAPTURE_GRAPH.json \
  --observations OBSERVATIONS.json \
  --out CAROUSEL_GRAPH.json
python3 -B tools/native_edit.py web-design \
  --graph CAROUSEL_GRAPH.json \
  --file-key FILE_KEY \
  --page-id PAGE_ID \
  --out PLAN.json
```

Both commands use Python's standard library. They do not call a browser service or Figma. The second command prepares a pinned plan; the existing native-edit flow applies that plan in the selected Figma file.

## Observation JSON

The input is a UTF-8 JSON object with `schemaVersion: 1`, `source`, `carousel`, `states`, and `transitions` fields.

`source` records the page and capture environment:

```json
{
  "url": "https://example.test/pricing",
  "title": "Example pricing",
  "browser": "Chromium 130",
  "viewport": {"width": 390, "height": 844},
  "dpr": 1,
  "capturedAt": "2026-11-14T08:30:00Z"
}
```

`carousel` defines the measured rail and finite state order:

```json
{
  "frameKey": "WEB-pricing-features:rail",
  "stateIds": ["WEB-pricing-feature-1", "WEB-pricing-feature-2"],
  "initialState": "WEB-pricing-feature-1",
  "intervalMs": 5000,
  "wrap": {"manual": false, "autoplay": true},
  "rail": {"rect": {"x": 0, "y": 210, "width": 390, "height": 420}}
}
```

State IDs must match the order of the screen nodes in the captured graph. Use two to sixteen states. `frameKey` identifies the observed rail. The compiler copies the rail rectangle to each state's `railBounds`, in viewport-relative CSS pixels.

Each `states` item includes its state ID and a pinned screenshot. The array order must match `carousel.stateIds`. If an item includes `index`, the value must match its zero-based array position.

```json
{"id": "WEB-pricing-feature-1", "capture": {"path": "state-1.png", "sha256": "<64 lowercase hex characters>"}}
```

Each transition names a source state, destination state, and input. Supported inputs are `swipe-left`, `swipe-right`, `next`, `previous`, and `autoplay`. An observed transition has `observed: true` and a screenshot evidence reference. A derived edge has `observed: false` and no evidence field.

```json
{
  "from": "WEB-pricing-feature-1",
  "to": "WEB-pricing-feature-2",
  "input": "swipe-left",
  "observed": true,
  "evidence": {"path": "swipe-1-to-2.png", "sha256": "<64 lowercase hex characters>"}
}
```

List one edge for every state and each declared input. Keep destinations consistent with state order and the separate manual and autoplay wrap settings. A clamped manual end points back to the same state. A wrapping autoplay end points to the first state.

## Evidence checks

The compiler checks every state and transition PNG against its SHA-256 value. Each PNG must be at most 8 MB, and all unique PNGs together must stay under 8 MB. Evidence paths must be relative, stay in the observation directory, and contain no symbolic links. Keep the output graph in that directory so the relative evidence paths remain valid.

The compiler checks transition endpoints, duplicate edges, trigger coverage, wrap destinations, the initial state, viewport bounds, and autoplay interval. It does not infer browser behavior from CSS classes or fill in missing observations. The signed native plan binds the resulting canonical graph hash and rechecks its evidence pins before use.
