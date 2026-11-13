# Official Widget API typings

Unmodified MIT-licensed Figma Widget API 1.13.0 declarations are pinned to
`8815555bab1cf358ee9958fe2fa2cf46f77f3fb6` in `source.json` with per-file SHA-256.
`upstream-package.json` preserves the original package metadata. `index.d.ts`
extends the official Plugin API with `figma.widget`; `widget-api-standalone.d.ts`
is also preserved for explicit type imports. Neither file is an implementation.

Use `tools/figma_widget_project.py` to verify/search the pinned source or create
a separate local Widget API counter project. See `docs/figma-widget.md` for
build and Figma desktop import steps. Generated widgets do not share or replace
the registered Figma Flow workspace. No source update or remote request happens
automatically. Updating the source requires an explicit upstream pin/hash review.
