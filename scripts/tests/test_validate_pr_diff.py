import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from validate.links import find_links_in_file, start_duplicate_links_checker
from validate.pr_diff import extract_added_lines


MIXED_DIFF = '''diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,2 +1,3 @@ section + https://header.example
-Removed https://removed.example?q=a+b
 Context https://context.example?q=a+b
+Added https://first.example?q=a+b
+Added https://second.example
diff --git a/scripts/tests/test_format.py b/scripts/tests/test_format.py
--- a/scripts/tests/test_format.py
+++ b/scripts/tests/test_format.py
@@ -0,0 +1,3 @@
+'## Index'
+'https://fixture.example'
+'https://fixture.example'
'''


class TestValidatePrDiff(unittest.TestCase):
    def actual_git_diff(self, before, after, binary=False, executable=None):
        """Generate fixtures with Git itself, without commits or network access."""
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)

            def git(*arguments):
                return subprocess.check_output([
                    'git', '-c', 'core.autocrlf=false', '-c', 'core.quotePath=true',
                    *arguments,
                ], cwd=directory, stderr=subprocess.PIPE)

            git('init', '--quiet')
            for name, content in before.items():
                path = workspace / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            git('add', '--all')
            tree = git('write-tree').decode().strip()
            for name in before.keys() - after.keys():
                (workspace / name).unlink()
            for name, content in after.items():
                path = workspace / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            git('add', '--all')
            if executable:
                git('update-index', '--chmod=+x', executable)
            options = ['--binary'] if binary else []
            return git('diff', '--cached', '--no-ext-diff', '--no-textconv',
                       '--no-color', '--find-renames=100%', *options, tree)

    def links_from_additions(self, diff, filename='README.md'):
        with tempfile.TemporaryDirectory() as directory:
            additions = Path(directory) / 'additions.txt'
            additions.write_text(''.join(extract_added_lines(diff, filename)), encoding='utf-8')
            return find_links_in_file(str(additions))

    def test_other_file_index_and_duplicate_fixtures_do_not_replace_readme_links(self):
        # Exercise the actual link parser, including its existing ## Index handling.
        links = self.links_from_additions(MIXED_DIFF)
        self.assertEqual(links, ['https://first.example?q=a+b', 'https://second.example'])
        start_duplicate_links_checker(links)

    def test_context_deleted_lines_and_hunk_headers_with_plus_are_not_additions(self):
        self.assertEqual(extract_added_lines(MIXED_DIFF, 'README.md'), [
            'Added https://first.example?q=a+b\n',
            'Added https://second.example\n',
        ])

    def test_real_duplicate_readme_additions_still_fail(self):
        diff = MIXED_DIFF.replace('https://second.example', 'https://first.example?q=a+b')
        with self.assertRaises(SystemExit) as error:
            start_duplicate_links_checker(self.links_from_additions(diff))
        self.assertEqual(error.exception.code, 1)

    def test_file_matching_is_exact(self):
        self.assertEqual(extract_added_lines(MIXED_DIFF, 'README.md.backup'), [])
        self.assertEqual(extract_added_lines(MIXED_DIFF.replace('b/README.md', 'b/README.md.backup'), 'README.md'), [])

    def test_added_header_like_content_and_multiple_hunks_are_preserved(self):
        diff = '''diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -0,0 +1 @@
+++ b/not-a-header https://first.example
@@ -10 +11 @@
-Old
+Second https://second.example
\\ No newline at end of file
'''
        self.assertEqual(extract_added_lines(diff, 'README.md'), [
            '++ b/not-a-header https://first.example\n',
            'Second https://second.example\n',
        ])

    def test_quoted_utf8_filename(self):
        diff = MIXED_DIFF.replace('+++ b/README.md', '+++ "b/caf\\303\\251.md"')
        self.assertEqual(len(extract_added_lines(diff, 'café.md')), 2)

    def test_no_target_additions_is_a_valid_empty_result(self):
        unrelated = MIXED_DIFF[MIXED_DIFF.index('diff --git a/scripts/'):]
        self.assertEqual(extract_added_lines(unrelated, 'README.md'), [])
        self.assertEqual(extract_added_lines('', 'README.md'), [])

    def test_invalid_or_truncated_diff_is_rejected(self):
        for diff in ['<html>HTTP error</html>', MIXED_DIFF.rsplit("+'https://fixture.example'", 1)[0],
                     MIXED_DIFF.replace('@@ -1,2 +1,3 @@', '@@ invalid @@'),
                     MIXED_DIFF.replace('@@ -1,2 +1,3 @@', '@@ -1,1 +1,3 @@')]:
            with self.subTest(diff=diff):
                with self.assertRaises(ValueError):
                    extract_added_lines(diff, 'README.md')

    def test_actual_git_added_line_keeps_unicode_and_control_separators(self):
        for separator in ['\u2028', '\u2029', '\x85', '\v', '\f', '\x1c', '\x1d', '\x1e']:
            with self.subTest(separator=repr(separator)):
                added = 'Description' + separator + 'https://valid.example\n'
                diff = self.actual_git_diff(
                    {'README.md': b'Original\n'},
                    {'README.md': b'Original\n' + added.encode('utf-8')},
                ).decode('utf-8')
                self.assertEqual(extract_added_lines(diff, 'README.md'), [added])
                self.assertEqual(self.links_from_additions(diff), ['https://valid.example'])

    def test_actual_git_cli_preserves_crlf_bytes(self):
        added = b'Added https://valid.example\r\n'
        diff = self.actual_git_diff(
            {'README.md': b'Original\r\n'},
            {'README.md': b'Original\r\n' + added},
        )
        script = Path(__file__).resolve().parents[1] / 'validate' / 'pr_diff.py'
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / 'diff.txt').write_bytes(diff)
            result = subprocess.run([
                sys.executable, str(script), 'diff.txt', str(workspace / 'README.md'),
            ], cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, added)

    def test_actual_git_metadata_only_changes_have_no_additions(self):
        original = {'README.md': b'Original\n'}
        cases = [
            ('mode', original, original, 'README.md'),
            ('rename', original, {'renamed.md': b'Original\n'}, None),
            ('new-empty', original, {**original, 'empty.txt': b''}, None),
            ('deleted-empty', {**original, 'empty.txt': b''}, original, None),
        ]
        for name, before, after, executable in cases:
            with self.subTest(name=name):
                diff = self.actual_git_diff(before, after, executable=executable).decode('utf-8')
                self.assertTrue(diff)
                self.assertEqual(extract_added_lines(diff, 'README.md'), [])

    def test_actual_git_binary_blocks_do_not_hide_readme_additions(self):
        for binary in [False, True]:
            with self.subTest(binary_patch=binary):
                diff = self.actual_git_diff(
                    {'A.bin': b'\x00original', 'README.md': b'Original\n'},
                    {'A.bin': b'\x00changed', 'README.md': b'Original\nhttps://valid.example\n'},
                    binary=binary,
                ).decode('utf-8')
                self.assertEqual(extract_added_lines(diff, 'README.md'), ['https://valid.example\n'])

    def test_actual_git_mode_and_content_change_requires_content(self):
        diff = self.actual_git_diff(
            {'README.md': b'Original\n'},
            {'README.md': b'Original\nhttps://real.example\n'},
            executable='README.md',
        ).decode('utf-8')
        self.assertIn('old mode 100644\nnew mode 100755\n', diff)
        self.assertEqual(extract_added_lines(diff, 'README.md'), ['https://real.example\n'])
        truncated = diff[:diff.index('--- a/README.md\n')]
        self.assertIn('index ', truncated)
        with self.assertRaises(ValueError):
            extract_added_lines(truncated, 'README.md')

    def test_actual_git_binary_target_is_rejected(self):
        for binary in [False, True]:
            with self.subTest(binary_patch=binary):
                diff = self.actual_git_diff(
                    {'README.md': b'Original\n'},
                    {'README.md': b'Original\n\x00https://unextractable.example\n'},
                    binary=binary,
                ).decode('utf-8')
                with self.assertRaises(ValueError):
                    extract_added_lines(diff, 'README.md')

    def test_actual_git_no_final_newline_marker(self):
        diff = self.actual_git_diff(
            {'README.md': b'Original\n'},
            {'README.md': b'Original\nhttps://valid.example'},
        ).decode('utf-8')
        self.assertIn('\\ No newline at end of file', diff)
        self.assertEqual(extract_added_lines(diff, 'README.md'), ['https://valid.example\n'])

    def test_missing_headers_or_orphan_lines_are_rejected(self):
        header = 'diff --git a/README.md b/README.md\n'
        old = '--- a/README.md\n'
        new = '+++ b/README.md\n'
        hunk = '@@ -0,0 +1 @@\n+https://real.example\n'
        cases = {
            'header-only': header + old + new,
            'missing-old-and-new': header + hunk,
            'missing-new': header + old + hunk,
            'missing-old': header + new + hunk,
            'orphan-addition': header + old + new + hunk + '+https://silently-dropped.example\n',
            'orphan-before-hunk': header + old + new + '+https://silently-dropped.example\n' + hunk,
            'header-only-before-next-file': header + old + new + MIXED_DIFF,
            'binary-summary-orphan': header + 'Binary files a/README.md and b/README.md differ\n'
                                     '+https://silently-dropped.example\n',
        }
        for name, diff in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    extract_added_lines(diff, 'README.md')

    def test_cli_accepts_absolute_target_with_workspace_relative_diff_path(self):
        script = Path(__file__).resolve().parents[1] / 'validate' / 'pr_diff.py'
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / 'diff.txt').write_text(MIXED_DIFF, encoding='utf-8')
            result = subprocess.run([
                sys.executable, str(script), 'diff.txt', str(workspace / 'README.md'),
            ], cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, ''.join(extract_added_lines(MIXED_DIFF, 'README.md')))


if __name__ == '__main__':
    unittest.main()
