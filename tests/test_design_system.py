import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("design_system", ROOT / "tools/design_system.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DesignSystemTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "examples/review-design/design.json").read_text())

    def test_semantic_change_reaches_css_and_previews(self):
        self.data["tokens"]["color"]["brand"]["$value"] = "#123456"
        design = module.compile_design(self.data)
        html, css = module.render(design, True)
        svg = module.render_svg(design, design["screens"][1], True)
        self.assertIn("--color-brand: #123456", css)
        self.assertIn("background: var(--color-brand)", html)
        self.assertIn('#123456', svg)
        self.assertEqual(design["tokens"]["color.brand"]["value"], "#123456")

    def test_svg_uses_component_dimensions_and_font_tokens(self):
        tokens = self.data["tokens"]
        tokens["space"]["round"]["$value"] = "20px"
        tokens["space"]["card"]["$value"] = "24px"
        tokens["font"]["size"]["$value"] = "18px"
        tokens["font"]["body"]["$value"] = "Verdana"
        styles = self.data["components"]["button"]["variants"]["primary"]
        styles["font-size"] = "font.size"
        styles["font-family"] = "font.body"
        design = module.compile_design(self.data)
        svg = module.render_svg(design, design["screens"][1], True)
        html, css = module.render(design, True)
        self.assertIn('rx="20"', svg)
        self.assertIn('x="48"', svg)
        self.assertIn('font-size="18"', svg)
        self.assertIn('font-family="Verdana"', svg)
        self.assertIn('--space-round: 20px', css)
        self.assertIn('font-size: var(--font-size)', html)

    def test_independent_legacy_styles_keep_historical_sorted_css_bytes(self):
        design = module.compile_design(self.data)
        expected = []
        for name, component in design['components'].items():
            for variant, styles in component['variants'].items():
                declarations = '; '.join(f"{prop}: var({design['tokens'][token]['css_name']})" for prop, token in sorted(styles.items()))
                expected.append(f'.{name}--{variant} {{ {declarations}; }}')
        self.assertEqual(module.components_css(design), '\n'.join(expected) + '\n')
        for component in design['components'].values():
            for variant, styles in component['variants'].items():
                component['variants'][variant] = dict(reversed(list(styles.items())))
        self.assertEqual(module.components_css(design), '\n'.join(expected) + '\n')

    def test_axis_padding_gap_and_declaration_order_match_css_and_svg(self):
        self.data['tokens']['space'].update({'x': {'$type': 'dimension', '$value': '24px'},
                                            'y': {'$type': 'dimension', '$value': '14px'},
                                            'gap': {'$type': 'dimension', '$value': '6px'}})
        props = self.data['components']['button']['variants']['primary']
        props.update({'padding-inline': 'space.x', 'padding-block': 'space.y', 'gap': 'space.gap'})
        design = module.compile_design(self.data)
        css = next(line for line in module.components_css(design).splitlines() if line.startswith('.button--primary '))
        self.assertIn('gap: var(--space-gap)', css)
        self.assertLess(css.index('padding: var('), css.index('padding-inline: var('))
        svg = module.render_svg(design, design['screens'][1], True)
        self.assertIn('x="48"', svg)
        # With the uniform declaration last, it overrides both axes in all outputs.
        padding = props.pop('padding')
        props['padding'] = padding
        design = module.compile_design(self.data)
        css = next(line for line in module.components_css(design).splitlines() if line.startswith('.button--primary '))
        self.assertLess(css.index('padding-inline: var('), css.index('padding: var('))
        padding_value = float(design['tokens'][padding]['value'][:-2])
        svg = module.render_svg(design, design['screens'][1], True)
        self.assertIn(f'x="{24 + padding_value:g}"', svg)

    def test_svg_defaults_to_single_inter_family_without_changing_tokens(self):
        design = module.compile_design(self.data)
        for styled in (False, True):
            for screen in design["screens"]:
                svg = ET.fromstring(module.render_svg(design, screen, styled))
                families = {text.attrib["font-family"] for text in svg.findall("{http://www.w3.org/2000/svg}text")}
                self.assertEqual(families, {"Inter"})
        self.assertEqual(design["tokens"]["font.body"]["value"], "Arial")

    def test_dtcg_objects_inheritance_and_alias_css(self):
        self.data["tokens"]["palette"]["$type"] = "color"
        self.data["tokens"]["palette"]["$description"] = "Palette"
        self.data["tokens"]["palette"]["blue"] = {"$value": {"colorSpace": "srgb", "components": [0.5, 0.25, 1], "alpha": 0.5}, "$description": "Blue"}
        self.data["tokens"]["space"]["card"]["$value"] = {"value": 1.25, "unit": "rem"}
        design = module.compile_design(self.data)
        self.assertEqual(design["tokens"]["color.brand"]["value"], "#8040ff80")
        self.assertEqual(design["tokens"]["color.brand"]["alias"], "palette.blue")
        self.assertEqual(design["tokens"]["space.card"]["value"], "1.25rem")
        _, css = module.render(design, True)
        self.assertIn("--color-brand: var(--palette-blue);", css)
        self.assertIn("--palette-blue: #8040ff80;", css)
        self.assertIn(".button--primary", module.components_css(design))
        self.assertIn("background: var(--color-brand)", module.components_css(design))

    def test_color_range_unsupported_values_and_collisions(self):
        for value in ({"colorSpace": "srgb", "components": [1.01, 0, 0]},
                      {"colorSpace": "srgb", "components": [0, 0, 0], "alpha": -0.1},
                      {"colorSpace": "display-p3", "components": [0, 0, 0]},
                      {"colorSpace": "srgb", "components": [True, 0, 0]},
                      {"colorSpace": "srgb", "components": [0, 0, 0], "hex": "evil"}):
            data = copy.deepcopy(self.data)
            data["tokens"]["palette"]["blue"]["$value"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.compile_design(data)
        data = copy.deepcopy(self.data)
        data["tokens"]["palette-blue"] = {"$type": "color", "$value": "#000000"}
        with self.assertRaisesRegex(ValueError, "collision"):
            module.compile_design(data)
        data = copy.deepcopy(self.data)
        data["components"]["a--b"] = {"variants": {"c": {"color": "color.text"}}}
        data["components"]["a"] = {"variants": {"b--c": {"color": "color.text"}}}
        with self.assertRaisesRegex(ValueError, "collision"):
            module.compile_design(data)

    def test_untrusted_text_is_escaped_and_css_values_rejected(self):
        self.data["screens"][0]["elements"][0]["text"] = '<script>alert("x")</script>'
        design = module.compile_design(self.data)
        html, _ = module.render(design, True)
        svg = module.render_svg(design, design["screens"][0], True)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<script>", svg)
        self.data["tokens"]["font"]["body"]["$value"] = "Arial; color:red"
        with self.assertRaises(ValueError):
            module.compile_design(self.data)

    def test_invalid_aliases_and_components(self):
        for value in ("{missing.token}", "{color.brand}", "{space.card}"):
            data = copy.deepcopy(self.data)
            data["tokens"]["color"]["brand"]["$value"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.compile_design(data)
        self.data["screens"][0]["elements"][-1]["variant"] = "unknown"
        with self.assertRaises(ValueError):
            module.compile_design(self.data)

    def test_output_is_new_and_invalid_input_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "out"
            command = [sys.executable, str(ROOT / "tools/design_system.py"), "--input", str(ROOT / "examples/review-design/design.json"), "--out", str(out)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertTrue((out / "SCR-CARDS-LIST-styled.svg").exists())
            self.assertIn(".button--primary", (out / "components.css").read_text())
            before = {p.name: p.read_bytes() for p in out.iterdir()}
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})
            invalid = Path(temp) / "bad.json"
            invalid.write_text('{"version":1}')
            bad_out = Path(temp) / "bad-out"
            result = subprocess.run([sys.executable, str(ROOT / "tools/design_system.py"), "--input", str(invalid), "--out", str(bad_out)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(bad_out.exists())


if __name__ == "__main__":
    unittest.main()
