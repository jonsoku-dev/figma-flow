import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import browser_access


class BrowserAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / ".figma-flow" / "playwright-mcp.json"

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_new_config_has_scoped_safe_defaults_and_strips_url_details(self):
        result = browser_access.register(self.path, [
            "HTTPS://ExAmPle.com:443/private?token=secret#fragment"
        ])
        config = self.read()
        self.assertEqual(config["browser"], {
            "isolated": True, "contextOptions": {"serviceWorkers": "block"}
        })
        self.assertEqual(config["server"], {
            "host": "127.0.0.1", "allowedHosts": ["localhost", "127.0.0.1"]
        })
        self.assertEqual(config["capabilities"], ["config"])
        self.assertEqual(config["network"]["allowedOrigins"], ["https://example.com"])
        self.assertEqual(result["origins"], ["https://example.com"])
        self.assertIn("Reload or reconnect", result["status"])
        self.assertNotIn("secret", self.path.read_text())

    def test_incremental_merge_is_exact_and_idempotent(self):
        browser_access.register(self.path, ["https://example.com/a"])
        before = self.path.read_bytes()
        browser_access.register(self.path, ["https://example.com/b?token=2"])
        self.assertEqual(self.read()["network"]["allowedOrigins"], ["https://example.com"])
        browser_access.register(self.path, ["http://example.com", "https://sub.example.com", "https://example.com:8443"])
        expected = ["https://example.com", "http://example.com", "https://sub.example.com", "https://example.com:8443"]
        self.assertEqual(self.read()["network"]["allowedOrigins"], expected)
        before_idempotent_call = self.path.read_bytes()
        self.assertEqual(browser_access.register(self.path, ["https://example.com"])["origins"], expected)
        self.assertEqual(self.path.read_bytes(), before_idempotent_call)
        self.assertNotEqual(before, self.path.read_bytes())

    def test_preserves_existing_settings_and_blocked_origins(self):
        original = {
            "browser": {"isolated": False, "contextOptions": {"serviceWorkers": "allow"}},
            "server": {"host": "127.0.0.1", "allowedHosts": ["localhost"]},
            "network": {"allowedOrigins": ["https://OLD.example:443"], "blockedOrigins": ["https://blocked.example"]},
            "capabilities": ["storage"], "custom": {"keep": True},
        }
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(original), encoding="utf-8")
        browser_access.register(self.path, ["http://new.example"])
        actual = self.read()
        self.assertEqual(actual["browser"], original["browser"])
        self.assertEqual(actual["network"]["blockedOrigins"], original["network"]["blockedOrigins"])
        self.assertEqual(actual["capabilities"], ["storage", "config"])
        self.assertEqual(actual["custom"], {"keep": True})
        self.assertEqual(actual["network"]["allowedOrigins"], ["https://old.example", "http://new.example"])

    def test_invalid_urls_leave_existing_file_unchanged_and_do_not_create_new_file(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"keep": true}\n', encoding="utf-8")
        original = self.path.read_bytes()
        invalid = [
            "", "relative/path", "file:///tmp/x", "data:text/plain,x", "https://user:pass@example.com",
            "https://*.example.com", "https://example.com:99999", "https://example.com:bad",
            "https://example.com:", "http://[fe80::1%25en0]/",
            "https://example.com\\@evil.test", "https://example.com/a b", "https://", "https://[::1",
            "https://faß.de", "https://사이트.한국",
        ]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                browser_access.register(self.path, [url])
            self.assertEqual(self.path.read_bytes(), original)
        new_path = self.root / "new.json"
        with self.assertRaises(ValueError):
            browser_access.register(new_path, ["file:///secret"])
        self.assertFalse(new_path.exists())

    def test_corrupt_or_unsafe_existing_config_is_preserved(self):
        self.path.parent.mkdir(parents=True)
        for content in (
            "{", json.dumps({"network": {"allowedOrigins": ["https://*.example.com"]}}),
            json.dumps({"network": {"allowedOrigins": ["https://example.com/path"]}}),
            json.dumps({"network": {"allowedOrigins": "https://example.com"}}),
            json.dumps({"browser": {"contextOptions": None}}),
            json.dumps({"capabilities": "config"}),
        ):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                original = self.path.read_bytes()
                with self.assertRaises(ValueError):
                    browser_access.register(self.path, ["https://safe.example"])
                self.assertEqual(self.path.read_bytes(), original)

    def test_browser_numeric_hosts_are_rejected_and_dns_trailing_dot_is_preserved(self):
        browser_access.register(self.path, ["https://Example.com.:443/path"])
        self.assertEqual(self.read()["network"]["allowedOrigins"], ["https://example.com."])
        original = self.path.read_bytes()
        for host in ("127.1", "2130706433", "0177.0.0.1", "0x7f.1", "0x7f000001", "127.0.0.1."):
            with self.subTest(host=host), self.assertRaises(ValueError):
                browser_access.register(self.path, [f"http://{host}:3000/"])
            self.assertEqual(self.path.read_bytes(), original)
        browser_access.register(self.path, ["http://127.0.0.1:3000/"])
        self.assertIn("http://127.0.0.1:3000", self.read()["network"]["allowedOrigins"])

    def test_refuses_symlink_config_path(self):
        target = self.root / "target.json"
        target.write_text('{"keep": true}', encoding="utf-8")
        self.path.parent.mkdir(parents=True)
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):
            browser_access.register(self.path, ["https://example.com"])
        self.assertEqual(target.read_text(), '{"keep": true}')

    def test_cli_generates_mcp_paths_for_each_project_without_plugin_root(self):
        for name in ("Machine A", "다른 작업 위치"):
            project = self.root / name
            project.mkdir()
            run = subprocess.run([
                sys.executable, str(ROOT / "tools/browser_access.py"),
                "--config", ".figma-flow/playwright-mcp.json", "--url", "https://example.com/page",
            ], cwd=project, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            server = result["mcp_server"]
            expected = project / ".figma-flow/playwright-mcp.json"
            self.assertTrue(expected.is_file())
            self.assertEqual(result["config_path"], str(expected.resolve()))
            self.assertEqual(server["command"], "npx")
            self.assertEqual(server["cwd"], str(project.resolve()))
            self.assertEqual(server["args"][-1], str(expected.resolve()))
            self.assertNotIn(str(ROOT), json.dumps(server, ensure_ascii=False))

    def test_ipv6_and_cli_output(self):
        result = browser_access.register(self.path, ["http://[::1]:80/a", "https://[2001:DB8::1]:444/"])
        self.assertEqual(result["origins"], ["http://[::1]", "https://[2001:db8::1]:444"])
        cli_path = self.root / "cli.json"
        run = subprocess.run([
            sys.executable, str(ROOT / "tools/browser_access.py"), "--config", str(cli_path),
            "--url", "https://cli.example/path?secret=yes",
        ], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["origins"], ["https://cli.example"])
        self.assertNotIn("secret", cli_path.read_text())
        bad = subprocess.run([
            sys.executable, str(ROOT / "tools/browser_access.py"), "--config", str(cli_path), "--url", "file:///tmp/x"
        ], capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("browser_access:", bad.stderr)


if __name__ == "__main__":
    unittest.main()
