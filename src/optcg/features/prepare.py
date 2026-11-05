"""Build a feature CSV from previously checked tournament CSV files."""

import argparse
import csv
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from compute import compute_features


def read_matches(paths):
    matches = {}
    tournament_dates = {}
    for path in paths:
        with path.open(newline="") as stream:
            for row in csv.DictReader(stream):
                if date.fromisoformat(row["date"]).isoformat() != row["date"]:
                    raise ValueError(f"{path}: date must use YYYY-MM-DD")
                if row["label"] not in ("0", "1"):
                    raise ValueError(f"{path}: label must be 0 or 1")
                match = {name: row[name] for name in ("tournament_id", "date", "leader_1", "leader_2")}
                if not all(value.strip() for value in match.values()):
                    raise ValueError(f"{path}: missing tournament, date or Leader")
                event = match["tournament_id"]
                previous_date = tournament_dates.setdefault(event, match["date"])
                if previous_date != match["date"]:
                    raise ValueError(f"{path}: conflicting dates for tournament {event}")
                for name in ("round", "table"):
                    match[name] = int(row[name])
                    if match[name] < 1:
                        raise ValueError(f"{path}: {name} must be positive")
                # The original single-phase CSV format omitted phase.
                match["phase"] = int(row.get("phase", "1"))
                if match["phase"] < 1:
                    raise ValueError(f"{path}: phase must be positive")
                match["label"] = int(row["label"])
                key = (match["tournament_id"], match["phase"], match["round"], match["table"])
                if key in matches and matches[key] != match:
                    raise ValueError(f"{path}: conflicting results for {key}")
                matches[key] = match
    if not matches:
        raise ValueError("No match rows found")
    return list(matches.values())


def write_features(rows, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", newline="", dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = list(compute_features(read_matches(args.inputs)))
    write_features(rows, args.output)
    print(f"Saved {len(rows)} dated feature rows to {args.output}")
    print("History uses earlier event dates. Historical result availability still needs verification.")


if __name__ == "__main__":
    main()
