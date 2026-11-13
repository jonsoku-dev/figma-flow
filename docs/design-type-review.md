# Typography specimen in Figma Design

The recipe adds a reusable local component to an existing Design page. It includes a display style, body text, a caption, and a text layer with developer metadata. Each style records its native font, size, line height, letter spacing and fill. A planner can trace each demonstrated API back to its member in the priority graph.

## Build the scoped developer plugin

Choose the destination file and page. Run these commands from the installation root with an existing local output directory. The first command binds the public template to that destination and records the exact current inventory and member keys. Keep the resulting file private. [Public template](../library/figma-recipes/design-type-review.graph.json)

```sh
python3 tools/design_type_review_graph.py --file-key FILE_KEY --page-id PAGE_ID \
  --out .figma-flow/type-review-graph.json
python3 tools/figma_sdk_project.py init .figma-flow/type-review-sdk \
  --editor figma --recipe design-type-review --review-graph .figma-flow/type-review-graph.json
npm --prefix .figma-flow/type-review-sdk install --ignore-scripts --no-audit --no-fund
python3 tools/figma_sdk_project.py build .figma-flow/type-review-sdk
```

Use the Figma-issued development plugin ID in the generated manifest. Open the selected Design file and page, then run the built plugin. The SDK enables file-key readback for this recipe so it can verify the destination before writing. The regular Figma Flow menu and this graph-scoped SDK recipe have separate entry points. For the historical priority ranking, pass `--baseline-only` to the graph generator.

## Actual editor result

The default graph selected 24 nodes and 23 edges. In the Design editor, the recipe created one main component with four editable text layers and selected the same component on repeat. Actual style readback reported Inter at 30/36, 17/25 and 11/16 pixels for font size and line height. The component also reported a 560-pixel width, 16-pixel corner radius, drop shadow, one-pixel stroke, and an 8/4 dash pattern. The metadata contains the 19 exact API member IDs and the graph and selection hashes. [Release verification](editable-web-verification.md#api-observations)
