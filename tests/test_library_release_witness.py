"""Offline witnesses for library pins, projections, and maintained catalogs."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import campaign_forms
import campaign_library
import figma_api_inventory
import figma_rest_inventory
import figma_sdk_project
import figma_widget_project
import route_design
import sync_workflow
import workflow
import workspace_recipes

sys.path.insert(0, str(ROOT / "library/figma-recipes"))
import recipe_design_graph


def pinned_compiler(env_names, expected_name):
    value = next((os.environ.get(name) for name in env_names if os.environ.get(name)), None)
    if not value:
        raise unittest.SkipTest(f"Set one of {', '.join(env_names)} to the pinned TypeScript 5.9.3 compiler")
    compiler = Path(value).resolve()
    package = json.loads((compiler.parent.parent / "package.json").read_text(encoding="utf-8"))
    if package.get("name") != "typescript" or package.get("version") != "5.9.3" or compiler.name != expected_name:
        raise AssertionError("The supplied compiler must be the pinned TypeScript 5.9.3 package")
    return compiler


class LibraryReleaseWitnessTests(unittest.TestCase):
    def _copy_recipe_build_tree(self, root):
        shutil.copytree(ROOT / "tools", root / "tools", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copytree(ROOT / "library", root / "library",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "node_modules"))
        shutil.copytree(ROOT / "figma-bridge/locales", root / "figma-bridge/locales")
        (root / "figma-bridge").mkdir(exist_ok=True)
        shutil.copyfile(ROOT / "figma-bridge/code.js", root / "figma-bridge/code.js")
        shutil.copyfile(ROOT / "figma-bridge/presentation.json", root / "figma-bridge/presentation.json")
        shutil.copytree(ROOT / "panel-ui/src", root / "panel-ui/src")
        shutil.copytree(ROOT / "skills/figma-flow/scripts", root / "skills/figma-flow/scripts")
        shutil.copytree(ROOT / "specs", root / "specs",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        (root / "tests/fixtures").mkdir(parents=True)
        shutil.copyfile(ROOT / "tests/fixtures/declared-component-properties.json",
                        root / "tests/fixtures/declared-component-properties.json")

    def _build_recipe_tree(self, root, compiler):
        build = root / "library/figma-recipes/build.py"
        result = subprocess.run([sys.executable, str(build), "--typescript", str(compiler)],
                                cwd=root, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_upstream_api_pins_and_rest_projection_are_offline_and_deterministic(self):
        try:
            import yaml
        except ImportError as exc:
            raise unittest.SkipTest("Install the pinned PyYAML 6.0.2 toolchain to regenerate REST inventory") from exc
        self.assertEqual(yaml.__version__, "6.0.2")
        plugin = figma_api_inventory.verify_source()
        widget = figma_widget_project.verify_source()
        rest_source, raw_rest = figma_rest_inventory.verify_source()
        self.assertEqual((plugin["version"], plugin["ref"]),
                         ("1.142.0", "dff4874ca083e18cd74835fd5afc5079d46866b7"))
        self.assertEqual((widget["version"], widget["ref"]),
                         ("1.13.0", "8815555bab1cf358ee9958fe2fa2cf46f77f3fb6"))
        self.assertEqual((rest_source["version"], rest_source["ref"]),
                         ("0.47.0", "af027cd20aca8326a41115e4d15bbdf875158e81"))
        self.assertEqual(hashlib.sha256(raw_rest).hexdigest(), rest_source["source_sha256"])
        self.assertEqual(figma_rest_inventory.canonical(figma_rest_inventory.build()),
                         figma_rest_inventory.INDEX.read_text(encoding="utf-8"))
        rest_requirements = (ROOT / "library/figma-rest/requirements.txt").read_text(encoding="utf-8")
        self.assertEqual("PyYAML==6.0.2\n", rest_requirements)
        self.assertEqual(gzip.decompress((ROOT / "library/figma-rest/openapi.yaml.gz").read_bytes()), raw_rest)

    def test_plugin_api_index_and_static_status_snapshot_rebuild_from_pinned_typescript(self):
        typescript = pinned_compiler(("FIGMA_API_TYPESCRIPT", "FIGMA_SDK_TEST_TYPESCRIPT"), "typescript.js")
        package = json.loads((ROOT / "library/figma-api/package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["private"], True)
        self.assertEqual(package["devDependencies"], {"typescript": "5.9.3"})
        catalog = figma_api_inventory.build(str(typescript))
        self.assertEqual(figma_api_inventory.canonical(catalog),
                         figma_api_inventory.INDEX.read_text(encoding="utf-8"))
        result = figma_api_inventory.coverage(catalog, str(typescript))
        compact = {key: value for key, value in result.items() if key != "members"}
        compact["members"] = [{key: row[key] for key in ("id", "status", "implementation", "runtime_acceptance")}
                              for row in result["members"]]
        baseline = json.loads((ROOT / "library/figma-api/coverage-baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(compact, baseline)
        self.assertTrue(all(row["implementation"] == "unverified" and row["runtime_acceptance"] == "unverified"
                            for row in result["members"]))

    def test_recipe_manifest_and_bundle_inventory_have_closed_pinned_entries(self):
        recipes = ROOT / "library/figma-recipes"
        manifest = json.loads((recipes / "manifest.json").read_text(encoding="utf-8"))
        bundle = json.loads((recipes / "bundle.json").read_text(encoding="utf-8"))
        entries = {row["id"]: row for row in manifest["recipes"]}
        compiled = {row["id"]: row for row in bundle["recipes"]}
        self.assertEqual(set(entries), set(compiled) | {row["id"] for row in bundle["sdkGraphRecipes"]})
        for identifier, row in entries.items():
            source = (recipes / row["entry"]).read_text(encoding="utf-8")
            self.assertIn(f"RECIPE_VISUALS['{identifier}']", source)
        for identifier, row in compiled.items():
            with self.subTest(recipe=identifier):
                source = recipes / row["source"]
                target = recipes / row["entry"]
                self.assertEqual(row["sourceSha256"], hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertEqual(row["jsSha256"], hashlib.sha256(target.read_bytes()).hexdigest())
                self.assertEqual(entries[identifier]["entry"], row["source"])
        helper = next(row for row in compiled.values() if row["id"] == "design-component-properties")
        helper_path = recipes / helper["helpers"]
        self.assertEqual(helper["helpersSha256"], hashlib.sha256(helper_path.read_bytes()).hexdigest())
        self.assertEqual(bundle["typescriptVersion"], "5.9.3")
        graph_bundle = bundle["sdkGraphRecipes"]
        self.assertEqual([row["id"] for row in graph_bundle], ["design-type-review"])
        graph_row = graph_bundle[0]
        self.assertEqual(graph_row["graphTemplateSha256"],
                         hashlib.sha256((recipes / graph_row["graphTemplate"]).read_bytes()).hexdigest())
        self.assertEqual(graph_row["sourceSha256"],
                         hashlib.sha256((recipes / graph_row["source"]).read_bytes()).hexdigest())
        visual_graph_path = recipes / "design-examples.graph.json"
        visual_graph_raw = visual_graph_path.read_bytes()
        graph_source = recipe_design_graph.parse_graph(visual_graph_raw)
        self.assertTrue(all(row["designGraph"] == visual_graph_path.name for row in manifest["recipes"]))
        self.assertEqual(bundle["designGraph"]["sourceSha256"], hashlib.sha256(visual_graph_raw).hexdigest())
        visual_projection = recipe_design_graph.typescript_projection(graph_source)
        self.assertEqual(bundle["designGraph"]["projectionSha256"], hashlib.sha256(visual_projection.encode()).hexdigest())
        payload = recipe_design_graph.payload_projection(graph_source)
        self.assertEqual(bundle["designGraph"]["componentPayloadSha256"], hashlib.sha256(payload.encode()).hexdigest())
        self.assertEqual(payload, (ROOT / "tests/fixtures/declared-component-properties.json").read_text(encoding="utf-8"))
        rollback = subprocess.run(["node", str(recipes / "test-rollback.cjs")],
                                  cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(rollback.returncode, 0, rollback.stderr)

    def test_visual_graph_preserves_the_existing_five_recipe_sample_values(self):
        graph = recipe_design_graph.load_graph()
        visuals = graph["visuals"]
        shapes = visuals["design-shapes"]
        self.assertEqual(shapes["frame"], {"width": 880, "height": 380, "pageXOffset": 160,
                                            "fills": [], "clipsContent": False})
        self.assertEqual((shapes["booleans"]["shapeWidth"], shapes["booleans"]["shapeHeight"],
                          shapes["booleans"]["stepX"], shapes["booleans"]["overlapX"],
                          shapes["booleans"]["secondY"], shapes["booleans"]["fill"]),
                         (100, 100, 180, 40, 40, {"r": 0.24, "g": 0.35, "b": 0.85}))
        self.assertEqual((shapes["mask"]["size"], shapes["mask"]["y"], shapes["content"]["width"],
                          shapes["content"]["height"], shapes["content"]["y"], shapes["content"]["fill"]),
                         (120, 220, 180, 80, 240, {"r": 0.95, "g": 0.45, "b": 0.2}))

        grid = visuals["design-grid"]
        self.assertEqual(grid["frame"], {"width": 420, "height": 280, "pageXOffset": 160})
        self.assertEqual(grid["grid"], {"mode": "GRID", "autoTracks": "NONE", "rows": 2, "columns": 2,
                                        "rowGap": 16, "columnGap": 16})
        self.assertEqual(grid["cells"], {"count": 4, "width": 160, "height": 100, "fillType": "SOLID",
                                         "fill": {"r": 0.2, "g": 0.4, "b": 0.8}, "redStep": 0.15})

        motion = visuals["design-motion"]
        self.assertEqual(motion["section"], {"width": 840, "height": 300, "pageXOffset": 160})
        self.assertEqual(motion["frame"], {"width": 360, "height": 240, "x": 24, "y": 30, "finishX": 420})
        self.assertEqual(motion["dot"], {"size": 64, "x": 24, "y": 88, "finishX": 272,
                                          "fillType": "SOLID", "fill": {"r": 0.24, "g": 0.35, "b": 0.85}})
        self.assertEqual(motion["transition"], {"type": "SMART_ANIMATE", "navigation": "NAVIGATE",
                                                "trigger": "ON_CLICK", "duration": 0.6, "easing": "EASE_IN_AND_OUT"})

        component = visuals["design-component-properties"]
        self.assertEqual(component["label"], {"fontFamily": "Inter", "fontStyle": "Regular", "fontSize": 18})
        self.assertEqual(component["frame"]["padding"], 32)
        self.assertEqual(component["frame"]["itemSpacing"], 20)
        self.assertEqual(component["component"]["padding"], 12)
        self.assertEqual(component["component"]["itemSpacing"], 12)
        self.assertEqual(component["symbol"], {"size": 24, "fillType": "SOLID", "fill": {"r": 0.22, "g": 0.36, "b": 0.85}})

        typography = visuals["design-type-review"]
        self.assertEqual(typography["font"]["preferred"], ["Inter", "Arial"])
        self.assertEqual(typography["frame"], {"width": 560, "height": 360, "xOffset": 120, "y": 80})
        self.assertEqual(typography["layout"], {"mode": "VERTICAL", "primaryAxisSizing": "AUTO",
                                                 "counterAxisSizing": "FIXED", "paddingTop": 28,
                                                 "paddingRight": 32, "paddingBottom": 28, "paddingLeft": 32,
                                                 "itemSpacing": 16})
        self.assertEqual(typography["component"], {
            "cornerRadius": 16, "strokeWeight": 1, "dashPattern": [8, 4], "strokeOpacity": 1,
            "strokeVisible": True, "strokeType": "SOLID", "backgroundType": "SOLID",
            "stroke": {"r": 0.32, "g": 0.38, "b": 0.5},
            "background": {"r": 0.075, "g": 0.09, "b": 0.13},
            "shadow": {"type": "DROP_SHADOW", "color": {"r": 0, "g": 0, "b": 0},
                       "opacity": 0.18, "offsetX": 0, "offsetY": 8, "radius": 16, "spread": 0,
                       "visible": True, "blendMode": "NORMAL"},
        })
        self.assertEqual({key: (style["fontSize"], style["lineHeight"], style["letterSpacing"], style["fill"])
                          for key, style in typography["textStyles"].items()}, {
            "display": (30, 36, -0.4, {"r": 0.96, "g": 0.97, "b": 1}),
            "body": (17, 25, 0.1, {"r": 0.78, "g": 0.82, "b": 0.9}),
            "caption": (11, 16, 0.8, {"r": 0.45, "g": 0.72, "b": 1}),
        })
        self.assertEqual(typography["metadata"], {"fontSize": 9, "fillType": "SOLID",
                                                   "fill": {"r": 0.63, "g": 0.68, "b": 0.77}})

    def test_graph_visual_mutations_project_to_standalone_build_and_failing_values_are_rejected(self):
        compiler = pinned_compiler(("FIGMA_SDK_TEST_TYPESCRIPT", "FIGMA_API_TYPESCRIPT"), "tsc.js")
        with tempfile.TemporaryDirectory(prefix="figma-flow-recipe-graph-mutation-") as temporary:
            root = Path(temporary)
            self._copy_recipe_build_tree(root)
            baseline_bundle = json.loads((root / "library/figma-recipes/bundle.json").read_text(encoding="utf-8"))
            graph_path = root / "library/figma-recipes/design-examples.graph.json"
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            values = {node["recipe"]: node["values"] for node in graph["nodes"] if node["type"] == "visual"}
            values["design-shapes"]["frame"]["width"] = 881
            grid = next(node for node in graph["nodes"] if node["id"] == "visual:design-grid")
            grid["values"]["frame"]["width"] = 517
            grid["values"]["cells"]["fill"]["r"] = 0.31
            grid["values"]["cells"]["redStep"] = 0.1
            values["design-motion"]["dot"]["size"] = 70
            values["design-component-properties"]["label"]["fontSize"] = 19
            values["design-component-properties"]["symbol"]["size"] = 27
            values["design-type-review"]["font"]["preferred"][0] = "Graph QA Sample"
            values["design-type-review"]["textStyles"]["body"]["fontSize"] = 18
            payload = next(node for node in graph["nodes"] if node.get("id") == "payload:declared-component-properties")
            payload["values"]["tokens"]["color"]["ink"]["$value"] = "#343434"
            graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self._build_recipe_tree(root, compiler)

            bundle = json.loads((root / "library/figma-recipes/bundle.json").read_text(encoding="utf-8"))
            self.assertEqual(bundle["designGraph"]["sourceSha256"], hashlib.sha256(graph_path.read_bytes()).hexdigest())
            before_javascript = {row["id"]: row["jsSha256"] for row in baseline_bundle["recipes"]}
            after_javascript = {row["id"]: row["jsSha256"] for row in bundle["recipes"]}
            self.assertEqual(set(before_javascript), set(after_javascript))
            self.assertTrue(all(before_javascript[key] != after_javascript[key] for key in before_javascript))
            output_type = bundle["sdkGraphRecipes"][0]
            original_type = json.loads((ROOT / "library/figma-recipes/bundle.json").read_text(encoding="utf-8"))["sdkGraphRecipes"][0]
            self.assertNotEqual(output_type["compiledSha256"], original_type["compiledSha256"])
            self.assertEqual(json.loads((root / "tests/fixtures/declared-component-properties.json").read_text())
                             ["tokens"]["color"]["ink"]["$value"], "#343434")
            generated_values = recipe_design_graph.typescript_projection(graph)
            self.assertIn("Graph QA Sample", generated_values)
            self.assertIn('"fontSize": 18', generated_values)
            helper = (root / "library/figma-recipes/component-properties.helpers.js").read_text(encoding="utf-8")
            self.assertIn('"#343434"', helper)

            source = root / "library/figma-recipes/bundled/design-grid.js"
            runtime = r'''const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const page={id:'1:1',selection:[],children:[]};
function node(type){return {type,children:[],fills:[],removed:false,resize(w,h){this.width=w;this.height=h;},appendChild(child){this.children.push(child);child.parent=this;},remove(){this.removed=true;}};}
const figma={editorType:'figma',currentPage:page,viewport:{scrollAndZoomIntoView(){}},
  createFrame(){return node('FRAME');},createRectangle(){return node('RECTANGLE');},createEllipse(){return node('ELLIPSE');},
  closePlugin(message){this.closed=message;}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{figma,console,Promise});
setImmediate(()=>{const frame=page.selection[0];assert.equal(frame.width,517);assert.equal(frame.height,280);
  assert.equal(frame.gridRowCount,2);assert.equal(frame.gridColumnCount,2);assert.equal(frame.children.length,4);
  assert.equal(frame.children[0].fills[0].color.r,0.31);assert.equal(frame.children[1].fills[0].color.r,0.41000000000000003);});
'''
            result = subprocess.run(["node", "-e", runtime, str(source)], cwd=root, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)

            invalid = json.loads(graph_path.read_text(encoding="utf-8"))
            next(node for node in invalid["nodes"] if node["id"] == "visual:design-grid")["values"]["frame"]["width"] = 0
            with self.assertRaisesRegex(ValueError, "positive finite number"):
                recipe_design_graph.validate_graph(invalid)

    def test_standalone_sdk_recipe_pins_and_compiles_its_graph_projection(self):
        compiler = pinned_compiler(("FIGMA_SDK_TEST_TYPESCRIPT", "FIGMA_API_TYPESCRIPT"), "tsc.js")
        with tempfile.TemporaryDirectory(prefix="figma-flow-recipe-sdk-") as temporary:
            parent = Path(temporary).resolve()
            project = parent / "grid"
            result = figma_sdk_project.initialize(project, "figma", recipe="design-grid")
            metadata = json.loads((project / "sdk-project.json").read_text(encoding="utf-8"))
            visual = recipe_design_graph.parse_graph((project / metadata["recipeDesign"]["graph"]).read_bytes())
            projection = recipe_design_graph.typescript_projection(visual, {"design-grid"})
            self.assertEqual(metadata["recipeDesign"]["graphSha256"], hashlib.sha256(
                (project / metadata["recipeDesign"]["graph"]).read_bytes()).hexdigest())
            self.assertEqual((project / metadata["recipeDesign"]["projection"]).read_text(encoding="utf-8"), projection)
            self.assertEqual(figma_sdk_project.compile_project(project, build=True, typescript=str(compiler))["status"], "built")
            output = (project / "dist/code.js").read_text(encoding="utf-8")
            self.assertIn("pageXOffset", projection)
            self.assertIn("RECIPE_VISUALS", output)
            (project / metadata["recipeDesign"]["projection"]).write_text(projection + "// drift\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "projection changed"):
                figma_sdk_project.compile_project(project, build=False, typescript=str(compiler))

    def test_recipe_visual_graph_rejects_duplicate_json_fields(self):
        source = (ROOT / "library/figma-recipes/design-examples.graph.json").read_text(encoding="utf-8")
        duplicate = source.replace('"nodes": [', '"nodes": [], "nodes": [', 1)
        with tempfile.TemporaryDirectory(prefix="figma-flow-duplicate-graph-") as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text(duplicate, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate design graph JSON key: nodes"):
                recipe_design_graph.load_graph(path)

    def test_recipe_publication_rejects_graph_values_changed_without_rebuild(self):
        with tempfile.TemporaryDirectory(prefix="figma-flow-stale-recipe-graph-") as temporary:
            root = Path(temporary)
            library = root / "library/figma-recipes"
            shutil.copytree(ROOT / "library/figma-recipes", library,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            (root / "tests/fixtures").mkdir(parents=True)
            shutil.copyfile(ROOT / "tests/fixtures/declared-component-properties.json",
                            root / "tests/fixtures/declared-component-properties.json")
            graph_path = library / "design-examples.graph.json"
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            next(node for node in graph["nodes"] if node["id"] == "visual:design-grid")["values"]["frame"]["width"] = 421
            graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            with patch.object(workspace_recipes, "LIBRARY", library), patch.object(workspace_recipes, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "canonical visual values graph"):
                    workspace_recipes.bundled_actions()

    def test_library_readmes_preserve_upstream_and_example_evidence_limits(self):
        api_readme = (ROOT / "library/figma-api/README.md").read_text(encoding="utf-8")
        rest_readme = (ROOT / "library/figma-rest/README.md").read_text(encoding="utf-8")
        widget_readme = (ROOT / "library/figma-widget/README.md").read_text(encoding="utf-8")
        widget_guide = (ROOT / "docs/figma-widget.md").read_text(encoding="utf-8")
        recipes_readme = (ROOT / "docs/figma-recipes.md").read_text(encoding="utf-8")
        self.assertIn("offline declaration catalog, not an executor or a runtime support claim", api_readme)
        self.assertIn("No network request is made by the CLI.", api_readme)
        self.assertIn("Every row retains `implementation: unverified` and `runtime_acceptance: unverified`.", api_readme)
        self.assertIn("never read credentials or send HTTP requests.", rest_readme)
        self.assertIn("Nothing evaluates or runs the returned command automatically.", rest_readme)
        self.assertIn("Neither file is an implementation", widget_readme)
        self.assertIn("예제는 Figma 공식 샘플이 아니다.", recipes_readme)
        self.assertIn("실제 에디터 삽입·협업 동기화는 별도 인수 검증이 필요하다.", widget_guide)
        self.assertIn("정적 번들 생성은 Figma 문서에 접근하지 않는다.", recipes_readme)

    def test_historical_api_audit_pins_all_stored_evidence_without_claiming_currentness(self):
        source = figma_api_inventory.verify_source()
        audit_path = ROOT / "library/figma-api/audit/members.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        candidate = audit["comparison"]["candidate"]
        self.assertEqual((candidate["api_source_ref"], candidate["api_source_version"], candidate["api_source_files"]),
                         (source["ref"], source["version"], source["files"]))
        self.assertRegex(candidate["commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(candidate["tree"], r"^[0-9a-f]{40}$")
        evidence_docs = audit["curated_evidence_sources"]
        self.assertEqual({row["path"] for row in evidence_docs}, {
            "library/figma-api/audit/evidence/curated.json",
            "library/figma-api/audit/evidence/design-recipes.json",
            "library/figma-api/audit/evidence/editor-gaps.json",
            "library/figma-api/audit/evidence/editor-recipes.json",
            "library/figma-api/audit/evidence/native-read.json",
        })
        for row in evidence_docs:
            evidence_path = ROOT / row["path"]
            self.assertEqual(hashlib.sha256(evidence_path.read_bytes()).hexdigest(), row["sha256"])
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["candidate"], {
                "ref": candidate["ref"], "commit": candidate["commit"], "tree": candidate["tree"]})
            self.assertTrue(evidence["members"] or evidence.get("scope_findings"))
        report = (ROOT / "library/figma-api/audit/report.md").read_text(encoding="utf-8")
        evidence_readme = (ROOT / "library/figma-api/audit/evidence/README.md").read_text(encoding="utf-8")
        self.assertIn("Candidate runtime", report)
        self.assertIn("The catalog is a declaration inventory, not an implementation inventory.", report)
        self.assertIn("Those references do not prove support.", report)
        self.assertIn("They are not a sample from which to estimate support across the full SDK.", evidence_readme)
        self.assertIn("The tests alone are not treated as a runtime observation.", evidence_readme)

    def test_recipe_outputs_rebuild_byte_identically_in_a_disposable_tree(self):
        compiler = pinned_compiler(("FIGMA_SDK_TEST_TYPESCRIPT", "FIGMA_API_TYPESCRIPT"), "tsc.js")
        with tempfile.TemporaryDirectory(prefix="figma-flow-recipe-build-") as temporary:
            root = Path(temporary)
            self._copy_recipe_build_tree(root)
            self._build_recipe_tree(root, compiler)
            expected_paths = [
                "bundle.json", "component-properties.helpers.js",
                "bundled/design-component-properties.js", "bundled/design-grid.js",
                "bundled/design-motion.js", "bundled/design-shapes.js",
            ]
            for relative in expected_paths:
                with self.subTest(path=relative):
                    self.assertEqual((root / "library/figma-recipes" / relative).read_bytes(),
                                     (ROOT / "library/figma-recipes" / relative).read_bytes())
            self.assertEqual((root / "tests/fixtures/declared-component-properties.json").read_bytes(),
                             (ROOT / "tests/fixtures/declared-component-properties.json").read_bytes())

    def test_maintained_campaign_catalogs_keep_source_links_and_unverified_plan_status(self):
        campaigns = campaign_library.load_library(campaign_library.DEFAULT_DATA)
        self.assertTrue(campaigns["sources"])
        self.assertTrue(campaigns["patterns"])
        self.assertRegex(campaigns["captured_on"], r"^\d{4}-\d\d-\d\d$")
        source_ids = {source["id"] for source in campaigns["sources"]}
        self.assertTrue(all(set(pattern["source_ids"]) <= source_ids for pattern in campaigns["patterns"]))
        for source in campaigns["sources"]:
            self.assertEqual("https", source["url"].split(":", 1)[0])
            self.assertTrue(source["evidence"].strip())
            self.assertTrue(source["observed"].strip())
        plan = campaign_library.plan(campaigns, campaigns["categories"][0]["id"])
        self.assertEqual((plan["status"], plan["verification"]), ("untested", "manual"))
        self.assertTrue(all(check["status"] == "untested" for pattern in plan["patterns"] for check in pattern["checks"]))

        registry = route_design.load_registry()
        self.assertEqual({"direction", "logo", "icons", "images", "typography", "motion", "figma", "verification"},
                         {lane["id"] for lane in registry["lanes"]})
        forms = campaign_forms.load()
        self.assertEqual({"commemorative-event", "launch-reveal", "participation-promotion"},
                         {form["id"] for form in forms["forms"]})
        all_forms = campaign_forms.select("1,2,3 모두", data=forms)
        self.assertEqual({form["id"] for form in all_forms}, {form["id"] for form in forms["forms"]})
        self.assertTrue(all(row["status"] == "planned" and "unverified" in row["evidence"] for row in all_forms))

        self.assertEqual(workflow.load_graph(), workflow.public_graph()["graph"])
        self.assertEqual([], sync_workflow.check())


if __name__ == "__main__":
    unittest.main()
