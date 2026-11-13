# FigJam review planner recipe

`figjam-review-planner` turns the selected review graph into a canvas scene. The graph is the sole source for the notes, links, table rows, and evidence code block. The recipe does not maintain a second example graph.

## Scene

- One wide sticky note names the graph and displays its SHA-256 revision.
- One wide sticky note per graph node shows its kind, status, title, detail, and semantic ID.
- A FigJam table lists every node's kind and status, ID, title, and designer/developer note.
- A JSON code block records the graph ID and SHA-256, node IDs, and semantic edges.
- A labelled connector joins each graph edge's endpoint sticky notes.

Each authored top-level node carries private plugin data for the recipe ID, graph SHA-256, and semantic ID. Node IDs are preserved as `node:<graph-node-id>`. Edge IDs are serialized from the edge's stable endpoint IDs and type; display titles are not used as identifiers. The JSON block and plugin data provide document readback for the projected graph revision.

## Bounds and reruns

The recipe accepts 1–24 graph nodes and at most 48 visible edges. A graph outside those limits fails before writing nodes; select a smaller review scope and retry. It preserves full titles and details in the canonical graph hash. Sticky notes and table cells shorten long text for display.

Running the same graph SHA-256 on the same page with the same development plugin ID selects and zooms to the existing complete board without creating a duplicate. If only part of that revision remains, the recipe refuses to add another partial copy. A new graph SHA-256 creates a new board revision and preserves earlier boards for comparison.

The recipe requires FigJam in `default` mode. It uses the current page and viewport, makes no network or filesystem calls, creates no pages, and does not edit or remove pre-existing nodes. If creation or readback fails, it removes only nodes created by that run and restores the original selection when still on the same page.

The recipe compiled against the pinned Figma Plugin API declarations and ran on a disposable FigJam board. A 20-node, 16-edge graph created 21 stickies, one table with 84 table cells, one code block, and 16 connectors. A same-SHA rerun selected the existing board and left the node count at 123, so the retry created no duplicates. This confirms the tested board and graph shape; other graph sizes still rely on the bounds and failure cleanup above.
