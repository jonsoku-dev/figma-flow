"""Small native getter regressions; synthetic identifiers, no Figma access required."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import figma_draft as draft


def fixture():
    layers = [
        dict(
            id="heading",
            kind="text",
            value="함께 만드는 더 좋은 시작",
            x=16,
            y=99,
            w=311.47,
            h=39,
            size=32,
            leading=39,
            font="display",
            ink="ink",
        ),
        dict(
            id="body",
            kind="text",
            value="모아 팀의 다음 협업을 시작하세요.",
            x=16,
            y=150.19,
            w=215.22,
            h=19,
            size=16,
            leading=19,
            font="body",
            ink="ink",
        ),
    ]
    candidate = {
        "id": "candidate",
        "colors": {"ink": "#000000"},
        "fonts": {
            "display": {"family": "Noto Sans KR", "style": "Bold"},
            "body": {"family": "Noto Sans KR", "style": "Regular"},
        },
        "state_layouts": {
            "mobile": {"idle": {"width": 390, "height": 800, "layers": layers, "control_boxes": {}}}
        },
        "prototype": {"bindings": [], "states": [{"id": "idle"}]},
        "control_styles": {"mobile": {}},
        "action_notes": {},
        "action_labels": {},
    }
    frame = {
        "id": "frame",
        "type": "FRAME",
        "parentId": "page",
        "x": 0,
        "y": 0,
        "width": 390,
        "height": 800,
    }
    nodes = {"candidate.mobile.idle": frame}
    for layer in layers:
        nodes["candidate.mobile.idle." + layer["id"]] = {
            "id": layer["id"],
            "type": "TEXT",
            "parentId": "frame",
            "x": layer["x"],
            "y": layer["y"],
            "width": layer["w"],
            "height": layer["h"],
            "characters": layer["value"],
            "fontName": candidate["fonts"][layer["font"]],
            "fontSize": layer["size"],
            "lineHeight": {"unit": "PIXELS", "value": layer["leading"]},
            "letterSpacing": {"unit": "PERCENT", "value": 0},
            "textAutoResize": "HEIGHT",
            "textAlignHorizontal": "LEFT",
        }
    return candidate, frame, nodes


def findings(candidate, frame, nodes):
    return draft.native_screen_findings(candidate, "mobile", "idle", frame, nodes)


class NativeGeometryTests(unittest.TestCase):
    def test_saved_mui_failure_pair_redacted_and_good_allocation(self):
        # Authored/readback numbers from the saved MUI mobile heading/body pair.
        candidate, frame, nodes = fixture()
        self.assertEqual(findings(candidate, frame, nodes), [])
        nodes["candidate.mobile.idle.heading"]["height"] = 78
        nodes["candidate.mobile.idle.body"]["height"] = 38
        codes = {x["code"] for x in findings(candidate, frame, nodes)}
        self.assertTrue({"text-overflow", "text-overlap"} <= codes)

    def test_saved_shadcn_failure_pair_redacted(self):
        candidate, frame, nodes = fixture()
        layers = candidate["state_layouts"]["mobile"]["idle"]["layers"]
        for layer, values in zip(
            layers, [(41, 172, 240.69, 31, 25, 36.25, 73), (41, 220, 137.64, 17, 14, 25.2, 51)]
        ):
            x, y, w, h, size, leading, rendered = values
            layer.update(x=x, y=y, w=w, h=h, size=size, leading=leading)
            nodes["candidate.mobile.idle." + layer["id"]].update(
                x=x,
                y=y,
                width=w,
                height=rendered,
                fontSize=size,
                lineHeight={"unit": "PIXELS", "value": leading},
            )
        self.assertTrue(
            {"text-overflow", "text-overlap"}
            <= {x["code"] for x in findings(candidate, frame, nodes)}
        )

    def test_height_slot_may_be_larger_than_rendered_box(self):
        candidate, frame, nodes = fixture()
        candidate["state_layouts"]["mobile"]["idle"]["layers"][0]["h"] = 48
        self.assertEqual(findings(candidate, frame, nodes), [])

    def test_geometry_typography_and_max_lines_drift(self):
        mutations = [
            ("x", 30, "geometry-drift"),
            ("width", 200, "geometry-drift"),
            ("height", 81, "text-overflow"),
            ("fontName", {"family": "Wrong", "style": "Bold"}, "text-font-drift"),
            ("fontSize", 33, "text-font-drift"),
            ("lineHeight", {"unit": "AUTO"}, "text-lineHeight-drift"),
            ("letterSpacing", {"unit": "PIXELS", "value": 2}, "text-letterSpacing-drift"),
            ("textAlignHorizontal", "CENTER", "text-alignment-drift"),
            ("parentId", "wrong", "parent-drift"),
            ("textAutoResize", "NONE", "text-resize-drift"),
        ]
        for field, value, code in mutations:
            with self.subTest(field=field):
                candidate, frame, nodes = fixture()
                nodes["candidate.mobile.idle.heading"][field] = value
                self.assertIn(code, {x["code"] for x in findings(candidate, frame, nodes)})
        candidate, frame, nodes = fixture()
        layer = candidate["state_layouts"]["mobile"]["idle"]["layers"][0]
        layer.update(h=80, max_lines=1)
        nodes["candidate.mobile.idle.heading"]["height"] = 78
        self.assertIn("text-max-lines", {x["code"] for x in findings(candidate, frame, nodes)})
        candidate, frame, nodes = fixture()
        nodes["candidate.mobile.idle.heading"]["y"] = -10
        self.assertIn("off-canvas", {x["code"] for x in findings(candidate, frame, nodes)})

    def test_letter_spacing_pixels_and_percent_equivalence(self):
        candidate, frame, nodes = fixture()
        candidate["state_layouts"]["mobile"]["idle"]["layers"][0]["letter_spacing"] = -0.32
        nodes["candidate.mobile.idle.heading"]["letterSpacing"] = {"unit": "PERCENT", "value": -1}
        self.assertEqual(findings(candidate, frame, nodes), [])

    def test_optional_text_contract_rejects_invalid_values(self):
        candidate, _, _ = fixture()
        base = candidate["state_layouts"]["mobile"]["idle"]["layers"][0]
        for field, values in [
            ("max_lines", [0, -1, 1.5, True]),
            ("letter_spacing", [True, float("inf"), "1"]),
            ("leading", [0, float("nan")]),
            ("align", ["middle"]),
        ]:
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    draft.check_layer(
                        dict(base, **{field: value}), {"ink": "#000000"}, {}, "screen"
                    )
        draft.check_layer(
            dict(base, letter_spacing=-0.5, max_lines=1), {"ink": "#000000"}, {}, "screen"
        )

    def test_optional_shadow_schema_and_native_readback_fidelity(self):
        shadow = {"x": 0, "y": 2, "blur": 6, "spread": -1, "color": "#2E7D32", "opacity": 0.24}
        effect = {
            "type": "DROP_SHADOW",
            "visible": True,
            "blendMode": "NORMAL",
            "showShadowBehindNode": True,
            "offset": {"x": 0, "y": 2},
            "radius": 6,
            "spread": -1,
            "color": {"r": 46 / 255, "g": 125 / 255, "b": 50 / 255, "a": 0.24},
        }
        for kind in ("rect", "ellipse"):
            layer = {
                "id": "surface",
                "kind": kind,
                "x": 0,
                "y": 0,
                "w": 100,
                "h": 40,
                "fill": "ink",
                "shadows": [shadow],
            }
            draft.check_layer(layer, {"ink": "#000000"}, {}, "screen")
            self.assertEqual(
                draft._native_shadow_findings({"effects": [effect]}, layer, "screen.surface"), []
            )
            for field, value in (
                ("blur", -1),
                ("x", "1"),
                ("opacity", 1.1),
                ("color", "red"),
                ("extra", 1),
            ):
                with self.subTest(kind=kind, field=field), self.assertRaises(ValueError):
                    draft.check_layer(
                        dict(layer, shadows=[dict(shadow, **{field: value})]),
                        {"ink": "#000000"},
                        {},
                        "screen",
                    )
        self.assertEqual(draft._native_shadow_findings({}, {}, "legacy"), [])
        self.assertEqual(
            draft._native_shadow_findings({"effects": []}, {"shadows": []}, "empty"), []
        )
        for field, value in (
            ("visible", False),
            ("blendMode", "MULTIPLY"),
            ("type", "INNER_SHADOW"),
            ("showShadowBehindNode", False),
            ("offset", {"x": 0, "y": 3}),
            ("spread", 0),
            ("radius", 5),
            ("color", {"r": 0, "g": 0, "b": 0, "a": 0.24}),
            ("color", {"r": 46 / 255, "g": 125 / 255, "b": 50 / 255, "a": 1}),
        ):
            with self.subTest(field=field):
                self.assertTrue(
                    draft._native_shadow_findings(
                        {"effects": [dict(effect, **{field: value})]},
                        {"shadows": [shadow]},
                        "shape",
                    )
                )
        self.assertTrue(
            draft._native_shadow_findings({"effects": []}, {"shadows": [shadow]}, "dropped")
        )
        second = dict(shadow, y=4)
        self.assertTrue(
            draft._native_shadow_findings(
                {"effects": [dict(effect, offset={"x": 0, "y": 4}), effect]},
                {"shadows": [shadow, second]},
                "reordered",
            )
        )
        rounded = copy.deepcopy(effect)
        rounded["color"]["g"] += 0.0000001
        self.assertEqual(
            draft._native_shadow_findings(
                {"effects": [rounded]}, {"shadows": [shadow]}, "float-color"
            ),
            [],
        )

    def test_shape_shadow_is_required_by_normal_screen_findings(self):
        candidate, frame, nodes = fixture()
        layer = {
            "id": "surface",
            "kind": "rect",
            "x": 0,
            "y": 0,
            "w": 100,
            "h": 40,
            "fill": "ink",
            "shadows": [
                {"x": 0, "y": 0, "blur": 0, "spread": 2, "color": "#000000", "opacity": 0.1}
            ],
        }
        candidate["state_layouts"]["mobile"]["idle"]["layers"].append(layer)
        nodes["candidate.mobile.idle.surface"] = {
            "id": "surface",
            "parentId": "frame",
            "type": "RECTANGLE",
            "x": 0,
            "y": 0,
            "width": 100,
            "height": 40,
            "effects": [],
        }
        self.assertIn("shadow-drift", {item["code"] for item in findings(candidate, frame, nodes)})

    def test_reusable_product_button_label_fit_and_source(self):
        candidate, frame, nodes = fixture()
        state = candidate["state_layouts"]["mobile"]["idle"]
        state["product_buttons"] = {
            "send": {"box": [16, 250, 200, 44], "variant": "Primary", "label": "Send"}
        }
        candidate["control_styles"]["mobile"]["Primary"] = {
            "fontSize": 14,
            "paddingX": 12,
            "paddingY": 10,
            "radius": 4,
        }
        nodes["candidate.mobile.component.Primary"] = {"id": "main", "type": "COMPONENT"}
        nodes["candidate.mobile.idle.send"] = {
            "id": "send",
            "type": "INSTANCE",
            "parentId": "frame",
            "mainComponentId": "main",
            "cornerRadius": 4,
            "x": 16,
            "y": 250,
            "width": 200,
            "height": 44,
            "paddingLeft": 12,
            "paddingRight": 12,
            "paddingTop": 10,
            "paddingBottom": 10,
        }
        nodes["candidate.mobile.idle.send.label"] = {
            "id": "label",
            "type": "TEXT",
            "parentId": "send",
            "x": 12,
            "y": 11,
            "width": 176,
            "height": 22,
            "characters": "Send",
            "fontName": candidate["fonts"]["body"],
            "fontSize": 14,
            "lineHeight": {"unit": "PIXELS", "value": 22},
            "letterSpacing": {"unit": "PIXELS", "value": 0},
            "textAlignHorizontal": "CENTER",
            "textAutoResize": "HEIGHT",
        }
        self.assertEqual(findings(candidate, frame, nodes), [])
        shadow_candidate = copy.deepcopy(candidate)
        shadow_candidate["control_styles"]["mobile"]["Primary"]["shadows"] = [
            {"x": 0, "y": 1, "blur": 2, "spread": 0, "color": "#000000", "opacity": 0.2}
        ]
        self.assertIn(
            "shadow-drift", {item["code"] for item in findings(shadow_candidate, frame, nodes)}
        )
        for target, field, value, code in [
            ("send.label", "height", 44, "control-label-overflow"),
            ("send", "visible", False, "visibility-drift"),
            ("send", "opacity", 0, "visibility-drift"),
            ("send.label", "visible", False, "visibility-drift"),
            ("send.label", "opacity", 0, "visibility-drift"),
            ("send.label", "parentId", "foreign-control", "control-label-missing"),
            ("send.label", "height", 23.1, "text-max-lines"),
            ("send.label", "textAutoResize", "NONE", "text-resize-drift"),
            ("send", "cornerRadius", 20, "control-shape-drift"),
            ("send.label", "x", 13.1, "control-label-alignment"),
            ("send", "width", 205, "geometry-drift"),
            ("send", "mainComponentId", "foreign", "control-source-drift"),
            ("send", "reactions", [{"trigger": {}}], "product-control-reaction"),
        ]:
            changed = copy.deepcopy(nodes)
            changed["candidate.mobile.idle." + target][field] = value
            self.assertIn(code, {x["code"] for x in findings(candidate, frame, changed)})

    def test_malformed_native_geometry_and_typography_fail_closed(self):
        for field in ("x", "y", "width", "height"):
            for value in (None, "12", [], {}, True, float("nan")):
                with self.subTest(field=field, value=value):
                    candidate, frame, nodes = fixture()
                    nodes["candidate.mobile.idle.heading"][field] = value
                    self.assertIn(
                        "geometry-missing",
                        {item["code"] for item in findings(candidate, frame, nodes)},
                    )
        for field in ("width", "height"):
            candidate, frame, nodes = fixture()
            nodes["candidate.mobile.idle.heading"].pop(field)
            self.assertIn(
                "geometry-missing", {item["code"] for item in findings(candidate, frame, nodes)}
            )
        for field in ("fontName", "lineHeight", "letterSpacing"):
            candidate, frame, nodes = fixture()
            nodes["candidate.mobile.idle.heading"][field] = ["mixed"]
            self.assertTrue(findings(candidate, frame, nodes))

    def test_visibility_and_screen_ownership_fail_closed(self):
        for key in ("candidate.mobile.idle", "candidate.mobile.idle.heading"):
            for field, value in (
                ("visible", False),
                ("opacity", 0),
                ("opacity", None),
                ("opacity", "1"),
            ):
                with self.subTest(key=key, field=field, value=value):
                    candidate, frame, nodes = fixture()
                    nodes[key][field] = value
                    self.assertIn(
                        "visibility-drift",
                        {item["code"] for item in findings(candidate, frame, nodes)},
                    )
        candidate, frame, nodes = fixture()
        self.assertEqual(
            draft.native_screen_findings(candidate, "mobile", "idle", frame, nodes, page_id="page"),
            [],
        )
        frame["parentId"] = "foreign-page"
        self.assertIn(
            "parent-drift",
            {
                item["code"]
                for item in draft.native_screen_findings(
                    candidate, "mobile", "idle", frame, nodes, page_id="page"
                )
            },
        )
        for field, value in (("x", "0"), ("y", None), ("width", 0), ("height", -1)):
            candidate, frame, nodes = fixture()
            frame[field] = value
            self.assertIn(
                "geometry-missing", {item["code"] for item in findings(candidate, frame, nodes)}
            )

    def test_duplicate_required_native_keys_and_ids_are_rejected(self):
        candidate, _, nodes = fixture()
        packet = {"candidates": [candidate]}
        rows = [dict(node, semanticKey=key) for key, node in nodes.items()]
        for duplicate in (
            dict(rows[0], id="another-frame"),
            dict(rows[1], id="another-heading"),
            dict(rows[0], semanticKey="other-key"),
        ):
            with self.subTest(duplicate=duplicate), self.assertRaisesRegex(ValueError, "Duplicate"):
                draft._native_readback_nodes({"nodes": rows + [duplicate]}, packet)
        # Legacy palette helper keys can repeat; only required screen/source keys must be unique.
        extras = [
            {"id": "palette-one", "semanticKey": "review.palette.sample"},
            {"id": "palette-two", "semanticKey": "review.palette.sample"},
        ]
        draft._native_readback_nodes({"nodes": rows + extras}, packet)

    def test_failure_diagnostics_are_never_admitted_as_readback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "failure.json"
            path.write_text(
                json.dumps({"schema": "figma-flow-native-geometry-failure-v1", "passed": False})
            )
            report = draft.verify_native_review("unused-manifest", path)
        self.assertFalse(report["passed"])
        self.assertIn("not an admissible readback", report["errors"][0])

    def test_review_annotation_font_is_required_even_with_explicit_layer_fonts(self):
        candidate, _, _ = fixture()
        candidate["fonts"].pop("body")
        errors = draft.layout_errors({"candidates": [candidate]})
        self.assertTrue(any("annotation font role missing: body" in error for error in errors))

    def test_product_button_preflight_rejects_bad_geometry_identity_and_style(self):
        candidate, _, _ = fixture()
        candidate["control_styles"]["mobile"]["Primary"] = {
            "fontSize": 14,
            "paddingX": 12,
            "paddingY": 10,
            "radius": 4,
            "minHeight": 44,
            "maxWidth": 350,
        }
        candidate["state_layouts"]["mobile"]["idle"]["product_buttons"] = {
            "send": {"box": [16, 250, 200, 44], "variant": "Primary", "label": "Send"}
        }
        authored = {"candidates": [candidate]}
        self.assertEqual(draft.layout_errors(authored), [])
        malformed_shadow = copy.deepcopy(authored)
        malformed_shadow["candidates"][0]["control_styles"]["mobile"]["Primary"]["shadows"] = [
            {"x": 0}
        ]
        self.assertTrue(any("shadows" in error for error in draft.layout_errors(malformed_shadow)))
        for field, value in [("box", [0, 0, -1, 44]), ("variant", "unknown"), ("label", "")]:
            changed = copy.deepcopy(authored)
            changed["candidates"][0]["state_layouts"]["mobile"]["idle"]["product_buttons"]["send"][
                field
            ] = value
            self.assertTrue(draft.layout_errors(changed))
        changed = copy.deepcopy(authored)
        buttons = changed["candidates"][0]["state_layouts"]["mobile"]["idle"]["product_buttons"]
        buttons["heading"] = buttons.pop("send")
        self.assertTrue(any("collides" in p for p in draft.layout_errors(changed)))

    def test_verifier_returns_actionable_findings_before_admitting_screen(self):
        candidate, frame, nodes = fixture()
        nodes["candidate.mobile.idle.heading"]["height"] = 78
        packet = {
            "scope": "exploratory-only",
            "production_admitted": False,
            "fileKey": None,
            "instance_sha256": "instance",
            "packet_sha256": "packet",
            "candidate_pins": {},
            "candidates": [candidate],
        }
        rows = [{"id": "page", "type": "PAGE"}] + [dict(v, semanticKey=k) for k, v in nodes.items()]
        raw = {
            "fileKey": "synthetic",
            "pageId": "page",
            "page_owner": "instance",
            "instance_sha256": "instance",
            "packet_sha256": "packet",
            "candidate_pins": {},
            "scope": "exploratory-only",
            "production_admitted": False,
            "nodes": rows,
        }
        with tempfile.TemporaryDirectory() as temp, patch.object(
            draft, "_attested_review_packet", return_value=packet
        ):
            path = Path(temp) / "readback.json"
            path.write_text(json.dumps(raw))
            report = draft.verify_native_review("manifest", path)
        self.assertFalse(report["passed"])
        self.assertTrue(report["layout_findings"])
        self.assertTrue(any("candidate.mobile.idle.heading" in error for error in report["errors"]))
        self.assertEqual(report["screens"], [])

    def test_failure_ui_downloads_full_diagnostics_without_readback_submission(self):
        import re

        script = re.search(
            r"<script>([\s\S]*)</script>",
            draft.ui_html({"url": "http://localhost/synthetic", "capability": "synthetic"}),
        ).group(1)
        harness = r"""
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const elements = Object.fromEntries(['make', 'save', 'status', 'status-panel', 'status-title', 'status-body', 'status-details', 'workspace-locale'].map(id => [id, {disabled: id === 'save', dataset: {}, setAttribute(name,value){this[name]=value;}, removeAttribute(name){delete this[name];}, addEventListener(name,callback){this['on'+name]=callback;}}]));
const downloads = [];
const blobs = [];
const posts = [];
let requests = 0;
const translations=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const context = {
  FlowUI:{locale:'ko',apply(){},t:key=>translations[key].ko,setLocale(){}},
  document: {documentElement:{dataset:{}},querySelectorAll:()=>[],getElementById: id => elements[id], createElement: () => ({click() {downloads.push(this.download);}})},
  window: {addEventListener(){}}, parent: {postMessage: message => posts.push(message)},
  Blob: class {constructor(parts) {this.parts = parts; blobs.push(this);}},
  URL: {createObjectURL: () => 'blob:synthetic', revokeObjectURL() {}},
  fetch: async () => {requests++; return {ok: true, json: async () => ({passed: true})};}
};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const receive = message => context.window.onmessage({data: {pluginMessage: message}});
(async () => {
  const diagnostic = {schema: 'figma-flow-native-geometry-failure-v1', passed: false,
    findings: [{layer: 'candidate.mobile.idle.heading', authored: {w: 240}, actual: {w: 240, h: 73}, naturalWidth: 260, message: 'details'.repeat(500)}]};
  await receive({type: 'geometry-failure', data: diagnostic});
  assert.equal(elements.save.disabled, false);
  assert(elements.status.textContent.includes(diagnostic.findings[0].message));
  await receive({type: 'status', busy: false, message: 'truncated failure'});
  assert(elements.status.textContent.includes(diagnostic.findings[0].message));
  elements.save.onclick();
  assert.equal(downloads[0], 'figma-direction-review-failure.json');
  assert.deepEqual(JSON.parse(blobs[0].parts[0]), diagnostic);
  assert.equal(requests, 0);
  elements.make.onclick();
  assert.equal(elements.save.disabled, true);
  elements.save.onclick();
  assert.equal(downloads.length, 1);
  assert(!elements.status.textContent.includes(diagnostic.findings[0].message));
  assert.equal(posts.at(-1).pluginMessage.type, 'draft-review');
  await receive({type: 'readback', data: {nodes: []}});
  assert.equal(requests, 1);
  elements.save.onclick();
  assert.equal(downloads.at(-1), 'figma-direction-review-readback.json');
  assert.equal(posts.at(-1).pluginMessage.type, 'receipt');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ui.js"
            shared = (ROOT / "figma-bridge/panel_components.js").read_text()
            path.write_text(shared + "\nconst PAIR = " + script.split("const PAIR = ", 1)[1])
            result = subprocess.run(
                ["node", "-e", harness, str(path), str(ROOT / "figma-bridge/locales/review.json")], capture_output=True, text=True
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_normal_verify_cli_cannot_advance_broken_screen_to_wait_selection(self):
        spec = importlib.util.spec_from_file_location(
            "native_demo", ROOT / "examples/native-direction-review/demo.py"
        )
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(demo.instantiate(Path(temp) / "project")["manifest"])
            before = manifest.read_bytes()
            packet = draft.make_packet(manifest)
            candidate = packet["candidates"][0]
            state = candidate["prototype"]["states"][0]["id"]
            key = candidate["id"] + ".desktop." + state
            layout = candidate["state_layouts"]["desktop"][state]
            raw = {
                k: packet[k]
                for k in [
                    "instance_sha256",
                    "packet_sha256",
                    "candidate_pins",
                    "scope",
                    "production_admitted",
                    "layout_pin",
                    "prepared_target",
                ]
            }
            raw.update(
                fileKey="synthetic",
                pageId="page",
                page_owner=packet["instance_sha256"],
                nodes=[
                    {"id": "page", "type": "PAGE"},
                    {
                        "id": "frame",
                        "semanticKey": key,
                        "type": "FRAME",
                        "width": layout["width"],
                        "height": layout["height"],
                    },
                ],
            )
            path = Path(temp) / "readback.json"
            path.write_text(json.dumps(raw))
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "tools/design_actions.py"),
                    "verify-native-review",
                    "--manifest",
                    str(manifest),
                    "--readback",
                    str(path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("layer-missing", result.stderr)
            self.assertEqual(before, manifest.read_bytes())
            self.assertNotEqual(
                json.loads(manifest.read_text())["workflow_symbol"], "WAIT_SELECTION"
            )


if __name__ == "__main__":
    unittest.main()
