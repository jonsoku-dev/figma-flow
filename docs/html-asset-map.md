# HTML asset map format

`input_effect.project()` can bind an already captured, same-origin HTTP asset to a local file. Use this opt-in path when the saved HTML references root-absolute or optimized assets that the normal local path resolver rejects.

The projector does not fetch the page or its assets. The selected project must already contain the exact saved HTML body, a page response metadata file, asset response capture files, the local source files, and the map manifest. The map pins those files in the resulting input record.

The HTML parser follows `img` and `source` `srcset` candidates, SVG `image` `href` values, linked stylesheets, and statically parsed CSS `@import` and `url()` references. It does not run JavaScript or resolve dynamically created references.

## Add the map to a project spec

Set `inputs.html-asset-map` next to `inputs.html`:

```python
spec = {
    'schema': 'figma-flow-input-effect-v1',
    'brief': 'brief.md',
    'facts': 'facts.json',
    'authority': 'authority.json',
    'inputs': {
        'html': 'captures/index.html',
        'html-asset-map': 'captures/html-asset-map.json',
    },
}
record = input_effect.project(project_root, spec)
input_effect.write_record(project_root, record, 'evidence/input-record.json')
```

The map requires an HTML input. Other HTML inputs keep the existing behavior. Root-absolute paths remain `rejected` unless the map binds the exact captured request to a local file. Remote URLs remain `external-unverified` and cannot appear in a map.

## Pin the captured page and assets

The manifest uses `figma-flow-html-asset-map-v1`:

```json
{
  "schema": "figma-flow-html-asset-map-v1",
  "page_capture": {
    "metadata_path": "captures/http-response.json",
    "metadata_sha256": "<sha256 of the metadata file>"
  },
  "local_root": "app",
  "assets": [
    {
      "id": "hero-image-1x",
      "capture_path": "captures/asset-responses.json",
      "capture_sha256": "<sha256 of the capture file>",
      "reference": "/_next/image?url=%2Fimages%2Fhero.png&w=640&q=75",
      "request_target": "/_next/image?url=%2Fimages%2Fhero.png&w=640&q=75",
      "local_app_path": "public/images/hero.png",
      "mapping": "transformed",
      "reason": "The same-origin image optimizer changed the response bytes; this points to the pinned local original."
    }
  ]
}
```

The page metadata file must record `url_final`, `http_status: 200`, and `body_sha256`. The body hash must match the exact bytes in the selected HTML file.

Each asset capture file contains an `assets` array, an `origin`, and `external_assets_requested: 0`. The capture origin must match the page origin. A matching row must have the exact `reference`, `http_status: 200`, response byte count and SHA-256, `local_app_path`, `local_sha256`, and `bytes_match_local`.

`request_target` stores the exact same-origin path and query sent to the server. It has no scheme, host, or fragment. Query order and values must match the captured reference. For a relative URL in CSS, set `base_target` to the path and query of the stylesheet request. The projector resolves the CSS URL from that base. A Next.js `/_next/image` entry is rejected if its nested `url` parameter points at a different origin.

`local_root` is a directory inside the project root. `local_app_path` is a file inside that directory. The projector checks the local file's SHA against the capture row. It rejects symlinks, traversal, and missing files.

Use `mapping: "byte-identical"` only when the response and local file have the same byte count and SHA-256. Use `mapping: "transformed"` when a same-origin service changed the response bytes, such as a Next.js image optimizer. A transformed entry needs a reason. The record stores both hashes and does not claim byte equality.

## Freshness and limits

The v4 input record pins the HTML file, manifest, page and asset capture metadata, and each mapped local file. `input_effect.freshness(record, root)` reports `stale` if any pinned file changes. Existing v3 records remain readable and keep their existing freshness checks. Regenerate v1 and v2 records as before.

An unlisted same-origin request keeps its default status. The projector also rejects maps with unused targets, duplicate targets, mismatched capture data, and cross-origin references. It never performs HTTP requests. The capture metadata is the selected local evidence; the projector does not independently authenticate who produced it.

The map records asset provenance and local file freshness. It does not render HTML, execute JavaScript, verify CSS cascade, compare transformed output pixels, or import assets into Figma. `visual_quality` remains `unverified`.
