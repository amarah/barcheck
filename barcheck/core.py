"""Validate daily bars without modifying the input file."""

import csv
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TextIO

REQUIRED = ("date", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class Issue:
    row: int
    code: str
    message: str


@dataclass
class Report:
    rows: int = 0
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict:
        return {"ok": self.ok, "rows": self.rows,
                "issues": [asdict(issue) for issue in self.issues]}


def check_csv(path: str | Path, *, max_gap_days: int | None = None) -> Report:
    """Check one daily series or multiple series keyed by an optional symbol column.

    Row numbers are CSV record numbers including the header, not physical line
    numbers when quoted fields span lines. I/O and decoding errors are raised.
    """
    with open(path, encoding="utf-8-sig", newline="") as stream:
        return check_stream(stream, max_gap_days=max_gap_days)


def check_stream(stream: TextIO, *, max_gap_days: int | None = None) -> Report:
    """Check CSV text from the stream's current position without closing it.

    Open file streams with newline="" to preserve CSV newline handling.
    """
    if max_gap_days is not None and (type(max_gap_days) is not int or max_gap_days < 1):
        raise ValueError("max_gap_days must be None or an integer of at least 1.")
    report = Report()

    def add(row: int, code: str, message: str) -> None:
        report.issues.append(Issue(row, code, message))

    def lines():
        for index, line in enumerate(stream):
            # stdin may preserve undecodable bytes as surrogate characters.
            # Check the entire line, including columns the validator ignores.
            if re.search(r"[\ud800-\udfff]", line):
                raise UnicodeError(f"Invalid text encoding on input line {index + 1}.")
            yield line.removeprefix("\ufeff") if index == 0 else line

    reader = csv.reader(lines(), strict=True)
    try:
        raw_header = next(reader, None)
        if raw_header is None:
            add(1, "empty_file", "The file has no header or data.")
            return report
        header = [name.strip().lower() for name in raw_header]
        if len(set(header)) != len(header) or "" in header:
            add(1, "invalid_header", "Column names must be nonempty and unique.")
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            add(1, "missing_columns", "Missing columns: " + ", ".join(missing))
        if report.issues:
            return report
        seen = set()
        latest = {}
        for row_number, cells in enumerate(reader, start=2):
            report.rows += 1
            if len(cells) != len(header):
                add(row_number, "row_width", f"Expected {len(header)} fields; got {len(cells)}.")
                continue
            values = dict(zip(header, (cell.strip() for cell in cells)))
            symbol = values.get("symbol", "")
            if "symbol" in header and not symbol:
                add(row_number, "missing_symbol", "The symbol is blank.")
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", values["date"]):
                    raise ValueError
                day = date.fromisoformat(values["date"])
            except ValueError:
                add(row_number, "invalid_date", "Date must be a valid YYYY-MM-DD date.")
            else:
                key = (symbol, day)
                if key in seen:
                    add(row_number, "duplicate_bar", "This symbol and date already appear in the file.")
                seen.add(key)
                if symbol in latest and day < latest[symbol]:
                    add(row_number, "out_of_order", "Dates must increase within each symbol.")
                elif (max_gap_days is not None and symbol in latest
                      and (day - latest[symbol]).days > max_gap_days):
                    previous = latest[symbol]
                    gap = (day - previous).days
                    series = f" for symbol {symbol}" if symbol else ""
                    add(row_number, "date_gap",
                        f"{day.isoformat()} is {gap} calendar days after "
                        f"{previous.isoformat()}{series}; limit is {max_gap_days}.")
                latest[symbol] = max(day, latest.get(symbol, day))

            numbers = {}
            for name in REQUIRED[1:]:
                try:
                    number = Decimal(values[name])
                except InvalidOperation:
                    add(row_number, "invalid_number", f"{name} must be a number.")
                    continue
                if not number.is_finite():
                    add(row_number, "nonfinite_number", f"{name} must be finite.")
                    continue
                numbers[name] = number
                if name == "volume":
                    if number < 0:
                        add(row_number, "negative_volume", "Volume cannot be negative.")
                elif number <= 0:
                    add(row_number, "nonpositive_price", f"{name} must be greater than zero.")
            if all(name in numbers for name in ("open", "high", "low", "close")):
                if not (numbers["low"] <= min(numbers["open"], numbers["close"])
                        <= max(numbers["open"], numbers["close"]) <= numbers["high"]):
                    add(row_number, "invalid_range", "Low and high must contain both open and close.")
    except csv.Error as exc:
        add(reader.line_num, "malformed_csv", f"CSV could not be parsed: {exc}")
    if report.rows == 0 and not report.issues:
        add(2, "no_data", "The file has a header but no bars.")
    return report
