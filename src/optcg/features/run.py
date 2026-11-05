"""Backfill or refresh checked tournaments, then calculate and optionally store features.

Newly discovered events go into a review list. Add them to approved_events.json
only after checking their completion and individual Standard format.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from tempfile import NamedTemporaryFile, TemporaryDirectory
from uuid import uuid4

import requests

from discover import completed_event_ids
from ingest_one import API, build_rows
from prepare import read_matches, write_features
from store import KEYS, connect, prepare_frame, publish_frame


APPROVED = Path("config/approved_events.json")
COMPLETED = "https://play.limitlesstcg.com/tournaments/completed?game=OP&show=100"
GROUP = "match_features_draft"
next_request_at = 0.0


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save_json(value, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def approved_events(path):
    events = json.loads(path.read_text())
    if not isinstance(events, list) or not events:
        raise ValueError("The approved-event list must be nonempty")
    ids = [event["id"] for event in events]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[0-9a-f]{24}", event) for event in ids):
        raise ValueError("Invalid or repeated approved tournament ID")
    for event in events:
        for field in ("checked_on", "scope", "event_url", "completion_url"):
            if not event.get(field):
                raise ValueError(f"Missing eligibility evidence: {field}")
    return events


def fetch(url):
    global next_request_at
    if time.monotonic() < next_request_at:
        print("Waiting for the source's reported rate-limit reset", flush=True)
    while time.monotonic() < next_request_at:
        time.sleep(max(0, min(5, next_request_at - time.monotonic())))
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    rate = response.headers.get("ratelimit", "")
    remaining = re.search(r"(?:^|;)\s*r=(\d+)", rate)
    reset = re.search(r"(?:^|;)\s*t=(\d+)", rate)
    if remaining and remaining[1] == "0":
        if not reset:
            raise RuntimeError("API rate limit exhausted; no reset time supplied. Retry later.")
        next_request_at = time.monotonic() + int(reset[1]) + 1
    return response


def fetch_event(event_id):
    answers, requests_log = {}, []
    for endpoint in ("details", "standings", "pairings"):
        url = f"{API}/{event_id}/{endpoint}"
        response = fetch(url)
        answers[endpoint] = response.json()
        requests_log.append({
            "url": url, "fetched_at": utc_now(),
            "rate_limit": {key: value for key, value in response.headers.items() if "ratelimit" in key.lower()},
        })
    if answers["details"]["id"] != event_id:
        raise ValueError("API returned a different tournament")
    # Retain only source fields needed to join players to their Leaders.
    answers["standings"] = [{"player": row.get("player"), "deck": {"id": (row.get("deck") or {}).get("id")}}
                             for row in answers["standings"]]
    answers["pairings"] = [{key: row.get(key) for key in ("phase", "round", "table", "player1", "player2", "winner")}
                            for row in answers["pairings"]]
    return {**answers, "requests": requests_log, "fetched_at": utc_now()}


def merge_event(history, event_id, rows):
    old = {tuple(row[key] for key in KEYS) for row in history if row["tournament_id"] == event_id}
    new = {tuple(row[key] for key in KEYS) for row in rows}
    if not rows or old - new:
        raise ValueError("An event lost previously stored matches; review the source before replacing it")
    return [row for row in history if row["tournament_id"] != event_id] + rows


def pending_events(value):
    if not isinstance(value, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("id"), str)
        or not re.fullmatch(r"[0-9a-f]{24}", item["id"]) for item in value
    ):
        raise ValueError("Pending events must be a list of records with valid tournament IDs")
    return value


def restore_pending(dataset):
    files, offset = [], 0
    while True:
        page = dataset.list("Resources", offset=offset, limit=1000)
        if not isinstance(page, list) or any(not isinstance(path, str) for path in page):
            raise ValueError("Resources listing must be a list of paths")
        files.extend(page)
        if len(page) < 1000:
            break
        offset += len(page)
    checkpoints = sorted(path for path in files if re.fullmatch(
        r"/?Resources/optcg_pending_events_\d{8}T\d{6}_[0-9a-f]{8}\.json", path))
    snapshots = sorted(path for path in files if re.fullmatch(
        r"/?Resources/optcg_source_snapshot_\d{8}T\d{6}_[0-9a-f]{8}\.json", path))
    with TemporaryDirectory() as directory:
        for remote in reversed(checkpoints[-1:] or snapshots):
            downloaded = dataset.download(remote, local_path=str(Path(directory) / Path(remote).name), overwrite=False)
            value = json.loads(Path(downloaded).read_text())
            if not checkpoints:
                if not isinstance(value, dict):
                    raise ValueError("Source snapshot must be a record")
                if "pending_events" not in value:
                    continue
                value = value["pending_events"]
            return pending_events(value)
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("backfill", "daily"), required=True)
    parser.add_argument("--publish", action="store_true", help="Restore history from and write verified output to Hopsworks")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    data = args.data_dir
    events = approved_events(APPROVED)
    ids = {event["id"] for event in events}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    snapshot = {"run_id": run_id, "started_at": utc_now(), "mode": args.mode, "events": {}}
    history_path = data / "history.csv"
    project = connect() if args.publish else None
    history = read_matches([history_path]) if history_path.exists() else []

    if project is not None:
        store = project.get_feature_store()
        groups = [group for group in store.get_feature_groups() if group.name == GROUP and group.version == 1]
        if groups:
            saved = store.get_feature_group(name=GROUP, version=1).read()
            if not saved.empty:
                restored_path = data / f"restored_{run_id}.csv"
                try:
                    write_features(saved.to_dict("records"), restored_path)
                    restored = read_matches([restored_path])
                    combined = {tuple(row[key] for key in KEYS): row for row in history}
                    combined.update({tuple(row[key] for key in KEYS): row for row in restored})
                    history = list(combined.values())
                finally:
                    restored_path.unlink(missing_ok=True)
    if {row["tournament_id"] for row in history} - ids:
        raise ValueError("Stored history includes an event removed from the approved list; review before proceeding")

    for event in events:
        event_id = event["id"]
        cached_path = data / "source_cache" / f"{event_id}.json"
        if args.mode == "backfill" and cached_path.exists():
            source = json.loads(cached_path.read_text())
        else:
            source = fetch_event(event_id)
        if source["details"]["id"] != event_id:
            raise ValueError("Cached source belongs to a different tournament")
        if datetime.fromisoformat(source["fetched_at"]).utcoffset() is None:
            raise ValueError("Source fetch time must include a timezone")
        rows, skipped = build_rows(source["details"], source["standings"], source["pairings"], confirmed_completed=True)
        history = merge_event(history, event_id, rows)
        save_json(source, cached_path)
        snapshot["events"][event_id] = {"eligibility": event, "source": source, "kept": len(rows), "skipped": dict(skipped)}
        print(f"{event_id}: {len(rows)} matches; excluded {dict(skipped)}", flush=True)

    pending = []
    if args.mode == "daily":
        listing = fetch(COMPLETED)
        discovered = completed_event_ids(listing.text)
        pending = [{"id": event_id, "url": f"https://play.limitlesstcg.com/tournament/{event_id}/details",
                    "reason": "Check participant count, individual Standard format and Swiss structure before admission"}
                   for event_id in discovered if event_id not in ids]
        snapshot["discovery"] = {"url": COMPLETED, "fetched_at": utc_now(), "ids": discovered,
                                 "html_sha256": hashlib.sha256(listing.content).hexdigest()}
        # shortcut: one discovery page; add historical pagination before widening coverage.
        pending_path = data / "pending_events.json"
        previous = pending_events(json.loads(pending_path.read_text())) if pending_path.exists() else []
        if project is not None:
            previous = restore_pending(project.get_dataset_api()) + previous
        pending = list({item["id"]: item for item in previous + pending if item["id"] not in ids}.values())
        save_json(pending, pending_path)
        snapshot["pending_events"] = pending
        print(f"{len(pending)} tournaments awaiting review", flush=True)

    frame = prepare_frame(history)
    frame["source_fetched_at"] = frame["tournament_id"].map(
        {event_id: item["source"]["fetched_at"] for event_id, item in snapshot["events"].items()})
    snapshot["finished_at"] = utc_now()
    snapshot["rows"] = len(frame)
    snapshot_path = data / "snapshots" / f"optcg_source_snapshot_{run_id}.json"
    save_json(snapshot, snapshot_path)
    if project is not None:
        # Unique filenames preserve old source versions without delete permission.
        if args.mode == "daily":
            checkpoint = data / "snapshots" / f"optcg_pending_events_{run_id}.json"
            save_json(pending, checkpoint)
            project.get_dataset_api().upload(str(checkpoint), "Resources", overwrite=False)
        remote = project.get_dataset_api().upload(str(snapshot_path), "Resources", overwrite=False)
        print(f"Source snapshot saved to {remote}", flush=True)
        publish_frame(project, frame, GROUP)
    write_features(history, history_path)
    write_features(frame.to_dict("records"), data / "features" / "latest.csv")
    print(f"Saved {len(frame)} feature rows. Historical publication times remain unverified.", flush=True)


if __name__ == "__main__":
    main()
