import argparse
import json
import sys

from .core import check_csv, check_stream


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check a daily OHLCV CSV before using it.")
    parser.add_argument("file", help="CSV file to check, or - for standard input")
    parser.add_argument("--json", action="store_true", help="Print a structured report")
    args = parser.parse_args(argv)
    try:
        report = check_stream(sys.stdin) if args.file == "-" else check_csv(args.file)
    except (OSError, UnicodeError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(f"Could not read {args.file}: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"Checked {report.rows} bars; found {len(report.issues)} issues.")
        for issue in report.issues:
            print(f"Row {issue.row} [{issue.code}]: {issue.message}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
