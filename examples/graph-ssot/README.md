# Graph SSOT for a component

The graph owns token values once. Figma variables and generated web styles are projections. A pairing receipt pins native identities, alias topology, component consumers, baseline values and graph hash.

## Minimal graph shape

```json
{
  "version": 1,
  "nodes": [],
  "edges": [],
  "design_system": {
    "version": 1,
    "id": "my-product",
    "tokens": {
      "button/size": {"type": "FLOAT", "value": 14},
      "button/inline": {"type": "FLOAT", "value": 16},
      "button/family": {"type": "STRING", "value": "Noto Sans KR"}
    },
    "components": {
      "invite-button": {
        "properties": {
          "fontSize": "button/size",
          "fontFamily": "button/family",
          "paddingLeft": "button/inline",
          "paddingRight": "button/inline"
        },
        "native": {
          "mainKeys": ["invite.component.Primary"],
          "instanceKeys": ["invite.screen.submit"]
        },
        "web": {"selector": "#invite-submit"}
      }
    }
  }
}
```

Use actual existing semantic keys or exact native IDs. Multiple declared pages require design_system.native.allowed_page_ids; Figma IDs belong to your project and private pairing data. Keys can use aliases instead of values. Referenced token types must agree. Existing graphs without design_system retain their existing tools.

## Discover and adopt

Run from the plugin root. The discovery plugin only reads the explicitly selected pages. Values in commands below are placeholders for your actual file/page/ID.

```sh
python3 tools/graph_sync.py discover --file-key FILE --page-id PAGE   --include-page-id ADDITIONAL_INSTANCE_PAGE --plugin-id ASSIGNED_ID --out DISCOVERY
# Run DISCOVERY/manifest.json in Figma Desktop; save actual graph-native-discovery.json.
python3 tools/graph_sync.py export --adopt --graph PROJECT/graph.json   --native-readback ACTUAL_DISCOVERY.json --web-module PROJECT/web/graph-tokens.mjs   --plugin-id ASSIGNED_ID --out INITIAL_EXPORT
```

Adoption creates a graph-owned variable namespace and rebinds only declared consumers. Every existing instance of a controlled main must be declared. Existing shared variables and other components are preserved. Incremental adoption also takes --pairing PREVIOUS_RECEIPT and admits explicit new fields/tokens while retaining existing owned identities. Inspect the initial values and alias topology, then run Apply graph values and save the actual focused getter.

The web imports the generated module. Render graphStylesheet in a style element, or consume muiComponents in MUI sx. Never pass raw numeric padding through MUI spacing conversion. Stamp graphSha256 in data-graph-sha on each mapped element. export writes web-probe.js; execute its read-only DOM probe through the authorized browser and save the actual result.

```sh
python3 tools/graph_sync.py pair --graph PROJECT/graph.json   --plan INITIAL_EXPORT/native-plan.json --readback ACTUAL_NATIVE.json   --web-module PROJECT/web/graph-tokens.mjs --web-proof ACTUAL_WEB.json   --out PAIRING.json
```

A generated module's bytes alone cannot prove that the actual app consumed it.

## Graph to Figma and web

Edit canonical values with load_graph/update_graph_values or the source editor. export resolves aliases and projects web values. Apply in Figma performs exact scope/baseline checks and compensates its own partial writes; concurrent edits are preserved as conflicts.

```sh
python3 tools/graph_sync.py export --graph PROJECT/graph.json --pairing PAIRING.json   --web-module PROJECT/web/graph-tokens.mjs --plugin-id ASSIGNED_ID --out NEXT_EXPORT
# Apply graph values; save getter, run actual web probe; pair the resulting current graph.
```

## Designer edits to graph

A variable edit imports normally. Direct component/instance edits require component-wide promotion with --node-edit-scope component. Preview records affected native instances and web selectors. Divergent direct edits or simultaneous edits to the same token are conflicts.

```sh
python3 tools/graph_sync.py import --graph PROJECT/graph.json --pairing PAIRING.json   --readback ACTUAL_DESIGNER_EDIT.json --node-edit-scope component   --web-module PROJECT/web/graph-tokens.mjs --out PREVIEW
python3 tools/graph_sync.py import --graph PROJECT/graph.json --pairing PAIRING.json   --readback ACTUAL_DESIGNER_EDIT.json --node-edit-scope component   --web-module PROJECT/web/graph-tokens.mjs --out ACCEPTED --apply
python3 tools/graph_sync.py export --graph PROJECT/graph.json --pairing PAIRING.json   --native-readback ACTUAL_DESIGNER_EDIT.json --import-report ACCEPTED/import-report.json   --web-module PROJECT/web/graph-tokens.mjs --plugin-id ASSIGNED_ID --out REPAIR
# Apply the accepted repair; actual native/web verification and pair finish the transaction.
```

The importer updates graph roots and derived foundations, then publishes the web module under the same graph lock. Interruption between file replacements leaves a recovery journal and never advances pairing.

```sh
python3 tools/graph_sync.py recover --recovery ACCEPTED/recovery.json
```

Supported design properties are fontFamily/fontSize, padding sides, backgroundColor/color/borderColor, borderWidth/borderRadius, gap, and supported width/height/minimum dimensions. Colors are opaque solid RGB. Normal/disabled variants can have separate graph components/selectors with nonoverlapping property scopes. Width/height require existing FIXED sizing; HUG uses minimum constraints. Complex structural/vector redesign, mixed paints and style-backed paints require explicit modeling/migration and are not silently inferred.

This route is an explicit export/read/import workflow. It does not run an unauthenticated background writer, and it does not create human selection or production design acceptance records.
