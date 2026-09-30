import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from barcheck import check_csv
from barcheck.__main__ import main

HEADER = "date,open,high,low,close,volume\n"
GOOD = "2026-09-21,100,103,99,102,1200\n"


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "prices.csv"

    def check(self, content):
        self.path.write_text(content, encoding="utf-8")
        return check_csv(self.path)

    def codes(self, content):
        return {issue.code for issue in self.check(content).issues}

    def test_valid_file_is_not_modified(self):
        report = self.check(HEADER + GOOD)
        self.assertTrue(report.ok)
        self.assertEqual(report.rows, 1)
        self.assertEqual(self.path.read_text(), HEADER + GOOD)

    def test_headers_ignore_case_whitespace_and_bom(self):
        self.assertTrue(self.check("\ufeff Date ,OPEN,High,low,close,volume\n" + GOOD).ok)

    def test_empty_and_header_only(self):
        self.assertEqual(self.codes(""), {"empty_file"})
        self.assertEqual(self.codes(HEADER), {"no_data"})

    def test_missing_and_duplicate_headers(self):
        self.assertIn("missing_columns", self.codes("date,open\n"))
        self.assertIn("invalid_header", self.codes(HEADER.rstrip() + ",Open\n"))

    def test_bad_row_width(self):
        self.assertEqual(self.codes(HEADER + GOOD.rstrip() + ",extra\n"), {"row_width"})

    def test_nonfinite_and_missing_numbers(self):
        for value in ("NaN", "Infinity", "-Infinity", "sNaN", "", "oops"):
            with self.subTest(value=value):
                self.assertFalse(self.check(HEADER + f"2026-09-21,{value},103,99,102,1\n").ok)

    def test_price_and_volume_bounds(self):
        self.assertIn("nonpositive_price", self.codes(HEADER + "2026-09-21,0,103,0,102,1\n"))
        self.assertIn("negative_volume", self.codes(HEADER + "2026-09-21,100,103,99,102,-1\n"))
        for volume in ("0", "0.5"):
            self.assertTrue(self.check(HEADER + f"2026-09-21,100,103,99,102,{volume}\n").ok)

    def test_impossible_ranges(self):
        for prices in ("104,103,99,102", "100,103,101,102", "100,99,103,102"):
            self.assertIn("invalid_range", self.codes(HEADER + f"2026-09-21,{prices},1\n"))

    def test_flat_bar_is_valid(self):
        self.assertTrue(self.check(HEADER + "2026-09-21,100,100,100,100,1\n").ok)

    def test_dates_are_strict_and_calendar_valid(self):
        for day in ("2026-02-30", "20260921", "2026-09-21T12:00:00", ""):
            self.assertIn("invalid_date", self.codes(HEADER + f"{day},100,103,99,102,1\n"))
        self.assertTrue(self.check(HEADER + "2024-02-29,100,103,99,102,1\n").ok)

    def test_duplicate_and_out_of_order(self):
        self.assertIn("duplicate_bar", self.codes(HEADER + GOOD * 2))
        self.assertIn("out_of_order", self.codes(HEADER + GOOD + GOOD.replace("09-21", "09-20")))

    def test_symbols_have_independent_date_sequences(self):
        content = "symbol," + HEADER + "A," + GOOD + "B," + GOOD
        self.assertTrue(self.check(content).ok)
        self.assertIn("duplicate_bar", self.codes(content + "A," + GOOD))
        self.assertIn("missing_symbol", self.codes("symbol," + HEADER + "," + GOOD))

    def test_optional_calendar_gap_limit_is_per_symbol(self):
        content = ("symbol," + HEADER + "A,2026-09-18,100,103,99,102,1200\n"
                   "B,2026-09-20,100,103,99,102,1200\n"
                   "A,2026-09-22,102,104,101,103,1500\n")
        self.path.write_text(content, encoding="utf-8")
        self.assertTrue(check_csv(self.path).ok)
        report = check_csv(self.path, max_gap_days=3)
        self.assertEqual([(issue.row, issue.code) for issue in report.issues], [(4, "date_gap")])
        self.assertTrue(check_csv(self.path, max_gap_days=4).ok)

    def test_gap_limit_validation(self):
        self.path.write_text(HEADER + GOOD, encoding="utf-8")
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_csv(self.path, max_gap_days=value)

    def test_quoted_csv_and_extra_columns(self):
        content = HEADER.rstrip() + ",note\n" + GOOD.rstrip() + ',"a,b"\n'
        self.assertTrue(self.check(content).ok)
        self.assertIn("malformed_csv", self.codes(HEADER + '"unterminated'))

    def test_json_and_exit_codes(self):
        for content, expected in ((HEADER + GOOD, 0), (HEADER + GOOD * 2, 1)):
            self.check(content)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main([str(self.path), "--json"]), expected)
            self.assertEqual(json.loads(output.getvalue())["ok"], expected == 0)

    def test_missing_file_and_invalid_encoding(self):
        for exists in (False, True):
            if exists:
                self.path.write_bytes(b"\xff")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main([str(self.path), "--json"]), 2)
            self.assertIn("error", json.loads(output.getvalue()))


if __name__ == "__main__":
    unittest.main()
