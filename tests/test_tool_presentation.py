"""Mutate authored report styles and observe the offline documents and starter output."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReportAppearanceTests(unittest.TestCase):
    def test_changed_palette_and_dimensions_reach_the_published_report_and_widget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for directory in ('tools','library','figma-bridge','panel-ui/src','skills'):
                shutil.copytree(ROOT/directory,root/directory,ignore=shutil.ignore_patterns('node_modules','__pycache__'))
            shutil.copyfile(ROOT/'plugin.json',root/'plugin.json')
            path=root/'tools/report-presentation.json'
            graph=json.loads(path.read_bytes())
            graph['surfaces']['delivery']['palette']['link']='#c03249'
            graph['surfaces']['routes']['palette']['paper']='#172635'
            graph['graphics']['widgetCounter'].update(spacing=23,border='#263748')
            path.write_text(json.dumps(graph))
            cmd=[sys.executable,'-B','tools/report_appearance.py']
            self.assertNotEqual(subprocess.run(cmd,cwd=root,capture_output=True).returncode,0)
            subprocess.run([*cmd,'--write'],cwd=root,check=True)
            subprocess.run(cmd,cwd=root,check=True)
            probe="""import sys;sys.path.insert(0,'tools')
import design_bundle,figma_widget_project
from pathlib import Path
html=design_bundle.landing([('Open','review')],[])
assert '#c03249' in html and '#1849a5' not in html
assert '#172635' in Path('tools/design-routes.html').read_text()
figma_widget_project.initialize(Path('widget'))
sample=Path('widget/src/code.tsx').read_text()
assert 'spacing={23}' in sample and 'stroke="#263748"' in sample
"""
            subprocess.run([sys.executable,'-B','-c',probe],cwd=root,check=True,timeout=20)

    def test_all_offline_report_rules_resolve_their_declared_palette_and_static_pages(self):
        sys.path.insert(0,str(ROOT/'tools'))
        import report_appearance
        source=report_appearance.report_graph()
        for name,surface in source['surfaces'].items():
            css=report_appearance.report_css(name)
            self.assertTrue(css.strip(),name)
            self.assertNotIn('$color(',css,name)
            for color in surface['palette'].values():
                self.assertIn(color,css,name)
        self.assertEqual(report_appearance.check(ROOT),[])


if __name__=='__main__':
    unittest.main()
