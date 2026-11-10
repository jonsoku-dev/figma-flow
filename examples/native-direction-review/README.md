# Two directions for a community workshop

This is a self-contained **test/demo**, not a game or finished design. It compares a welcome bulletin with a session agenda. Each has an overview, details, and a real return action in desktop/mobile layouts. All paths are relative. `previews/*.png` are deterministic Pillow drawings, **not browser captures, generated final artwork, or live Figma evidence**.

Run from the plugin package root with Python, Pillow and Node.js available:

```sh
python3 examples/native-direction-review/demo.py --out ./workshop-review
```

The command copies this example to a **new** directory, checks its source/Pillow proposals, and records an explicitly limited fixture-source agent review. It supplies **no `--review-destination`**. The normal default must stop at `NATIVE_REVIEW_PENDING`; no direction is selected or approved and nothing is registered in Figma.

Use **your existing local development plugin ID** to prepare a portable reviewer:

```sh
python3 tools/design_actions.py prepare-native-review \
  --manifest workshop-review/review/directions.json \
  --out workshop-review/reviewer \
  --plugin-id YOUR_EXISTING_LOCAL_PLUGIN_ID
```

Use the returned `plugin/manifest.json` with that local plugin in your own currently open Design file. Click **검토 시안 만들기** (some versions label it **A/B/C 검토 시안 만들기**), then **결과 JSON 저장**. Read the ordinary **주석 읽기** boards and their links in **Design mode**. Paid Dev Mode, hooks, Computer Use, a remote Figma API, and any other project's private setup are unnecessary.

Validate the actual saved getter result before asking a person to choose:

```sh
python3 tools/design_actions.py verify-native-review \
  --manifest workshop-review/review/directions.json \
  --readback PATH_TO_YOUR_SAVED_READBACK.json
```

Preparing a package is not evidence of a Figma run. The example includes no managed human transcript or selection certificate. Human selection and all production remain separate gates. Source HTML is runnable locally; actual browser/font rendering and live Figma behavior are not certified by the demo.

Since 0.17.0 both directions follow [the visual quality requirements](../../skills/figma-flow/references/visual-quality.md): every entry screen has a visual anchor (a sun illustration made of `ellipse` layers for the bulletin, a clock and dotted timeline for the agenda), every shape declares a `role`, cards use `radius` and `stroke`, and the two directions differ in composition, type scale and color. `python3 tools/design_quality.py --layout examples/native-direction-review/native-layout.json` reports 0 errors and 0 warnings; the 0.16.1 version of this example had 23 warnings (`missing-role`, `no-visual-anchor`, `type-scale`, `ornament-heavy`). The Pillow previews draw the same radius, stroke, ellipse and opacity values, but they remain approximations, not Figma rendering.

`candidate-spec.json` pins the sources and `native-layout.json` declares fonts, colors, per-state editable layers/control boxes, and preview asset hashes. Edit these in your copied project, not in the installed example. To reproduce the shipped demo inputs only: `python3 examples/native-direction-review/demo.py --regenerate-fixture`.

The source graph also pins actual native role bindings: `type/body → size/body` is FLOAT 16 on body text and component/instance labels; `type/family/body → font/family/body` is STRING Inter on the same text. `space/content → space/base` is FLOAT 24 on actual control left/right padding, and `radius/control → radius/base` is FLOAT 6 on mains and screen instances. Desktop and mobile are both explicit. Headings, note boards and explanatory palette typography remain auxiliary uses, separate from these role claims; the button's vertical padding stays 14.

The generator rejects missing role targets and mismatched actual field values before writing graph pins. Run `python3 -B -m unittest discover -s examples/native-direction-review -p test_demo.py` from the plugin root for byte parity and source preflight checks. These checks produce no native, browser or user-choice evidence.
