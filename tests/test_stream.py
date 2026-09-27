import io
import json
import subprocess
import sys
import unittest

from barcheck import check_stream


HEADER = 'date,open,high,low,close,volume\n'
GOOD = '2026-09-21,100,103,99,102,1200\n'


class StreamChecks(unittest.TestCase):
    def test_reads_from_current_position_without_closing(self):
        stream = io.StringIO('skip this line\n' + HEADER + GOOD)
        stream.readline()
        report = check_stream(stream)
        self.assertTrue(report.ok)
        self.assertEqual(report.rows, 1)
        self.assertFalse(stream.closed)

    def test_nonseekable_input_with_bom_and_quoted_header(self):
        class NonSeekable(io.StringIO):
            def seek(self, *args):
                raise AssertionError('Input must not be rewound')

        stream = NonSeekable('\ufeff"date",open,high,low,close,volume\r\n' + GOOD)
        self.assertTrue(check_stream(stream).ok)
        self.assertFalse(stream.closed)

    def test_cli_stdin_reports_and_exit_codes(self):
        cases = [
            (HEADER + GOOD, 0, None),
            (HEADER + GOOD * 2, 1, 'duplicate_bar'),
            ('', 1, 'empty_file'),
            (HEADER + '"unterminated', 1, 'malformed_csv'),
        ]
        for content, exit_code, issue_code in cases:
            with self.subTest(issue=issue_code):
                result = subprocess.run(
                    [sys.executable, '-m', 'barcheck', '-', '--json'],
                    input=content, text=True, capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, exit_code, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report['ok'], exit_code == 0)
                if issue_code:
                    self.assertIn(issue_code, [issue['code'] for issue in report['issues']])

    def test_cli_stdin_text_report(self):
        result = subprocess.run(
            [sys.executable, '-m', 'barcheck', '-'],
            input=HEADER + GOOD, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Checked 1 bars; found 0 issues.', result.stdout)
