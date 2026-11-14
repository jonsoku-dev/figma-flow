"""Behavior tests for reference_distribution_guard using synthetic fixtures only."""
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/reference_distribution_guard.py'


def run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ['git', '-C', str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc.stdout.strip()


def run_guard(repo: Path, *args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, '-B', str(SCRIPT), '--repo', str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = json.loads(proc.stdout)
    return proc.returncode, payload


def make_zip(path: Path, members: dict[str, bytes], empty_dirs: tuple[str, ...] = ()) -> Path:
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for directory in empty_dirs:
            zf.writestr(directory.rstrip('/') + '/', b'')
        for name, data in members.items():
            zf.writestr(name, data)
    return path


class ReferenceDistributionGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / 'synthetic-repo'
        self.repo.mkdir()
        run_git(self.repo, 'init', '-q')
        run_git(self.repo, 'config', 'user.name', 'Synthetic Test')
        run_git(self.repo, 'config', 'user.email', 'synthetic@example.invalid')
        shutil.copy2(ROOT / '.gitignore', self.repo / '.gitignore')
        (self.repo / 'README.md').write_text('# Independent Synthetic Repo\n\nOriginal documentation.\n', encoding='utf-8')
        (self.repo / 'src').mkdir()
        (self.repo / 'src/__init__.py').write_bytes(b'')
        (self.repo / 'src/app.py').write_text('def main():\n    return "independent"\n', encoding='utf-8')
        (self.repo / 'examples/demo/evidence').mkdir(parents=True)
        (self.repo / 'examples/demo/evidence/check.json').write_text('{"ok": true}\n', encoding='utf-8')
        run_git(self.repo, 'add', '.')
        run_git(self.repo, 'commit', '-qm', 'initial synthetic commit')

    def commit_file(self, rel: str, data: bytes, message: str = 'update') -> None:
        target = self.repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        run_git(self.repo, 'add', '-f', rel)
        run_git(self.repo, 'commit', '-qm', message)

    def test_paths_only_mode_is_explicit_and_passes_clean_repo(self):
        code, report = run_guard(self.repo, '--ref', 'HEAD')
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'paths_only_clear')
        self.assertEqual(report['mode'], 'paths-only')
        self.assertFalse(report['reference_comparison_performed'])
        self.assertFalse(report['reference_literals_checked'])
        self.assertEqual(report['checks_performed'], {
            'paths_and_ephemeral': True, 'reference_zips': False, 'reference_literals': False,
        })
        self.assertIn('--reference-zip', report['notice'])
        self.assertIn('--reference-literals', report['notice'])
        self.assertEqual(report['findings'], [])

    def test_gitignore_ignores_reference_zips_extracted_dirs_and_protected_locations(self):
        ignored_samples = [
            'magicuidesign-sample-123.zip',
            'magicuidesign-sample-123/app/page.tsx',
            'nested/magicuidesign-copy/index.ts',
            '.env.local',
            '.herdr/state.json',
            'private/notes.txt',
            'tmp/scratch.log',
            'receipts/run.json',
            'figma-flow-plugin-0.35.0.zip',
            'release.tar',
        ]
        for rel in ignored_samples:
            with self.subTest(rel=rel):
                proc = subprocess.run(
                    ['git', '-C', str(self.repo), 'check-ignore', '-q', rel],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.assertEqual(proc.returncode, 0, f'expected .gitignore to ignore {rel}')

        # Worktree scan stays clean when ignored local files sit on disk.
        (self.repo / 'magicuidesign-local.zip').write_bytes(b'PK\x05\x06' + b'\x00' * 18)
        (self.repo / 'magicuidesign-local').mkdir()
        (self.repo / 'magicuidesign-local/secret.tsx').write_text('local only\n', encoding='utf-8')
        code, report = run_guard(self.repo, '--worktree')
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'paths_only_clear')

        # Forced staging of an ignored reference archive is caught before commit.
        subprocess.run(['git', '-C', str(self.repo), 'add', '-f', 'magicuidesign-local.zip'], check=True)
        code, staged_report = run_guard(self.repo, '--staged')
        self.assertEqual(code, 1)
        self.assertEqual(staged_report['status'], 'blocked')
        self.assertEqual(staged_report['counts']['forbidden_paths'], 1)

    def test_blocks_forbidden_paths_and_ephemeral_evidence_without_reference_zip(self):
        cases = [
            ('magicuidesign-sample.zip', 'forbidden_path'),
            ('vendor/magicuidesign-extracted/page.tsx', 'forbidden_path'),
            ('assets/copied.zip', 'forbidden_path'),
            ('.figma-flow/run.json', 'forbidden_path'),
            ('.codex/config.toml', 'forbidden_path'),
            ('private/draft.md', 'forbidden_path'),
            ('evidence/local.json', 'ephemeral_evidence'),
            ('nested/design-review.json', 'ephemeral_evidence'),
            ('nested/run-receipt.json', 'ephemeral_evidence'),
            ('scratch.tmp', 'ephemeral_evidence'),
        ]
        for idx, (rel, expected_category) in enumerate(cases):
            with self.subTest(rel=rel):
                branch = f'case-{idx}'
                run_git(self.repo, 'checkout', '-qb', branch, 'HEAD')
                self.commit_file(rel, b'synthetic content\n', f'add {rel}')
                code, report = run_guard(self.repo, '--ref', branch)
                self.assertEqual(code, 1)
                self.assertEqual(report['status'], 'blocked')
                self.assertTrue(any(
                    f['category'] == expected_category and f['target_path'] == rel
                    for f in report['findings']
                ), report)
                run_git(self.repo, 'checkout', '-q', '-')

    def test_blocks_renamed_and_crlf_converted_reference_members_without_leaking_text(self):
        secret_sentinel = 'SYNTHETIC_UNIQUE_MARKER_9F3A_DO_NOT_PRINT'
        unique_crlf = (
            f'// {secret_sentinel}\r\n'
            'export function SyntheticHeroSection() {\r\n'
            '  return "unique template body with enough lines and bytes to pass size threshold";\r\n'
            '}\r\n'
        ).encode('utf-8')
        binary_blob = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + b'\x42' * 200
        ref_member_name = 'private-dir/OriginalPrivateWidget.tsx'

        ref1 = make_zip(self.base / 'ref-one.zip', {
            'README.md': b'# Reference Bundle One\nDifferent README content.\n',
            'empty.png': b'',
        })
        ref2 = make_zip(self.base / 'secret-ref-two-folder.zip', {
            ref_member_name: unique_crlf,
            'public/diagram.png': binary_blob,
        })

        # Clean independent repo passes when compared against both reference ZIPs.
        code, clear_report = run_guard(
            self.repo, '--ref', 'HEAD', '--reference-zip', str(ref1), '--reference-zip', str(ref2)
        )
        self.assertEqual(code, 0)
        self.assertEqual(clear_report['status'], 'clear')
        self.assertTrue(clear_report['reference_comparison_performed'])
        self.assertEqual(clear_report['counts']['trivial_empty_skipped'], 1)

        # Copy the CRLF member with LF endings under an unrelated filename.
        lf_copy = unique_crlf.replace(b'\r\n', b'\n')
        self.commit_file('components/renamed_copy.tsx', lf_copy, 'add renamed LF copy')
        code, blocked_report = run_guard(
            self.repo, '--ref', 'HEAD', '--reference-zip', str(ref1), '--reference-zip', str(ref2)
        )
        self.assertEqual(code, 1)
        self.assertEqual(blocked_report['status'], 'blocked')
        self.assertEqual(blocked_report['counts']['unique_reference_matches'], 1)
        finding = blocked_report['findings'][0]
        self.assertEqual(finding['category'], 'unique_reference_match')
        self.assertEqual(finding['disposition'], 'blocked_unique_reference_match')
        self.assertEqual(finding['target_path'], 'components/renamed_copy.tsx')
        self.assertEqual(finding['match_kind'], 'normalized_text_lf')
        self.assertTrue(finding['renamed'])
        self.assertEqual(finding['line_ending'], 'lf')
        self.assertEqual(finding['reference_member_line_ending'], 'crlf')
        self.assertEqual(finding['reference_index'], 1)

        # Ensure neither private text nor reference filenames/personal paths appear in output.
        serialized = json.dumps(blocked_report)
        self.assertNotIn(secret_sentinel, serialized)
        self.assertNotIn('OriginalPrivateWidget', serialized)
        self.assertNotIn('secret-ref-two-folder', serialized)
        self.assertNotIn(str(self.base), serialized)

        # Binary asset match (renamed) also blocks with exact_bytes.
        self.commit_file('assets/copied_diagram.png', binary_blob, 'add renamed binary copy')
        code, bin_report = run_guard(
            self.repo, '--ref', 'HEAD', '--reference-zip', str(ref1), '--reference-zip', str(ref2)
        )
        self.assertEqual(code, 1)
        self.assertEqual(bin_report['counts']['unique_reference_matches'], 2)
        bin_finding = next(f for f in bin_report['findings'] if f['target_path'] == 'assets/copied_diagram.png')
        self.assertEqual(bin_finding['match_kind'], 'exact_bytes')
        self.assertTrue(bin_finding['renamed'])
        self.assertEqual(bin_finding['line_ending'], 'binary')

        # Text output format also keeps private text and personal paths redacted.
        text_proc = subprocess.run(
            [sys.executable, '-B', str(SCRIPT), '--repo', str(self.repo), '--ref', 'HEAD',
             '--reference-zip', str(ref2), '--format', 'text'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(text_proc.returncode, 1)
        self.assertNotIn(secret_sentinel, text_proc.stdout)
        self.assertNotIn('OriginalPrivateWidget', text_proc.stdout)
        self.assertNotIn(str(self.base), text_proc.stdout)

    def test_ambiguous_common_or_small_matches_block_locally_with_review_verdict(self):
        small_config = b'module.exports = { plugins: {} };\n'
        tiny_helper = b'export const id = (x: string) => x;\n'
        ref = make_zip(self.base / 'ref-common.zip', {
            'postcss.config.mjs': small_config,
            'tiny_helper.ts': tiny_helper,
            'README.md': b'# Completely different reference readme\n' * 10,
        })

        # Same common basename (README.md) with independent content passes.
        code, clean = run_guard(self.repo, '--ref', 'HEAD', '--reference-zip', str(ref))
        self.assertEqual(code, 0)
        self.assertEqual(clean['status'], 'clear')

        # Common boilerplate basename and tiny (<128B) file with matching hash block locally with ambiguous verdict.
        self.commit_file('postcss.config.mjs', small_config, 'add matching config')
        self.commit_file('src/tiny_helper.ts', tiny_helper, 'add matching small snippet')
        code, blocked = run_guard(self.repo, '--ref', 'HEAD', '--reference-zip', str(ref))
        self.assertEqual(code, 1)
        self.assertEqual(blocked['status'], 'blocked')
        self.assertEqual(blocked['counts']['ambiguous_reference_matches'], 2)
        self.assertEqual(blocked['counts']['unique_reference_matches'], 0)
        self.assertTrue(all(
            f['category'] == 'ambiguous_reference_match' and f['disposition'] == 'blocked_ambiguous_review_required'
            for f in blocked['findings']
        ))

    def test_legitimate_pinned_dependencies_are_preserved_while_unpinned_files_are_checked(self):
        pinned_bytes = b'Apache-2.0 synthetic pinned dependency license text.\n' * 8
        pinned_sha = hashlib.sha256(pinned_bytes).hexdigest()
        manifest = {
            'schema': 'figma-flow-skill-dependencies-v1',
            'skills': {
                'impeccable': {
                    'directory': 'vendor/skills/impeccable',
                    'entrypoint': 'SKILL.md',
                    'files': {'LICENSE': pinned_sha},
                }
            },
        }
        self.commit_file('vendor/skills/manifest.json', json.dumps(manifest).encode('utf-8'), 'add manifest')
        self.commit_file('vendor/skills/impeccable/LICENSE', pinned_bytes, 'add pinned license')

        ref = make_zip(self.base / 'ref-with-apache.zip', {
            'third-party/LICENSE': pinned_bytes,
            'src/UniqueComponent.tsx': b'export const UniqueComponent = () => "proprietary synthetic content";\n' * 5,
        })

        code, clear = run_guard(self.repo, '--ref', 'HEAD', '--reference-zip', str(ref))
        self.assertEqual(code, 0)
        self.assertEqual(clear['status'], 'clear')
        self.assertGreaterEqual(clear['counts']['legitimate_dependency_preserved'], 1)

        # Unpinned file placed inside vendor/skills/ is NOT exempted and is blocked.
        self.commit_file(
            'vendor/skills/impeccable/sneaky.tsx',
            b'export const UniqueComponent = () => "proprietary synthetic content";\n' * 5,
            'add unpinned file under vendor',
        )
        code, blocked = run_guard(self.repo, '--ref', 'HEAD', '--reference-zip', str(ref))
        self.assertEqual(code, 1)
        self.assertEqual(blocked['counts']['unique_reference_matches'], 1)
        self.assertEqual(blocked['findings'][0]['target_path'], 'vendor/skills/impeccable/sneaky.tsx')

    def test_corrupt_pins_or_spoofed_acorn_provenance_fail_closed(self):
        # Corrupt manifest.json fails closed instead of quietly skipping pin validation.
        run_git(self.repo, 'checkout', '-qb', 'bad-manifest', 'HEAD')
        self.commit_file('vendor/skills/manifest.json', b'{not json', 'corrupt manifest')
        code, err = run_guard(self.repo, '--ref', 'bad-manifest')
        self.assertEqual(code, 2)
        self.assertEqual(err['status'], 'error')
        run_git(self.repo, 'checkout', '-q', 'main')

        # Spoofed vendor/acorn/PROVENANCE.txt + replaced acorn.js also fails closed.
        run_git(self.repo, 'checkout', '-qb', 'bad-acorn', 'HEAD')
        self.commit_file('vendor/acorn/PROVENANCE.txt', b'fake provenance\n', 'spoof acorn prov')
        self.commit_file('vendor/acorn/acorn.js', b'export const Stolen = 1;\n', 'spoof acorn js')
        code2, err2 = run_guard(self.repo, '--ref', 'bad-acorn')
        self.assertEqual(code2, 2)
        self.assertEqual(err2['status'], 'error')

    def test_target_zip_checks_raw_zip_prefix_stripped_ephemeral_and_member_matches(self):
        unique_body = b'export const SyntheticTarget = () => "synthetic bundle content";\n' * 6
        ref = make_zip(self.base / 'ref.zip', {'app/page.tsx': unique_body})

        # 1. Exact raw ZIP match against reference ZIP is blocked.
        code, exact_zip_report = run_guard(
            self.repo, '--target-zip', str(ref), '--reference-zip', str(ref)
        )
        self.assertEqual(code, 1)
        self.assertEqual(exact_zip_report['counts']['exact_reference_zips'], 1)

        # 2. Clean distribution ZIP with standard git-archive prefix passes.
        clean_dist = make_zip(self.base / 'figma-flow-plugin-0.35.0.zip', {
            'figma-flow-plugin/README.md': b'# Clean Plugin\n',
            'figma-flow-plugin/examples/demo/evidence/check.json': b'{"ok": true}\n',
            'figma-flow-plugin/tools/ok.py': b'print("ok")\n',
        })
        code, clean_report = run_guard(
            self.repo, '--target-zip', str(clean_dist), '--reference-zip', str(ref)
        )
        self.assertEqual(code, 0)
        self.assertEqual(clean_report['status'], 'clear')

        # 3. Distribution ZIP containing root ephemeral dir or renamed CRLF copy or empty forbidden dir is blocked.
        dirty_dist = make_zip(
            self.base / 'dirty-dist.zip',
            {
                'figma-flow-plugin/evidence/raw.json': b'{"ephemeral": true}\n',
                'figma-flow-plugin/src/copied.tsx': unique_body.replace(b'\n', b'\r\n'),
            },
            empty_dirs=('figma-flow-plugin/magicuidesign-empty',),
        )
        code, dirty_report = run_guard(
            self.repo, '--target-zip', str(dirty_dist), '--reference-zip', str(ref)
        )
        self.assertEqual(code, 1)
        self.assertEqual(dirty_report['counts']['ephemeral_evidence'], 1)
        self.assertEqual(dirty_report['counts']['unique_reference_matches'], 1)
        self.assertEqual(dirty_report['counts']['forbidden_paths'], 1)

    def test_invalid_reference_zip_empty_zip_or_unsafe_ref_returns_error_exit_2(self):
        bad_zip = self.base / 'not-a-zip.zip'
        bad_zip.write_text('not zip bytes', encoding='utf-8')
        code, err = run_guard(self.repo, '--ref', 'HEAD', '--reference-zip', str(bad_zip))
        self.assertEqual(code, 2)
        self.assertEqual(err['status'], 'error')
        self.assertNotIn(str(self.base), json.dumps(err))

        empty_zip = make_zip(self.base / 'empty.zip', {}, empty_dirs=('empty-dir',))
        code_empty, err_empty = run_guard(self.repo, '--ref', 'HEAD', '--reference-zip', str(empty_zip))
        self.assertEqual(code_empty, 2)
        self.assertEqual(err_empty['status'], 'error')

        code2, err2 = run_guard(self.repo, '--ref', '../HEAD')
        self.assertEqual(code2, 2)
        self.assertEqual(err2['status'], 'error')

    def test_reference_literals_blocks_single_line_quotes_in_docs_and_tests_by_id_only(self):
        doc_quote = 'SYNTHETIC_ONE_LINE_DOC_QUOTE_8842_NEVER_PRINT'
        test_quote = 'SYNTHETIC_ONE_LINE_TEST_SNIPPET_9917_NEVER_PRINT'
        literals_file = self.base / 'private-local-literals-secret-name.json'
        literals_file.write_text(json.dumps({
            'rules': [
                {'id': 'SYN-DOC-01', 'literal': doc_quote},
                {'id': 'SYN-TEST-02', 'literal': test_quote},
            ]
        }), encoding='utf-8')

        # Clean independent repo passes with literals check enabled and zip check honestly omitted.
        code, clean = run_guard(self.repo, '--ref', 'HEAD', '--reference-literals', str(literals_file))
        self.assertEqual(code, 0)
        self.assertEqual(clean['status'], 'clear')
        self.assertEqual(clean['mode'], 'paths-and-reference-literals')
        self.assertFalse(clean['reference_comparison_performed'])
        self.assertTrue(clean['reference_literals_checked'])
        self.assertIn('--reference-zip', clean['notice'])

        # Commit 1-line quotes inside a doc (CRLF), a test file (LF), and a UTF-16 file.
        doc_bytes = f'# Guide\r\n\r\nIntro line\r\nQuoted: {doc_quote}\r\n'.encode('utf-8')
        test_bytes = f'def test_case():\n    assert "{test_quote}"\n'.encode('utf-8')
        utf16_bytes = f'UTF16 note: {test_quote}\r\n'.encode('utf-16')
        self.commit_file('docs/draft.md', doc_bytes, 'add doc with 1-line quote')
        self.commit_file('tests/test_draft.py', test_bytes, 'add test with 1-line quote')
        self.commit_file('docs/utf16-note.txt', utf16_bytes, 'add utf16 note with quote')

        code, blocked = run_guard(self.repo, '--ref', 'HEAD', '--reference-literals', str(literals_file))
        self.assertEqual(code, 1)
        self.assertEqual(blocked['status'], 'blocked')
        self.assertEqual(blocked['counts']['reference_literal_matches'], 3)
        by_path = {f['target_path']: f for f in blocked['findings']}
        self.assertEqual(by_path['docs/draft.md']['rule_id'], 'SYN-DOC-01')
        self.assertEqual(by_path['docs/draft.md']['target_sha256'], hashlib.sha256(doc_bytes).hexdigest())
        self.assertEqual(by_path['docs/draft.md']['line'], 4)
        self.assertEqual(by_path['tests/test_draft.py']['rule_id'], 'SYN-TEST-02')
        self.assertEqual(by_path['tests/test_draft.py']['target_sha256'], hashlib.sha256(test_bytes).hexdigest())
        self.assertEqual(by_path['tests/test_draft.py']['line'], 2)
        self.assertEqual(by_path['docs/utf16-note.txt']['rule_id'], 'SYN-TEST-02')

        text_proc = subprocess.run(
            [sys.executable, '-B', str(SCRIPT), '--repo', str(self.repo), '--ref', 'HEAD',
             '--reference-literals', str(literals_file), '--format', 'text'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(text_proc.returncode, 1)
        combined = json.dumps(blocked) + text_proc.stdout + text_proc.stderr
        for forbidden_out in (doc_quote, test_quote, 'private-local-literals-secret-name', str(self.base)):
            self.assertNotIn(forbidden_out, combined)
        self.assertIn('rule=SYN-DOC-01', text_proc.stdout)
        self.assertIn('rule=SYN-TEST-02', text_proc.stdout)

    def test_reference_literals_plain_text_rules_on_target_zip_and_error_handling(self):
        line_quote = 'SYNTHETIC_LINE_RULE_ALPHA_5501'
        rules_txt = self.base / 'local-rules.txt'
        rules_txt.write_text(f'# private comment\n\n{line_quote}\n', encoding='utf-8')

        dist_zip = make_zip(self.base / 'dist.zip', {
            'figma-flow-plugin/docs/note.md': f'Line one\nLine two {line_quote} end\n'.encode('utf-8'),
        })
        code, blocked = run_guard(
            self.repo, '--target-zip', str(dist_zip), '--reference-literals', str(rules_txt)
        )
        self.assertEqual(code, 1)
        self.assertEqual(blocked['counts']['reference_literal_matches'], 1)
        finding = blocked['findings'][0]
        self.assertEqual(finding['rule_id'], 'lit-1-3')
        self.assertEqual(finding['target_path'], 'figma-flow-plugin/docs/note.md')
        self.assertNotIn(line_quote, json.dumps(blocked))
        self.assertNotIn('local-rules.txt', json.dumps(blocked))

        # Combining --reference-zip and --reference-literals reports combined mode cleanly.
        empty_ref_zip = make_zip(self.base / 'ref-empty.zip', {'other.txt': b'unrelated\n' * 20})
        code_both, clean_both = run_guard(
            self.repo, '--ref', 'HEAD', '--reference-zip', str(empty_ref_zip), '--reference-literals', str(rules_txt)
        )
        self.assertEqual(code_both, 0)
        self.assertEqual(clean_both['mode'], 'paths-and-reference-hashes-and-literals')
        self.assertTrue(clean_both['reference_comparison_performed'])
        self.assertTrue(clean_both['reference_literals_checked'])

        empty_rules = self.base / 'empty-rules.txt'
        empty_rules.write_text('# only comments\n\n', encoding='utf-8')
        err_code, err_payload = run_guard(
            self.repo, '--ref', 'HEAD', '--reference-literals', str(empty_rules)
        )
        self.assertEqual(err_code, 2)
        self.assertEqual(err_payload['status'], 'error')
        self.assertNotIn('empty-rules.txt', json.dumps(err_payload))

    def test_blocks_nested_git_repos_and_unsafe_symlinks_without_quiet_skip(self):
        # 1. Untracked nested git repository in --worktree is blocked, not quietly skipped.
        nested = self.repo / 'copied-template'
        nested.mkdir()
        run_git(nested, 'init', '-q')
        (nested / 'page.tsx').write_text('nested\n', encoding='utf-8')
        code, wt_report = run_guard(self.repo, '--worktree')
        self.assertEqual(code, 1)
        self.assertEqual(wt_report['counts']['forbidden_paths'], 1)
        self.assertEqual(wt_report['findings'][0]['disposition'], 'blocked_gitlink_submodule')
        shutil.rmtree(nested)

        # 2. Unsafe symlink committed to git or packed into target-zip is blocked.
        (self.repo / 'src/leak_link').symlink_to('../private/secret.tsx')
        run_git(self.repo, 'add', 'src/leak_link')
        run_git(self.repo, 'commit', '-qm', 'add unsafe symlink')
        code_sym, sym_report = run_guard(self.repo, '--ref', 'HEAD')
        self.assertEqual(code_sym, 1)
        self.assertEqual(sym_report['findings'][0]['disposition'], 'blocked_forbidden_symlink')

        zip_with_sym = self.base / 'sym-dist.zip'
        with zipfile.ZipFile(zip_with_sym, 'w') as zf:
            info = zipfile.ZipInfo('figma-flow-plugin/src/escape')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, '../../outside/secret.txt')
        code_zsym, zsym_report = run_guard(self.repo, '--target-zip', str(zip_with_sym))
        self.assertEqual(code_zsym, 1)
        self.assertEqual(zsym_report['findings'][0]['disposition'], 'blocked_forbidden_symlink')


if __name__ == '__main__':
    unittest.main()
