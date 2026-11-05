"""Compare the three recorded baselines on a chosen period of prepared features.

This scores the supplied rows. It cannot establish their tournament eligibility
or when historical results became public. Keep those checks with the input data.
"""

import argparse
import csv
from datetime import date
import hashlib
import json
from math import isfinite
from pathlib import Path
from statistics import mean, median, stdev

from prepare import write_features


KEYS = ("tournament_id", "phase", "round", "table")
RATES = ("leader_1_win_rate", "leader_2_win_rate", "matchup_win_rate",
         "leader_1_recent_win_rate", "leader_2_recent_win_rate")
COUNTS = ("leader_1_matches", "leader_2_matches", "matchup_matches",
          "leader_1_recent_matches", "leader_2_recent_matches")
MIN_PRACTICAL_GAIN = 0.0025


def read_feature_rows(path):
    required = set(KEYS + RATES + COUNTS + ("date", "leader_1", "leader_2", "label"))
    rows, seen, event_dates = [], set(), {}
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames or []
        if required - set(header) or len(header) != len(set(header)):
            raise ValueError("Feature CSV has missing or duplicate column names")
        for row in reader:
            if any(row[name] is None or not row[name].strip() for name in required):
                raise ValueError("Feature CSV has an empty required value")
            if date.fromisoformat(row["date"]).isoformat() != row["date"]:
                raise ValueError("Dates must use YYYY-MM-DD")
            event = row["tournament_id"]
            if event_dates.setdefault(event, row["date"]) != row["date"]:
                raise ValueError("One tournament has conflicting dates")
            if row["label"] not in ("0", "1"):
                raise ValueError("Label must be 0 or 1")
            row["label"] = int(row["label"])
            for name in ("phase", "round", "table") + COUNTS:
                row[name] = int(row[name])
                minimum = 0 if name in COUNTS else 1
                if row[name] < minimum:
                    raise ValueError(f"Invalid {name}")
            for name in RATES:
                row[name] = float(row[name])
                if not isfinite(row[name]) or not 0 <= row[name] <= 1:
                    raise ValueError(f"Invalid probability in {name}")
            for leader in ("leader_1", "leader_2"):
                if row[f"{leader}_recent_matches"] > row[f"{leader}_matches"]:
                    raise ValueError("Recent match count exceeds overall count")
                for suffix in ("", "_recent"):
                    if row[f"{leader}{suffix}_matches"] == 0 and row[f"{leader}{suffix}_win_rate"] != 0.5:
                        raise ValueError("An unseen Leader must have a neutral rate")
            if row["matchup_matches"] > min(row["leader_1_matches"], row["leader_2_matches"]):
                raise ValueError("Pair count exceeds a Leader's appearances")
            if row["leader_1"] == row["leader_2"] and row["matchup_win_rate"] != 0.5:
                raise ValueError("Identical Leaders must have a 50% pair estimate")
            key = tuple(row[name] for name in KEYS)
            if key in seen:
                raise ValueError(f"Duplicate physical match: {key}")
            seen.add(key)
            rows.append(row)
    if not rows:
        raise ValueError("Feature CSV contains no rows")
    return rows


def brier_both_orientations(probability, label):
    forward = (probability - label) ** 2
    reverse = ((1 - probability) - (1 - label)) ** 2
    return (forward + reverse) / 2


def evaluate(rows, start, end):
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    if start > end:
        raise ValueError("Start date must not be after end date")
    events = {}
    for row in rows:
        if not start <= date.fromisoformat(row["date"]) <= end:
            continue
        reference = (row["leader_1_win_rate"] + 1 - row["leader_2_win_rate"]) / 2
        losses = [brier_both_orientations(p, row["label"])
                  for p in (0.5, reference, row["matchup_win_rate"])]
        events.setdefault((row["date"], row["tournament_id"]), []).append(losses)
    if not events:
        raise ValueError("No matches fall inside the requested period")

    tournaments = []
    for (day, event), losses in sorted(events.items()):
        constant, leader, pair = (mean(values) for values in zip(*losses))
        tournaments.append({
            "tournament_id": event, "date": day, "matches": len(losses),
            "brier_constant": constant, "brier_leader": leader, "brier_pair": pair,
            "pair_minus_leader": pair - leader, "pair_minus_constant": pair - constant,
        })

    matches = sum(row["matches"] for row in tournaments)
    overall = {name: sum(row[name] * row["matches"] for row in tournaments) / matches
               for name in ("brier_constant", "brier_leader", "brier_pair")}
    gain = overall["brier_leader"] - overall["brier_pair"]
    differences = [row["pair_minus_leader"] for row in tournaments]
    summary = {
        "start": start.isoformat(), "end": end.isoformat(),
        "matches": matches, "tournaments": len(tournaments), **overall,
        "pair_improvement_over_leader": gain,
        "practical_gain_threshold": MIN_PRACTICAL_GAIN,
        "meets_practical_gain_threshold": gain >= MIN_PRACTICAL_GAIN,
        "tournament_pair_minus_leader": {
            "minimum": min(differences), "median": median(differences),
            "maximum": max(differences),
            "sample_standard_deviation": stdev(differences) if len(differences) > 1 else None,
            "pair_better": sum(value < -1e-12 for value in differences),
            "tied": sum(abs(value) <= 1e-12 for value in differences),
            "pair_worse": sum(value > 1e-12 for value in differences),
        },
        "limitations": [
            "Date-based features do not prove historical result availability.",
            "Tournament eligibility and organiser concentration require the input provenance.",
            "Tournament differences describe this sample; they are not confidence intervals.",
        ],
    }
    return summary, tournaments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("features", type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    summary, tournaments = evaluate(read_feature_rows(args.features), args.start, args.end)
    summary["source_sha256"] = hashlib.sha256(args.features.read_bytes()).hexdigest()
    # A new directory preserves any earlier evaluation instead of overwriting it.
    args.output.mkdir(parents=True, exist_ok=False)
    write_features(tournaments, args.output / "tournaments.csv")
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Scored {summary['matches']} matches from {summary['tournaments']} tournaments.")
    print(f"Saved descriptive results to {args.output}")


if __name__ == "__main__":
    main()
