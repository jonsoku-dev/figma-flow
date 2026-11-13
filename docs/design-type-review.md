# Designer and developer typography specimen

`library/figma-recipes/design-type-review.ts` creates a graph-scoped typography component on an explicitly selected existing Design page. It uses a versioned frame name containing the injected graph and selection hashes. Repeating the same graph and selection verifies and reuses the existing component; a different version or graph creates a sibling and leaves previous artifacts intact. The recipe does not delete or edit the board's existing nodes.

The public graph template is [design-type-review.graph.json](../library/figma-recipes/design-type-review.graph.json). It contains no file or page identifiers. Generate a local, private graph only after selecting an exact existing file and page:

```sh
python3 tools/design_type_review_graph.py \
  --file-key FILE_KEY \
  --page-id PAGE_ID \
  --baseline-only \
  --out .figma-flow/type-review-graph.json
```

The generated graph binds the private scope to the current pinned API audit and priority inventory. The proposed manifest row remains a local working artifact and is not added to the shared recipe catalog. It requires `reviewGraph: true` and `runtimeHelpers: false`. Project the generated graph through the `project_graph` and `typescript_projection` helpers in `tools/review_graph.py` so the recipe receives `FLOW_REVIEW_GRAPH`, `FLOW_REVIEW_GRAPH_SHA256`, and `FLOW_REVIEW_SELECTION_SHA256`.

The graph was assembled from the pinned 0.28 audit and the 0.29 observation graph. Its queue source can be replayed with:

```sh
python3 tools/api_priority.py build --baseline-only --out .figma-flow/api-priority-baseline.json
python3 tools/api_priority.py queue --inventory .figma-flow/api-priority-baseline.json --receiver TEXT --limit 10000
python3 tools/api_priority.py queue --inventory .figma-flow/api-priority-baseline.json --receiver FRAME --limit 10000
python3 tools/api_priority.py queue --inventory .figma-flow/api-priority-baseline.json --receiver PluginAPI --limit 10000
```

The included PluginAPI rows place `listAvailableFontsAsync` at queue position 24 and `createComponentFromNode` at 25. Text range readers begin at 63; range setters follow at 70. Frame `effects` and `dashPattern` appear at 19 and 34. Corner radius, fills, strokes, and stroke weight already have 0.29 graph evidence. The recipe checks every API key, owner, feasibility class, and receiver against the injected graph before using it.

The specimen selects an available font from the actual Figma editor, applies font name, size, line height, letter spacing, and fill to separate text ranges, then checks those values through the matching range getters. It also reads back the frame's CSS summary, radius, effects, dash pattern, fills, and stroke weight before converting only its newly created frame to a component. Visible engineer metadata records the selected member IDs, queue ranks, source, and actual getter results.

Local verification compiles the TypeScript source against the pinned Plugin API declarations and runs the focused graph/source checks. The recipe still needs execution in the registered Figma lab to verify actual fonts, visual layout, getter values, and repeated-run behavior.
