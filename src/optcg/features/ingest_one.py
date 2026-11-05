"""Download one finished tournament from Limitless and save its Swiss matches as rows.

    uv run src/optcg/features/ingest_one.py 6abcff56783097f8dcb74097 --confirmed-completed

First check the public event page: it must be completed, individual and Standard
format. The cached API details have no completion field or reliable team flag.
The flag confirms you made that check; it cannot verify it automatically.

One row per match: tournament_id, date, phase, round, table, leader_1, leader_2, label.
label is 1 if the first listed player won, otherwise 0.
Player names are not saved: the model only needs the Leaders.
"""

import argparse
import csv
from collections import Counter
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

import requests

API = "https://play.limitlesstcg.com/api/tournaments"
MIN_PLAYERS = 32
EARLIEST_DATE = date(2024, 9, 1)
OUT_DIR = Path("data/matches")
FIELDS = ["tournament_id", "date", "phase", "round", "table", "leader_1", "leader_2", "label"]


def get(path):
    """Ask the Limitless API for one address and return the answer as Python data."""
    response = requests.get(f"{API}/{path}", timeout=30)
    response.raise_for_status()  # stop with an error if the API did not answer "200 OK"
    return response.json()


def check_tournament(details, confirmed_completed):
    """Check the scope fields the API actually supplies."""
    if not confirmed_completed:
        raise ValueError("First confirm completion, individual play and Standard format on the event page")
    if not isinstance(details.get("id"), str) or not details["id"].strip():
        raise ValueError("Tournament has a missing or malformed ID")
    if details.get("game") != "OP":
        raise ValueError("Tournament must be One Piece (OP)")
    if type(details.get("players")) is not int or details["players"] < MIN_PLAYERS:
        raise ValueError("Tournament must have at least 32 players")
    day = date.fromisoformat(details["date"][:10])
    if day < EARLIEST_DATE:
        raise ValueError("Tournament must be dated 2024-09-01 or later")
    phases = {}
    for phase in details["phases"]:
        number = phase["phase"]
        if type(number) is not int or number < 1 or number in phases:
            raise ValueError("Invalid or duplicate tournament phase")
        phases[number] = phase["type"]
    if "SWISS" not in phases.values():
        raise ValueError("Tournament has no SWISS phase")
    return day.isoformat(), phases


def build_rows(details, standings, pairings, *, confirmed_completed=False):
    """Build rows after the caller has checked completion and individual Standard play."""
    day, phases = check_tournament(details, confirmed_completed)
    leader_of = {}
    for standing in standings:
        player = standing.get("player")
        if not isinstance(player, str) or not player.strip():
            raise ValueError("Standing has a missing or malformed player ID")
        leader = (standing.get("deck") or {}).get("id")
        if leader is not None and (not isinstance(leader, str) or not leader.strip()):
            raise ValueError("Standing has a malformed Leader ID")
        if player in leader_of and leader_of[player] != leader:
            raise ValueError("Conflicting Leader records for one player")
        leader_of[player] = leader

    rows, skipped = [], Counter()
    seen = {}
    for match in pairings:
        player_1, player_2, winner = match.get("player1"), match.get("player2"), match.get("winner")
        phase = match.get("phase")
        if type(phase) is not int or phase not in phases:
            raise ValueError("Pairing has an unknown or malformed phase")
        if phases[phase] != "SWISS":
            skipped["top cut"] += 1
            continue
        if any(type(match.get(name)) is not int or match[name] < 1 for name in ("round", "table")):
            raise ValueError("Pairing round and table must be positive integers")
        if not isinstance(player_1, str) or not player_1.strip():
            raise ValueError("Pairing has a missing or malformed first player")
        key = (details["id"], phase, match["round"], match["table"])
        result = (player_1, player_2, winner)
        if key in seen:
            if seen[key] != result:
                raise ValueError(f"Conflicting results for match {key}")
            skipped["duplicate"] += 1
            continue
        seen[key] = result
        if player_2 is None or player_2 == "":
            skipped["bye"] += 1
            continue
        if not isinstance(player_2, str) or not player_2.strip() or player_1 == player_2:
            raise ValueError("Pairing must have two different player IDs")
        if winner is not None and not isinstance(winner, (str, int)):
            raise ValueError("Pairing has a malformed winner")
        if winner not in (player_1, player_2):
            skipped["draw or no result"] += 1
            continue
        leader_1, leader_2 = leader_of.get(player_1), leader_of.get(player_2)
        if not leader_1 or not leader_2:
            skipped["Leader unknown"] += 1
            continue
        rows.append({
            "tournament_id": details["id"],
            "date": day,
            "phase": phase,
            "round": match["round"],
            "table": match["table"],
            "leader_1": leader_1,
            "leader_2": leader_2,
            "label": int(winner == player_1),
        })
    return rows, skipped


def save_rows(rows, output):
    """Replace an existing CSV only after a complete, nonempty write."""
    if not rows:
        raise ValueError("No eligible matches; existing CSV was left unchanged")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", newline="", dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tournament_id")
    parser.add_argument("--confirmed-completed", action="store_true",
                        help="I checked the public event is completed, individual and Standard format")
    args = parser.parse_args(argv)
    if not args.confirmed_completed:
        parser.error("Check the public event page, then add --confirmed-completed")
    tournament_id = args.tournament_id
    if Path(tournament_id).name != tournament_id:
        parser.error("Use a tournament ID, not a path")
    details = get(f"{tournament_id}/details")
    if details["id"] != tournament_id:
        raise ValueError("API returned a different tournament ID")
    check_tournament(details, args.confirmed_completed)
    rows, skipped = build_rows(details, get(f"{tournament_id}/standings"),
                               get(f"{tournament_id}/pairings"), confirmed_completed=True)
    out = OUT_DIR / f"{tournament_id}.csv"
    save_rows(rows, out)

    print(f"{details['name']} ({details['date'][:10]}, {details['players']} players)")
    print(f"  kept {len(rows)} matches, skipped {dict(skipped)}")
    print(f"  saved to {out}")


if __name__ == "__main__":
    main()
