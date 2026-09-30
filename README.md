# barcheck

Check a daily price-data CSV before feeding it into a backtest or dashboard.
Bad rows are easier to fix when the report points to the exact record.

```bash
python -m barcheck examples/prices.csv
python -m barcheck your-prices.csv --json
```

Python 3.10 or later is required. There are no runtime dependencies, API keys,
or network calls. Input files stay on your machine and are never modified.

## What it checks

- Missing or duplicate column names and rows with the wrong number of fields
- Invalid dates and dates out of order within a symbol
- Duplicate bars for the same symbol and date
- Missing, nonnumeric, infinite, or NaN prices and volume
- Prices at or below zero and negative volume
- High and low values that do not contain both open and close
- Optionally, gaps longer than a chosen number of calendar days

## CSV format

Required columns: `date,open,high,low,close,volume`.
An optional `symbol` column lets you check several series in one file.
Without it, the entire file is treated as one series.

Column names are case-insensitive and surrounding whitespace is ignored.
Additional columns are allowed. Dates must use `YYYY-MM-DD`. Use a decimal
point for numbers and omit thousands separators. Zero and fractional volume
are allowed. Symbols are case-sensitive.

```csv
symbol,date,open,high,low,close,volume
DEMO,2026-09-21,100,103,99,102,1200
DEMO,2026-09-22,102,104,101,103,1500
```

These are synthetic example prices.

## Reports and exit codes

The text report lists the record number, an issue code, and an explanation.
The header is record 1. For a malformed CSV parse error, the reported number
is the physical line where parsing stopped. JSON output includes `ok`, `rows`,
and `issues`. A file-access error instead includes `ok` and `error`.

| Exit code | Meaning |
| --- | --- |
| 0 | All checks passed |
| 1 | Data or CSV-format issues found |
| 2 | Could not read the file, or invalid command arguments |

Use the exit code to stop a pipeline before a backtest starts:

```bash
python -m barcheck prices.csv && python run_backtest.py
```

`run_backtest.py` represents your own backtest script.

To flag unexpectedly long breaks within each symbol, set a calendar-day limit:

```bash
python -m barcheck prices.csv --max-gap-days 4
```

Gap checking is opt in because weekends, holidays, and trading schedules differ.
It does not use an exchange calendar.

For an installed command, run `python -m pip install .`, then `barcheck prices.csv`.
This project has not been published to PyPI.

Pass `-` to read CSV from standard input, including output from another command:

```bash
cat examples/prices.csv | python -m barcheck - --json
```

Piped input uses the same checks, reports, and exit codes as a file. It is read
once without a temporary file. Standard input uses Python's terminal encoding;
set `PYTHONIOENCODING=utf-8` when piping UTF-8 data in another locale.

## Python API

```python
from barcheck import check_csv

report = check_csv("examples/prices.csv")
if not report.ok:
    for issue in report.issues:
        print(issue.row, issue.code, issue.message)
```

The API raises file-access and decoding errors so callers can handle them.
Use `check_stream(stream)` for an open text file or `io.StringIO`. It reads from
the current position and leaves the stream open. Open text files with `newline=""`
for CSV newline handling. Both APIs accept an optional leading UTF-8 BOM.

## Limits

This version checks daily bars with positive prices. It does not validate
intraday timestamps, exchange calendars, missing sessions, corporate actions,
or whether a price matches an external source. It does not distinguish raw
from adjusted prices. A passing report means the listed checks passed, not
that the dataset is complete or correct. Instruments that allow zero or
negative prices need different validation rules.

Duplicate detection keeps one key per bar in memory. Issues are also kept in
memory; very large files with many errors may need a streaming report later.

## Development

```bash
python -m unittest discover -s tests -v
```

Useful next steps include configurable column mappings, optional exchange
calendar checks, and streaming reports for large files.
