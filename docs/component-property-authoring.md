# Declared component properties

The ordinary design-system source can declare native `BOOLEAN` visibility and
`INSTANCE_SWAP` properties. `tools/design_system.py` preserves them in
`resolved.json`; the ordinary reviewed `tools/figma_bridge.py` import creates
them on the owning component set (or main component when sets are unavailable).
Existing text properties and declared variant axes retain their existing path.

The generated HTML and static SVG previews use each instance's `property_values`
or the component defaults. They hide BOOLEAN-disabled labels and slots, show the
selected swap component with its variant styles, and use the instance text for
the root label. Designs without declared properties keep the existing preview
markup. Preview expansion is capped at 512 component nodes per screen; oversized
acyclic swap graphs fail before the output directory is created.

```json
{
  "properties": {
    "ShowLabel": {"type": "BOOLEAN", "target": "label", "default_value": true},
    "Symbol": {
      "type": "INSTANCE_SWAP",
      "target": "symbol",
      "default_value": {"component": "symbol", "variant": "circle"},
      "preferred_values": [
        {"component": "symbol", "variant": "circle"},
        {"component": "symbol", "variant": "square"}
      ]
    },
    "ShowSymbol": {"type": "BOOLEAN", "target": "symbol", "default_value": true}
  }
}
```

Put `properties` beside a component's `variants`. A swap declaration creates a
real nested instance named `slot:<target>` in every authored main variant.
`BOOLEAN.target` names `label` or one of that component's declared swap targets.
There is one native binding per target field. Defaults apply to every main
variant; individual screen instances can override them:

```json
{
  "id": "example", "kind": "component", "component": "button",
  "variant": "default", "text": "Continue",
  "property_values": {
    "ShowLabel": false,
    "Symbol": {"component": "symbol", "variant": "square"}
  }
}
```

Property names cannot contain `#`, reuse the owned text name `문구`, or collide
with a variant axis. Swap references must name local source component variants.
Recursive swap dependencies, including preferred targets and instance overrides,
are rejected. Remote keys, arbitrary descendant selectors, and undeclared
property overrides are unsupported. Preferred values guide Figma's picker; they
do not restrict a valid local override to that list.

The importer uses the returned suffixed native property key for references and
instance overrides. A swap default and override use the local main's node ID;
preferred values use its component key. Missing native APIs or retained values
fail the import and use the existing page/variable/style rollback. Preflight
runs before page creation. Source-hash reuse and explicit fresh-page rules are
unchanged. Fresh handoff verification checks source defaults and overrides against
actual definitions, references, preferred keys, instance values, visibility and
nested main IDs. Reusing the same imported page preserves valid user instance
overrides and verifies their live consistency without rewriting them. Explicit
readback comparison to the supplied source reports those edits as `changed` in
`component_property_checks`. Missing observed fields cannot pass from metadata
alone. These semantics follow the [Figma component-property API](https://developers.figma.com/docs/plugins/working-with-component-properties/).

## Reproduce

The minimal real source fixture is
[`tests/fixtures/declared-component-properties.json`](../tests/fixtures/declared-component-properties.json).
It contains one button, two local symbol variants, defaults, preferred swaps,
a hidden-label override, and a hidden-symbol override. Compile it through the
normal source path with a new output directory:

```sh
python3 tools/design_system.py \
  --input tests/fixtures/declared-component-properties.json \
  --out /tmp/figma-component-properties-source
```

Pass that output's `resolved.json`, its exact SHA256, and matching selected
product graph/selection to the normal reviewed bridge compile command described
in [`docs/guide.md`](guide.md). The normal selection, graph, palette coverage,
and native-write admission checks still apply; the fixture does not bypass them.
Run the resulting local plugin's ordinary import, then read back the page.
Verify property definitions and defaults on the main/set, `visible` and
`mainComponent` references on actual sublayers, preferred component keys, and
per-instance values plus actual nested main IDs and visibility. Import the same
source again to check page reuse. Automated API fixtures alone do not establish
live Figma acceptance.

Focused checks:

```sh
python3 -B -m unittest discover -s tests -p 'test_declared_component_properties*.py'
node --test tests/test_declared_component_properties.cjs tests/rd01_import_axes_acceptance.cjs
```
