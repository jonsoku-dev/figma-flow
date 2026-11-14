"""NF-01 component families compile, validation, preview, and readback-compare tests."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from design_system import compile_design, compile_graph_component_families, render, render_svg
from figma_bridge import compare_declared_component_properties, validate
from graph_design_system import load_graph, resolve_design_system
from graph_sync import commit_component_fields, native_property, sync_selected_component_fields

FIXTURES = ROOT / "tests" / "fixtures" / "nf01"


def apply_invalid_patch(source, patch):
    data = copy.deepcopy(source)
    kind = patch["kind"]
    if kind == "replace-family-id":
        data["componentFamilies"][patch["index"]]["id"] = patch["value"]
    elif kind == "replace-family-version":
        data["componentFamilies"][patch["index"]]["version"] = patch["value"]
    elif kind == "replace-family-layout":
        entry = next(f for f in data["componentFamilies"] if f["id"] == patch["family"])
        entry["layout"] = patch["value"]
    elif kind == "add-undeclared-component-variant":
        comp = data["components"][patch["component"]]
        comp["variants"][patch["variant"]] = copy.deepcopy(next(iter(comp["variants"].values())))
    elif kind == "set-element-override":
        element = next(e for e in data["screens"][0]["elements"] if e.get("id") == patch["element_id"])
        element.setdefault("property_values", {})[patch["prop_id"]] = patch["value"]
    elif kind == "set-family-allowed-ids":
        entry = next(f for f in data["componentFamilies"] if f["id"] == patch["family"])
        prop = next(p for p in entry["properties"] if p["id"] == patch["prop_id"])
        prop["allowedFamilyIds"] = patch["value"]
    elif kind == "set-family-default":
        entry = next(f for f in data["componentFamilies"] if f["id"] == patch["family"])
        prop = next(p for p in entry["properties"] if p["id"] == patch["prop_id"])
        prop["default_value"] = patch["value"]
    else:
        raise AssertionError(f"Unknown patch kind: {kind}")
    return data


class ComponentFamiliesCompileTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((FIXTURES / "six-families.json").read_text(encoding="utf-8"))
        self.invalid_cases = json.loads((FIXTURES / "invalid-cases.json").read_text(encoding="utf-8"))["cases"]

    def test_six_canonical_families_compile_and_preserve_input(self):
        snapshot = copy.deepcopy(self.source)
        compiled = compile_design(self.source)
        validate(compiled)
        self.assertEqual(self.source, snapshot, "compile_design must never mutate caller input")
        self.assertEqual(compiled["status"], "ready")
        self.assertEqual(
            [item["id"] for item in compiled["componentFamilies"]],
            ["input", "checkbox", "radio", "field", "table-cell", "table-row"],
        )
        self.assertEqual(compiled["components"]["field"]["layout"], "VERTICAL")
        self.assertEqual(compiled["components"]["checkbox"]["layout"], "HORIZONTAL")
        self.assertEqual(compiled["components"]["radio"]["layout"], "HORIZONTAL")
        self.assertEqual(compiled["components"]["table-row"]["layout"], "HORIZONTAL")
        self.assertEqual(
            compiled["components"]["field"]["swap_targets"],
            ["input", "checkbox", "radio"],
        )
        self.assertEqual(
            compiled["components"]["table-row"]["swap_targets"],
            ["table-cell"],
        )
        # Duplicate display names ('Cell') are preserved on distinct property IDs ('firstCell', 'secondCell').
        row_props = compiled["components"]["table-row"]["properties"]
        self.assertEqual(row_props["firstCell"]["name"], "Cell")
        self.assertEqual(row_props["secondCell"]["name"], "Cell")
        self.assertNotEqual(row_props["firstCell"]["target"], row_props["secondCell"]["target"])
        # DOM correspondence metadata is preserved on screen elements.
        self.assertEqual(
            compiled["screens"][0]["elements"][0]["dom_source"]["label_for"],
            "participant_name",
        )
        self.assertEqual(
            compiled["screens"][0]["elements"][2]["dom_source"]["th_scope"],
            "row",
        )

    def test_status_lifecycle_unmapped_to_mapped_to_ready_and_legacy_omission(self):
        # 1. Omitting componentFamilies keeps exact 4-key legacy output.
        legacy = copy.deepcopy(self.source)
        legacy.pop("componentFamilies")
        for element in legacy["screens"][0]["elements"]:
            element.pop("property_values", None)
            element.pop("dom_source", None)
        compiled_legacy = compile_design(legacy)
        self.assertEqual(sorted(compiled_legacy), ["components", "screens", "tokens", "version"])

        # 2. Unmapped family -> status == 'unmapped'
        unmapped = copy.deepcopy(legacy)
        unmapped["componentFamilies"] = [{
            "id": "field",
            "version": 1,
            "axes": {"state": ["default", "error", "disabled"]},
            "properties": [{"id": "label", "type": "TEXT", "targetKey": "field-label"}],
        }]
        unmapped["components"] = {"button": {"variants": {"default": {"color": "color.ink"}}}}
        unmapped["screens"] = [{
            "id": "home",
            "title": "Home",
            "trace": ["NF-01"],
            "elements": [{"kind": "text", "text": "Placeholder"}],
        }]
        compiled_unmapped = compile_design(unmapped)
        self.assertEqual(compiled_unmapped["status"], "unmapped")
        self.assertEqual(compiled_unmapped["family_preview"][0]["status"], "unmapped")

        # 3. Mapped family with zero screen instances -> status == 'mapped'
        mapped = copy.deepcopy(self.source)
        mapped["screens"] = [{
            "id": "empty-family-screen",
            "title": "Mapped only",
            "trace": ["NF-01"],
            "elements": [{"kind": "heading", "text": "No instances placed yet"}],
        }]
        compiled_mapped = compile_design(mapped)
        self.assertEqual(compiled_mapped["status"], "mapped")
        self.assertTrue(all(row["status"] == "mapped" for row in compiled_mapped["family_preview"]))

    def test_invalid_fixtures_fail_before_any_output_is_written(self):
        for case in self.invalid_cases:
            with self.subTest(case=case["name"]):
                bad = apply_invalid_patch(self.source, case["patch"])
                with self.assertRaisesRegex(ValueError, case["expected_error"]):
                    compile_design(bad)
                with tempfile.TemporaryDirectory() as tmp:
                    src = Path(tmp) / "bad.json"
                    out = Path(tmp) / "out"
                    src.write_text(json.dumps(bad), encoding="utf-8")
                    proc = subprocess.run(
                        [sys.executable, "-B", str(ROOT / "tools" / "design_system.py"), "--input", str(src), "--out", str(out)],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                    )
                    self.assertNotEqual(proc.returncode, 0)
                    self.assertFalse(out.exists(), f"Failed case {case['name']} must write zero files")

    def test_secret_and_private_paths_rejected_in_overrides_and_dom_source(self):
        for bad_val in (
            "sk-live-abcdef1234567890ABCD",
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "/Users/alice/private/design.json",
            "password=supersecretvalue",
        ):
            bad = copy.deepcopy(self.source)
            bad["screens"][0]["elements"][0]["property_values"]["helpText"] = bad_val
            with self.assertRaisesRegex(ValueError, "Secret, credential, or private path"):
                compile_design(bad)

    def test_html_and_svg_previews_render_text_boolean_and_swap_slots(self):
        compiled = compile_design(self.source)
        html_doc, _css = render(compiled, True)
        self.assertIn("Participant name", html_doc)
        self.assertIn("Required for workshop check-in.", html_doc)
        # showHelp=false on field-session-choice hides the default help text
        self.assertEqual(html_doc.count("Use the name shown on booking confirmation."), 0)
        self.assertIn("input--focus", html_doc)
        self.assertIn("radio--disabled", html_doc)
        # showSecondCell=false hides cell-1 while keeping cell-0 header
        self.assertIn("table-cell--header", html_doc)
        self.assertNotIn('data-slot="cell-1"', html_doc)

        svg_doc = render_svg(compiled, compiled["screens"][0], True)
        self.assertIn("Participant name", svg_doc)
        self.assertIn("<svg", svg_doc)

    def test_compile_graph_component_families_from_design_and_graph(self):
        contract = compile_graph_component_families(
            self.source,
            owner_key="nf01.demo",
            position={"x": 1440, "y": 40},
        )
        self.assertEqual(contract["schema"], "figma-flow-semantic-family-contract-v1")
        self.assertEqual(contract["mode"], "additive-family-workbench")
        set_ids = [s["id"] for s in contract["componentSets"]]
        # Leaf families must appear before composite families referencing them
        self.assertLess(set_ids.index("nf01.demo/set:input"), set_ids.index("nf01.demo/set:field"))
        self.assertLess(set_ids.index("nf01.demo/set:checkbox"), set_ids.index("nf01.demo/set:field"))
        self.assertLess(set_ids.index("nf01.demo/set:radio"), set_ids.index("nf01.demo/set:field"))
        self.assertLess(set_ids.index("nf01.demo/set:table-cell"), set_ids.index("nf01.demo/set:table-row"))
        self.assertEqual(len(contract["instances"]), 3)
        self.assertEqual(contract["instances"][0]["domSource"]["label_for"], "participant_name")

        # Graph-shaped input with componentFamilies + family_instances
        graph_input = {
            "version": 1,
            "nodes": [{"id": "screen-form", "type": "screen", "title": "Form"}],
            "edges": [],
            "design_foundations": {
                "version": 1,
                "roles": [{"name": "Body", "kind": "typography", "token": "type/family/body", "value": "Hahmlet", "native": {"type": "STRING", "value": "Hahmlet"}}],
            },
            "componentFamilies": copy.deepcopy(self.source["componentFamilies"]),
            "family_instances": [
                {
                    "id": "login-email-field",
                    "component": "field",
                    "variant": "default",
                    "text": "Email",
                    "property_values": {
                        "label": "Email address",
                        "showHelp": True,
                        "control": {"component": "input", "variant": "default"},
                    },
                    "dom_source": {"selector": "input#id_email", "label_for": "id_email", "required": True},
                }
            ],
        }
        graph_contract = compile_graph_component_families(graph_input, owner_key="littlehands.nf01")
        self.assertEqual(graph_contract["workbench"]["font"]["family"], "Hahmlet")
        self.assertEqual(len(graph_contract["componentSets"]), 6)
        self.assertEqual(graph_contract["instances"][0]["key"], "littlehands.nf01/instance:login-email-field")

    def test_compare_declared_properties_handles_text_boolean_swap_and_duplicate_names(self):
        minimal = {
            "version": 1,
            "tokens": {"color": {"ink": {"$type": "color", "$value": "#112233"}}},
            "componentFamilies": [
                {
                    "id": "table-cell",
                    "version": 1,
                    "axes": {"state": ["default"]},
                    "properties": [{"id": "cellText", "name": "Text", "type": "TEXT", "targetKey": "label", "default_value": "Cell"}],
                },
                {
                    "id": "table-row",
                    "version": 1,
                    "axes": {"state": ["default"]},
                    "properties": [
                        {"id": "c0", "name": "Cell", "type": "INSTANCE_SWAP", "targetKey": "col-0", "allowedFamilyIds": ["table-cell"]},
                        {"id": "c1", "name": "Cell", "type": "INSTANCE_SWAP", "targetKey": "col-1", "allowedFamilyIds": ["table-cell"]},
                        {"id": "note", "name": "Note", "type": "TEXT", "targetKey": "row-note", "default_value": "Default note"},
                        {"id": "showNote", "name": "Show note", "type": "BOOLEAN", "targetKey": "row-note", "default_value": True},
                    ],
                },
            ],
            "components": {
                "table-cell": {"variants": {"default": {"color": "color.ink"}}},
                "table-row": {"variants": {"default": {"color": "color.ink"}}},
            },
            "screens": [{
                "id": "s1",
                "title": "S1",
                "trace": ["NF-01"],
                "elements": [{
                    "id": "row-inst",
                    "kind": "component",
                    "component": "table-row",
                    "variant": "default",
                    "text": "Row",
                    "property_values": {"note": "Edited note", "showNote": False},
                }],
            }],
        }
        expected = compile_design(minimal)
        page = {
            "id": "0:1",
            "type": "PAGE",
            "children": [
                {
                    "id": "1:0",
                    "type": "COMPONENT_SET",
                    "componentPropertyDefinitions": {
                        "Text#10": {"type": "TEXT", "defaultValue": "Cell"},
                    },
                    "children": [{
                        "id": "1:1",
                        "type": "COMPONENT",
                        "component_key": "ck-cell",
                        "semantic_id": "component:table-cell/default",
                        "declared_metadata": {"declared_property_keys": {"cellText": "Text#10"}},
                        "children": [{
                            "id": "1:2",
                            "type": "TEXT",
                            "semantic_id": "component:table-cell/default/label",
                            "characters": "Cell",
                            "componentPropertyReferences": {"characters": "Text#10"},
                        }],
                    }],
                },
                {
                    "id": "2:0",
                    "type": "COMPONENT_SET",
                    "componentPropertyDefinitions": {
                        "Cell#20": {"type": "INSTANCE_SWAP", "defaultValue": "1:1", "preferredValues": [{"type": "COMPONENT", "key": "ck-cell"}]},
                        "Cell#21": {"type": "INSTANCE_SWAP", "defaultValue": "1:1", "preferredValues": [{"type": "COMPONENT", "key": "ck-cell"}]},
                        "Note#22": {"type": "TEXT", "defaultValue": "Default note"},
                        "Show note#23": {"type": "BOOLEAN", "defaultValue": True},
                    },
                    "children": [{
                        "id": "2:1",
                        "type": "COMPONENT",
                        "component_key": "ck-row",
                        "semantic_id": "component:table-row/default",
                        "declared_metadata": {
                            "declared_property_keys": {
                                "c0": "Cell#20",
                                "c1": "Cell#21",
                                "note": "Note#22",
                                "showNote": "Show note#23",
                            }
                        },
                        "children": [
                            {"id": "2:2", "type": "TEXT", "semantic_id": "component:table-row/default/label", "characters": "table-row"},
                            {"id": "2:3", "type": "INSTANCE", "semantic_id": "component:table-row/default/slot:col-0", "main_component_id": "1:1", "componentPropertyReferences": {"mainComponent": "Cell#20"}},
                            {"id": "2:4", "type": "INSTANCE", "semantic_id": "component:table-row/default/slot:col-1", "main_component_id": "1:1", "componentPropertyReferences": {"mainComponent": "Cell#21"}},
                            {"id": "2:5", "type": "TEXT", "semantic_id": "component:table-row/default/text:row-note", "characters": "Default note", "visible": True, "componentPropertyReferences": {"characters": "Note#22", "visible": "Show note#23"}},
                        ],
                    }],
                },
                {
                    "id": "3:0",
                    "type": "FRAME",
                    "semantic_id": "s1",
                    "children": [{
                        "id": "3:1",
                        "type": "INSTANCE",
                        "semantic_id": "row-inst",
                        "main_component_id": "2:1",
                        "componentProperties": {
                            "Cell#20": {"type": "INSTANCE_SWAP", "value": "1:1"},
                            "Cell#21": {"type": "INSTANCE_SWAP", "value": "1:1"},
                            "Note#22": {"type": "TEXT", "value": "Edited note"},
                            "Show note#23": {"type": "BOOLEAN", "value": False},
                        },
                        "children": [
                            {"id": "3:2", "type": "TEXT", "semantic_id": "row-inst/label", "characters": "Row"},
                            {"id": "3:3", "type": "INSTANCE", "semantic_id": "row-inst/slot:col-0", "main_component_id": "1:1"},
                            {"id": "3:4", "type": "INSTANCE", "semantic_id": "row-inst/slot:col-1", "main_component_id": "1:1"},
                            {"id": "3:5", "type": "TEXT", "semantic_id": "row-inst/text:row-note", "characters": "Edited note", "visible": False},
                        ],
                    }],
                },
            ],
        }
        checks = compare_declared_component_properties(page, expected)
        self.assertTrue(checks)
        self.assertEqual({c["status"] for c in checks}, {"match"}, [c for c in checks if c["status"] != "match"])

    def test_dom_source_allowlist_and_tall_family_screen_svg_bounds(self):
        rich = copy.deepcopy(self.source)
        rich["screens"][0]["elements"][0]["dom_source"].update({
            "placeholder": "Enter participant full name",
            "help_id": "help_participant_name",
            "aria_describedby": "help_participant_name",
            "name": "participant_name",
            "readonly": False,
        })
        # Duplicate elements to exceed 640px vertical height in a single form+table screen
        base_elements = copy.deepcopy(rich["screens"][0]["elements"])
        for extra_idx in range(2):
            for el in base_elements:
                dup = copy.deepcopy(el)
                dup["id"] = f"{el['id']}-extra-{extra_idx}"
                rich["screens"][0]["elements"].append(dup)
        compiled = compile_design(rich)
        svg_doc = render_svg(compiled, compiled["screens"][0], True)
        self.assertIn("<svg", svg_doc)
        self.assertNotIn('height="640"', svg_doc)

        bad_url = copy.deepcopy(self.source)
        bad_url["screens"][0]["elements"][0]["dom_source"]["selector"] = "https://example.invalid/form"
        with self.assertRaisesRegex(ValueError, "external URL forbidden"):
            compile_design(bad_url)

    def test_selective_sync_cas_for_field_and_table_row_boolean_swap_and_text(self):
        field_spec = {
            "schema": "figma-flow-component-field-v1",
            "component": {"id": "participant-field", "node_id": "inst:field-1", "main_component_id": "comp:field-default"},
            "fields": [
                {
                    "field": "label",
                    "type": "TEXT",
                    "property_key": "Label#field:label",
                    "token": "nf01/field/label",
                    "before": "Participant name",
                    "after": "Attendee full name",
                },
                {
                    "field": "showHelp",
                    "type": "BOOLEAN",
                    "property_key": "Show help#field:showHelp",
                    "token": "nf01/field/show-help",
                    "before": True,
                    "after": False,
                },
                {
                    "field": "control",
                    "type": "INSTANCE_SWAP",
                    "property_key": "Control#field:control",
                    "token": "nf01/field/control-swap",
                    "allowed_swap_ids": ["comp:input-default", "comp:checkbox-checked", "comp:radio-selected"],
                    "before": "comp:input-default",
                    "after": "comp:checkbox-checked",
                },
                {
                    "field": "helpText",
                    "type": "TEXT",
                    "property_key": "Help#field:helpText",
                    "token": "nf01/field/help-text",
                    "before": "As shown on roster",
                    "after": "Unselected edit must stay untouched",
                },
            ],
        }
        row_spec = {
            "schema": "figma-flow-component-field-v1",
            "component": {"id": "roster-row-1", "node_id": "inst:row-1", "main_component_id": "comp:row-default"},
            "fields": [
                {
                    "field": "primaryCell",
                    "type": "TEXT",
                    "property_key": "Cell#row:cell0",
                    "token": "nf01/row/primary-cell",
                    "before": "Sample row",
                    "after": "Confirmed participant",
                },
                {
                    "field": "showSecondCell",
                    "type": "BOOLEAN",
                    "property_key": "Show second#row:showSecondCell",
                    "token": "nf01/row/show-second",
                    "before": True,
                    "after": True,
                },
            ],
        }
        field_observed = {
            "label": "Participant name",
            "showHelp": True,
            "control": "comp:input-default",
            "helpText": "As shown on roster",
        }
        row_observed = {
            "primaryCell": "Sample row",
            "showSecondCell": True,
        }

        # Python vs JS commitComponentFields parity on selective TEXT + BOOLEAN + INSTANCE_SWAP
        py_field = commit_component_fields(field_spec, ["label", "showHelp", "control"], field_observed)
        js_runner = (
            "const {commitComponentFields} = require('./figma-bridge/graph_token_sync.js');"
            "const input = JSON.parse(process.argv[1]);"
            "process.stdout.write(JSON.stringify(commitComponentFields(input.spec, input.selection, input.observed)));"
        )
        completed = subprocess.run(
            ["node", "--eval", js_runner, json.dumps({
                "spec": field_spec,
                "selection": ["control", "label", "showHelp"],
                "observed": field_observed,
            })],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(completed.stdout), py_field)
        self.assertEqual(py_field["values"]["helpText"], "As shown on roster")
        self.assertNotIn("helpText", py_field["baseline"])
        self.assertFalse(py_field["full_apply"])
        self.assertEqual(py_field["applied"][2]["property_key"], "Control#field:control")

        # Stale BOOLEAN / INSTANCE_SWAP CAS and disallowed swap target leave observed untouched
        stale_bool = dict(field_observed, showHelp=False)
        stale_before = copy.deepcopy(stale_bool)
        with self.assertRaisesRegex(ValueError, "stale before value: showHelp"):
            commit_component_fields(field_spec, ["showHelp"], stale_bool)
        self.assertEqual(stale_bool, stale_before)

        bad_type_observed = dict(field_observed, showHelp=1)
        with self.assertRaisesRegex(ValueError, "stale before value: showHelp"):
            commit_component_fields(field_spec, ["showHelp"], bad_type_observed)

        bad_swap_spec = copy.deepcopy(field_spec)
        bad_swap_spec["fields"][2]["after"] = "comp:table-row-default"
        with self.assertRaisesRegex(ValueError, "disallowed swap target: control"):
            commit_component_fields(bad_swap_spec, ["control"], field_observed)

        # End-to-end selective sync of 1 Field + 1 TableRow into canonical graph.json + generated web ESM module
        with tempfile.TemporaryDirectory() as tmp:
            graph_path = Path(tmp) / "graph.json"
            web_path = Path(tmp) / "tokens.mjs"
            graph_doc = {
                "design_system": {
                    "version": 1,
                    "tokens": {
                        "nf01/field/label": {"type": "STRING", "value": "Participant name"},
                        "nf01/field/show-help": {"type": "BOOLEAN", "value": True},
                        "nf01/field/control-swap": {"type": "STRING", "value": "comp:input-default"},
                        "nf01/field/help-text": {"type": "STRING", "value": "As shown on roster"},
                        "nf01/row/primary-cell": {"type": "STRING", "value": "Sample row"},
                        "nf01/row/show-second": {"type": "BOOLEAN", "value": True},
                    },
                    "components": {
                        "participant-field-help": {
                            "properties": {
                                "visible": "nf01/field/show-help",
                                "characters": "nf01/field/help-text",
                            },
                            "web": {"selector": "#help_participant_name"},
                        },
                        "participant-field": {
                            "properties": {
                                "characters": "nf01/field/label",
                                "instanceSwap": "nf01/field/control-swap",
                            },
                            "web": {"selector": "label#label_participant_name"},
                        },
                        "roster-row-1": {
                            "properties": {
                                "characters": "nf01/row/primary-cell",
                                "visible": "nf01/row/show-second",
                            },
                            "web": {"selector": "tr#roster-row-1"},
                        },
                    },
                }
            }
            graph_path.write_text(json.dumps(graph_doc, indent=2) + "\n", encoding="utf-8")
            initial_sha = load_graph(graph_path).source_sha256

            synced = sync_selected_component_fields(
                graph_path,
                [
                    {"spec": field_spec, "selection": ["label", "showHelp", "control"], "observed": field_observed},
                    {"spec": row_spec, "selection": ["primaryCell"], "observed": row_observed},
                ],
                initial_sha,
                web_module=web_path,
            )
            updated_resolved = resolve_design_system(load_graph(graph_path))
            self.assertEqual(updated_resolved["graphSha256"], synced["graph_sha256"])
            self.assertEqual(updated_resolved["tokens"]["nf01/field/label"], "Attendee full name")
            self.assertIs(updated_resolved["tokens"]["nf01/field/show-help"], False)
            self.assertEqual(updated_resolved["tokens"]["nf01/field/control-swap"], "comp:checkbox-checked")
            self.assertEqual(updated_resolved["tokens"]["nf01/row/primary-cell"], "Confirmed participant")
            # Unselected helpText and showSecondCell remain untouched
            self.assertEqual(updated_resolved["tokens"]["nf01/field/help-text"], "As shown on roster")
            self.assertIs(updated_resolved["tokens"]["nf01/row/show-second"], True)
            self.assertIn("#help_participant_name { display: none; }", updated_resolved["graphStylesheet"])
            self.assertTrue(web_path.is_file())
            self.assertIn("Attendee full name", web_path.read_text(encoding="utf-8"))

        # Native property reader supports visible, characters, and instanceSwap
        self.assertEqual(native_property({"id": "n1", "type": "TEXT", "visible": False}, "visible"), (False, None))
        self.assertEqual(native_property({"id": "n2", "type": "TEXT", "characters": "Cell value"}, "characters"), ("Cell value", None))
        self.assertEqual(
            native_property(
                {
                    "id": "n3",
                    "type": "INSTANCE",
                    "componentProperties": {"Control#1:0": {"type": "INSTANCE_SWAP", "value": "comp:radio-selected"}},
                },
                "instanceSwap",
            ),
            ("comp:radio-selected", None),
        )


if __name__ == "__main__":
    unittest.main()
