import csv
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import run
from ingest_one import build_rows
from prepare import read_matches, write_features


FIRST = "111111111111111111111111"
SECOND = "222222222222222222222222"
FETCHED = "2026-11-04T18:00:00+00:00"


def approval(event_id=FIRST):
    return {"id": event_id, "checked_on": "2026-11-04",
            "scope": "Completed individual Standard event",
            "event_url": f"https://play.limitlesstcg.com/tournament/{event_id}/details",
            "completion_url": "https://play.limitlesstcg.com/tournaments/completed?game=OP"}


def source(event_id=FIRST, label=1, tables=1):
    return {
        "details": {"id": event_id, "name": "Test event", "game": "OP", "players": 32,
                    "date": "2025-08-25T18:00:00Z", "phases": [{"phase": 1, "type": "SWISS"}]},
        "standings": [{"player": "p1", "name": "Unused name", "deck": {"id": "A"}},
                      {"player": "p2", "deck": {"id": "B"}}],
        "pairings": [{"phase": 1, "round": 1, "table": table, "player1": "p1", "player2": "p2",
                      "winner": "p1" if label else "p2", "unused": "not needed"}
                     for table in range(1, tables + 1)],
        "fetched_at": FETCHED, "requests": [],
    }


def matches(saved_source):
    return build_rows(saved_source["details"], saved_source["standings"],
                      saved_source["pairings"], confirmed_completed=True)[0]


def setup_run(tmp_path, monkeypatch, mode="backfill", publish=False):
    manifest = tmp_path / "approved.json"
    manifest.write_text(json.dumps([approval()]))
    monkeypatch.setattr(run, "APPROVED", manifest)
    data = tmp_path / "data"
    args = ["run.py", "--mode", mode, "--data-dir", str(data)]
    if publish:
        args.append("--publish")
    monkeypatch.setattr("sys.argv", args)
    return data


def fake_project(monkeypatch, saved=None, resources=None):
    groups = [] if saved is None else [SimpleNamespace(
        name=run.GROUP, version=1, read=lambda: pytest.fail("Listing summaries have no loaded features"))]
    group_lookups, group_reads = [], []
    uploads, published = [], []
    resources = {} if resources is None else resources.copy()
    downloads, listings = [], []

    def upload(path, destination, overwrite):
        uploads.append((path, destination, overwrite))
        remote = destination + "/" + Path(path).name
        assert remote not in resources and overwrite is False
        resources[remote] = json.loads(Path(path).read_text())
        return remote

    def list_files(path, offset, limit):
        listings.append((path, offset, limit))
        return list(resources)[offset:offset + limit]

    def download(path, local_path, overwrite):
        downloads.append(path)
        assert not Path(local_path).exists() and overwrite is False
        Path(local_path).write_text(json.dumps(resources[path]))
        return local_path

    def read_saved():
        group_reads.append(True)
        return saved

    def get_feature_group(name, version):
        assert saved is not None and (name, version) == (run.GROUP, 1)
        group_lookups.append((name, version))
        return SimpleNamespace(read=read_saved)

    store = SimpleNamespace(get_feature_groups=lambda: groups, get_feature_group=get_feature_group,
                            group_lookups=group_lookups, group_reads=group_reads)
    project = SimpleNamespace(
        get_feature_store=lambda: store,
        get_dataset_api=lambda: SimpleNamespace(upload=upload, list=list_files, download=download,
                                                downloads=downloads, listings=listings),
    )
    monkeypatch.setattr(run, "connect", lambda: project)
    monkeypatch.setattr(run, "publish_frame", lambda actual_project, frame, name:
                        published.append((actual_project, frame.copy(), name)))
    return project, uploads, published


def test_replacing_an_event_keeps_other_events_and_repeating_does_not_duplicate():
    old = matches(source()) + matches(source(SECOND))
    replacement = matches(source(label=0))
    merged = run.merge_event(old, FIRST, replacement)
    assert len(merged) == 2
    assert next(row for row in merged if row["tournament_id"] == FIRST)["label"] == 0
    assert next(row for row in merged if row["tournament_id"] == SECOND)["label"] == 1
    assert run.merge_event(merged, FIRST, replacement) == merged


def test_an_event_cannot_silently_lose_previously_saved_matches():
    with pytest.raises(ValueError, match="lost previously stored"):
        run.merge_event(matches(source(tables=2)), FIRST, matches(source()))
    with pytest.raises(ValueError, match="lost previously stored"):
        run.merge_event([], FIRST, [])


@pytest.mark.parametrize("events", [[], [approval(), approval()],
                                    [{**approval(), "id": "not-an-id"}],
                                    [{**approval(), "completion_url": ""}]])
def test_invalid_approval_manifests_are_rejected(tmp_path, events):
    path = tmp_path / "approved.json"
    path.write_text(json.dumps(events))
    with pytest.raises(ValueError):
        run.approved_events(path)


def test_fetch_event_records_receipt_times_and_keeps_only_needed_player_fields(monkeypatch):
    payload = source()
    calls = []

    def fetch(url):
        calls.append(url)
        endpoint = url.rsplit("/", 1)[-1]
        return SimpleNamespace(json=lambda: deepcopy(payload[endpoint]),
                               headers={"ratelimit": '"default";r=45;t=120', "Other": "ignored"})

    monkeypatch.setattr(run, "fetch", fetch)
    monkeypatch.setattr(run, "utc_now", lambda: FETCHED)
    saved = run.fetch_event(FIRST)
    assert len(calls) == 3 and len(saved["requests"]) == 3
    assert saved["fetched_at"] == FETCHED
    assert all(item["fetched_at"] == FETCHED for item in saved["requests"])
    assert all(set(item["rate_limit"]) == {"ratelimit"} for item in saved["requests"])
    assert set(saved["standings"][0]) == {"player", "deck"}
    assert "unused" not in saved["pairings"][0]


def test_backfill_reuses_original_fetch_time_and_reruns_without_duplicate_rows(tmp_path, monkeypatch):
    data = setup_run(tmp_path, monkeypatch)
    cached = source()
    run.save_json(cached, data / "source_cache" / f"{FIRST}.json")
    monkeypatch.setattr(run, "fetch_event", lambda _: pytest.fail("Backfill should reuse this cache"))
    run.main()
    run.main()
    assert len(read_matches([data / "history.csv"])) == 1
    snapshots = list((data / "snapshots").glob("*.json"))
    assert len(snapshots) == 2
    assert all(json.loads(path.read_text())["events"][FIRST]["source"]["fetched_at"] == FETCHED
               for path in snapshots)
    with (data / "features" / "latest.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["source_fetched_at"] == FETCHED


def test_daily_refreshes_approved_events_and_queues_new_candidates(tmp_path, monkeypatch):
    data = setup_run(tmp_path, monkeypatch, mode="daily")
    run.save_json(source(), data / "source_cache" / f"{FIRST}.json")
    refreshed = {**source(label=0), "fetched_at": "2026-11-04T19:00:00+00:00"}
    calls = []

    def fetch_event(event_id):
        calls.append(event_id)
        return refreshed

    html = '<table class="completed-tournaments">' + "".join(
        f'<a href="/tournament/{event_id}/standings">Event</a>' for event_id in (FIRST, SECOND)) + '</table>'
    monkeypatch.setattr(run, "fetch_event", fetch_event)
    monkeypatch.setattr(run, "fetch", lambda _: SimpleNamespace(text=html, content=html.encode()))
    run.main()
    assert calls == [FIRST]
    assert read_matches([data / "history.csv"])[0]["label"] == 0
    assert json.loads((data / "pending_events.json").read_text())[0]["id"] == SECOND
    assert not (data / "source_cache" / f"{SECOND}.json").exists()
    snapshot = json.loads(next((data / "snapshots").glob("*.json")).read_text())
    assert snapshot["events"][FIRST]["source"]["fetched_at"] == refreshed["fetched_at"]


def test_daily_keeps_unreviewed_candidates_that_leave_the_latest_page(tmp_path, monkeypatch):
    data = setup_run(tmp_path, monkeypatch, mode="daily")
    run.save_json([{"id": SECOND, "url": "saved candidate", "reason": "Needs review"},
                   {"id": FIRST, "url": "now approved", "reason": "Already reviewed"}],
                  data / "pending_events.json")
    html = '<table class="completed-tournaments"></table>'
    monkeypatch.setattr(run, "fetch_event", lambda _: source())
    monkeypatch.setattr(run, "fetch", lambda _: SimpleNamespace(text=html, content=html.encode()))
    run.main()
    assert [item["id"] for item in json.loads((data / "pending_events.json").read_text())] == [SECOND]


@pytest.mark.parametrize("prefix", ["Resources/", "/Resources/"])
def test_fresh_daily_runner_restores_queue_and_uploads_unique_small_checkpoints(tmp_path, monkeypatch, prefix):
    data = setup_run(tmp_path, monkeypatch, mode="daily", publish=True)
    old_id = "3" * 24
    remote = prefix + "optcg_pending_events_20261103T180000_1234abcd.json"
    full = prefix + "optcg_source_snapshot_20261103T180000_1234abcd.json"
    queue = [{"id": event_id} for event_id in (old_id, FIRST, SECOND, SECOND)]
    project, uploads, _ = fake_project(monkeypatch, resources={remote: queue, full: {"pending_events": queue}})
    discovered = [SECOND] + [f"{index:024x}" for index in range(3, 102)]
    html = '<table class="completed-tournaments">' + "".join(
        f'<a href="/tournament/{event_id}/standings">Event</a>' for event_id in discovered) + '</table>'
    monkeypatch.setattr(run, "fetch_event", lambda _: source())
    monkeypatch.setattr(run, "fetch", lambda _: SimpleNamespace(text=html, content=html.encode()))
    run.main()
    pending_path = data / "pending_events.json"
    pending = json.loads(pending_path.read_text())
    assert {item["id"] for item in pending} == {old_id, *discovered}
    assert len(pending) == 101 and old_id not in discovered
    assert project.get_dataset_api().downloads == [remote]
    pending_path.unlink()  # The next runner has no local queue either.
    run.main()
    checkpoints = [path for path, _, _ in uploads if Path(path).name.startswith("optcg_pending_events_")]
    assert len(checkpoints) == len(set(checkpoints)) == 2
    assert all(destination == "Resources" and overwrite is False for _, destination, overwrite in uploads)
    assert json.loads(pending_path.read_text()) == pending


def test_daily_unions_remote_and_local_queue_and_removes_approved_ids(tmp_path, monkeypatch):
    data = setup_run(tmp_path, monkeypatch, mode="daily", publish=True)
    local_id, remote_id = "3" * 24, "4" * 24
    run.save_json([{"id": local_id}, {"id": FIRST}, {"id": SECOND}], data / "pending_events.json")
    fake_project(monkeypatch, resources={
        "Resources/optcg_pending_events_20261103T180000_1234abcd.json":
            [{"id": remote_id}, {"id": FIRST}, {"id": SECOND}],
    })
    html = f'<table class="completed-tournaments"><a href="/tournament/{SECOND}/details">Event</a></table>'
    monkeypatch.setattr(run, "fetch_event", lambda _: source())
    monkeypatch.setattr(run, "fetch", lambda _: SimpleNamespace(text=html, content=html.encode()))
    run.main()
    pending = json.loads((data / "pending_events.json").read_text())
    assert {item["id"] for item in pending} == {local_id, remote_id, SECOND}
    assert len(pending) == 3


@pytest.mark.parametrize("prefix", ["Resources/", "/Resources/"])
def test_remote_queue_restore_paginates_and_falls_back_past_backfill_snapshot(monkeypatch, prefix):
    old = prefix + "optcg_source_snapshot_20261102T180000_1234abcd.json"
    new = prefix + "optcg_source_snapshot_20261103T180000_1234abcd.json"
    resources = {f"Resources/unrelated_{index}.json": {} for index in range(1000)}
    resources.update({old: {"pending_events": [{"id": SECOND}]}, new: {"mode": "backfill"}})
    project, _, _ = fake_project(monkeypatch, resources=resources)
    dataset = project.get_dataset_api()
    assert run.restore_pending(dataset) == [{"id": SECOND}]
    assert dataset.downloads == [new, old]
    assert dataset.listings == [("Resources", 0, 1000), ("Resources", 1000, 1000)]


def test_first_daily_publish_without_a_remote_queue_starts_one(tmp_path, monkeypatch):
    data = setup_run(tmp_path, monkeypatch, mode="daily", publish=True)
    project, uploads, _ = fake_project(monkeypatch)
    html = '<table class="completed-tournaments"></table>'
    monkeypatch.setattr(run, "fetch_event", lambda _: source())
    monkeypatch.setattr(run, "fetch", lambda _: SimpleNamespace(text=html, content=html.encode()))
    run.main()
    assert json.loads((data / "pending_events.json").read_text()) == []
    assert project.get_feature_store().group_lookups == []
    assert project.get_dataset_api().downloads == []
    assert Path(uploads[0][0]).name.startswith("optcg_pending_events_")


@pytest.mark.parametrize("failure", ["listing", "download", "invalid_queue", "invalid_id", "invalid_listing"])
def test_failed_remote_queue_restore_preserves_local_queue(tmp_path, monkeypatch, failure):
    data = setup_run(tmp_path, monkeypatch, mode="daily", publish=True)
    pending_path = data / "pending_events.json"
    run.save_json([{"id": SECOND}], pending_path)
    original = pending_path.read_bytes()
    payload = {"id": SECOND} if failure == "invalid_queue" else [{"id": "invalid" if failure == "invalid_id" else FIRST}]
    project, uploads, _ = fake_project(monkeypatch, resources={
        "Resources/optcg_pending_events_20261103T180000_1234abcd.json": payload,
    })
    dataset = project.get_dataset_api()

    def fail(*args, **kwargs):
        raise RuntimeError("Remote access failed")

    if failure in ("listing", "download", "invalid_listing"):
        if failure == "invalid_listing":
            dataset.list = lambda *args, **kwargs: {"paths": []}
        else:
            setattr(dataset, "list" if failure == "listing" else "download", fail)
        monkeypatch.setattr(project, "get_dataset_api", lambda: dataset)
    html = '<table class="completed-tournaments"></table>'
    monkeypatch.setattr(run, "fetch_event", lambda _: source())
    monkeypatch.setattr(run, "fetch", lambda _: SimpleNamespace(text=html, content=html.encode()))
    with pytest.raises((RuntimeError, ValueError)):
        run.main()
    assert pending_path.read_bytes() == original
    assert uploads == []


def test_published_backfill_leaves_pending_queue_alone(tmp_path, monkeypatch):
    data = setup_run(tmp_path, monkeypatch, publish=True)
    pending_path = data / "pending_events.json"
    run.save_json([{"id": SECOND}], pending_path)
    original = pending_path.read_bytes()
    run.save_json(source(), data / "source_cache" / f"{FIRST}.json")
    project, uploads, _ = fake_project(monkeypatch)
    run.main()
    assert pending_path.read_bytes() == original
    assert project.get_dataset_api().listings == []
    assert len(uploads) == 1 and Path(uploads[0][0]).name.startswith("optcg_source_snapshot_")


@pytest.mark.parametrize("change", ["different_event", "naive_time"])
def test_invalid_cache_identity_or_timestamp_leaves_previous_history(tmp_path, monkeypatch, change):
    data = setup_run(tmp_path, monkeypatch)
    history = data / "history.csv"
    write_features(matches(source()), history)
    original = history.read_bytes()
    cached = source(SECOND) if change == "different_event" else {**source(), "fetched_at": "2026-11-04T18:00:00"}
    run.save_json(cached, data / "source_cache" / f"{FIRST}.json")
    with pytest.raises(ValueError):
        run.main()
    assert history.read_bytes() == original


def test_failed_refresh_preserves_history_and_previous_cache(tmp_path, monkeypatch):
    data = setup_run(tmp_path, monkeypatch, mode="daily")
    previous = source(tables=2)
    history, cache = data / "history.csv", data / "source_cache" / f"{FIRST}.json"
    write_features(matches(previous), history)
    run.save_json(previous, cache)
    old_history, old_cache = history.read_bytes(), cache.read_bytes()
    monkeypatch.setattr(run, "fetch_event", lambda _: source(tables=1))
    with pytest.raises(ValueError, match="lost previously stored"):
        run.main()
    assert history.read_bytes() == old_history and cache.read_bytes() == old_cache


def test_cloud_run_uploads_snapshot_and_uses_separate_draft_group(tmp_path, monkeypatch):
    data = setup_run(tmp_path, monkeypatch, publish=True)
    run.save_json(source(), data / "source_cache" / f"{FIRST}.json")
    project, uploads, published = fake_project(monkeypatch, pd.DataFrame())
    run.main()
    assert project.get_feature_store().group_lookups == [(run.GROUP, 1)]
    assert project.get_feature_store().group_reads == [True]
    assert uploads[0][1:] == ("Resources", False)
    assert published[0][0] is project and published[0][2] == "match_features_draft"
    assert len(published[0][1]) == 1
    assert len(read_matches([data / "history.csv"])) == 1


@pytest.mark.parametrize("stage", ["get_feature_groups", "get_feature_group", "read"])
@pytest.mark.parametrize("status", [403, 404])
def test_remote_history_errors_preserve_local_history(tmp_path, monkeypatch, stage, status):
    data = setup_run(tmp_path, monkeypatch, publish=True)
    history = data / "history.csv"
    write_features(matches(source()), history)
    original = history.read_bytes()
    project, uploads, published = fake_project(monkeypatch, pd.DataFrame(matches(source())))
    store = project.get_feature_store()

    def fail(*args, **kwargs):
        raise run.requests.HTTPError(f"HTTP {status}")

    if stage == "read":
        monkeypatch.setattr(store, "get_feature_group", lambda **kwargs: SimpleNamespace(read=fail))
    else:
        monkeypatch.setattr(store, stage, fail)
    with pytest.raises(run.requests.HTTPError, match=str(status)):
        run.main()
    assert history.read_bytes() == original
    assert uploads == [] and published == []


def test_remote_unapproved_event_cannot_overwrite_local_history(tmp_path, monkeypatch):
    data = setup_run(tmp_path, monkeypatch, publish=True)
    history = data / "history.csv"
    write_features(matches(source()), history)
    original = history.read_bytes()
    fake_project(monkeypatch, pd.DataFrame(matches(source(SECOND))))
    with pytest.raises(ValueError, match="removed from the approved list"):
        run.main()
    assert history.read_bytes() == original
    assert not list(data.glob("restored_*.csv"))


def test_older_remote_copy_cannot_hide_matches_already_saved_locally(tmp_path, monkeypatch):
    data = setup_run(tmp_path, monkeypatch, publish=True)
    history = data / "history.csv"
    write_features(matches(source(tables=2)), history)
    original = history.read_bytes()
    run.save_json(source(tables=1), data / "source_cache" / f"{FIRST}.json")
    fake_project(monkeypatch, pd.DataFrame(matches(source(tables=1))))
    with pytest.raises(ValueError, match="lost previously stored"):
        run.main()
    assert history.read_bytes() == original


def test_rate_limit_wait_uses_the_source_reset_and_small_sleep_chunks(monkeypatch):
    clock, calls, sleeps = [100.0], [], []
    headers = iter([{"ratelimit": '"default";r=0;t=12'}, {}])

    def get(url, timeout):
        calls.append(clock[0])
        return SimpleNamespace(headers=next(headers), raise_for_status=lambda: None)

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(run, "next_request_at", 0)
    monkeypatch.setattr(run.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(run.time, "sleep", sleep)
    monkeypatch.setattr(run.requests, "get", get)
    run.fetch("https://example.invalid/first")
    run.fetch("https://example.invalid/second")
    assert calls == [100, 113]
    assert all(0 <= seconds <= 5 for seconds in sleeps)


def test_failed_json_write_preserves_previous_file(tmp_path):
    path = tmp_path / "state.json"
    run.save_json({"valid": True}, path)
    original = path.read_bytes()
    with pytest.raises(ValueError):
        run.save_json({"invalid": float("nan")}, path)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
