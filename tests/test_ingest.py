import csv

import pytest

from optcg.features import ingest_one


def details(**changes):
    return {
        "id": "event", "game": "OP", "players": 32,
        "date": "2024-09-01T18:00:00.000Z", "format": None,
        "phases": [{"phase": 1, "type": "SWISS"}], **changes,
    }


def standings():
    return [
        {"player": "alice", "deck": {"id": "OP01-001"}},
        {"player": "bob", "deck": {"id": "OP02-001"}},
    ]


def pairing(**changes):
    return {"phase": 1, "round": 1, "table": 1,
            "player1": "alice", "player2": "bob", "winner": "alice", **changes}


def build(pairings, **changes):
    return ingest_one.build_rows(details(**changes), standings(), pairings,
                                 confirmed_completed=True)


def test_only_explicit_swiss_phases_are_kept_with_their_own_match_keys():
    phases = [{"phase": 1, "type": "SWISS"}, {"phase": 2, "type": "SWISS"},
              {"phase": 3, "type": "SINGLE_BRACKET"}]
    rows, skipped = build([pairing(), pairing(phase=2, winner="bob"),
                           {"phase": 3, "match": "final"}], phases=phases)
    assert [(row["phase"], row["label"]) for row in rows] == [(1, 1), (2, 0)]
    assert skipped == {"top cut": 1}
    assert set(rows[0]) == set(ingest_one.FIELDS)


@pytest.mark.parametrize("changes", [
    {"id": ""}, {"game": "PTCG"}, {"players": 31}, {"players": "32"},
    {"date": "2024-08-31T18:00:00.000Z"}, {"date": "not a date"},
    {"phases": [{"phase": 1, "type": "SINGLE_ELIMINATION"}]},
])
def test_out_of_scope_or_malformed_tournaments_fail(changes):
    with pytest.raises(ValueError):
        build([pairing()], **changes)


def test_completion_requires_a_real_world_check_not_an_invented_api_field(monkeypatch):
    with pytest.raises(ValueError, match="confirm"):
        ingest_one.build_rows(details(), standings(), [pairing()])
    monkeypatch.setattr(ingest_one, "get", lambda _: pytest.fail("No API request before confirmation"))
    with pytest.raises(SystemExit):
        ingest_one.main(["event"])


@pytest.mark.parametrize("changes", [
    {"player1": None}, {"player1": []}, {"player1": ""},
    {"player2": "alice"}, {"player2": []}, {"player2": " "},
    {"phase": 99}, {"phase": True}, {"round": 0}, {"table": "1"},
    {"winner": []},
])
def test_malformed_pairings_fail(changes):
    with pytest.raises(ValueError):
        build([pairing(**changes)])


def test_byes_and_undecided_results_are_excluded():
    rows, skipped = build([
        pairing(table=1, player2=None), pairing(table=2, player2=""),
        pairing(table=3, winner=0), pairing(table=4, winner=-1),
        pairing(table=5, winner=None), pairing(table=6),
    ])
    assert len(rows) == 1 and rows[0]["table"] == 6
    assert skipped == {"bye": 2, "draw or no result": 3}


def test_missing_leader_is_excluded_and_conflicting_leader_records_fail():
    known = standings()
    known[1]["deck"] = None
    rows, skipped = ingest_one.build_rows(details(), known, [pairing()], confirmed_completed=True)
    assert rows == [] and skipped == {"Leader unknown": 1}
    conflicting = standings() + [{"player": "alice", "deck": {"id": "OP03-001"}}]
    with pytest.raises(ValueError, match="Conflicting Leader"):
        ingest_one.build_rows(details(), conflicting, [pairing()], confirmed_completed=True)


def test_duplicate_matches_are_counted_once_and_conflicts_stop_the_run():
    rows, skipped = build([pairing(), pairing()])
    assert len(rows) == 1 and skipped == {"duplicate": 1}
    for changed in (pairing(winner="bob"), pairing(player2=None)):
        with pytest.raises(ValueError, match="Conflicting results"):
            build([pairing(), changed])


def test_empty_or_failed_write_preserves_the_previous_csv(tmp_path):
    target = tmp_path / "matches.csv"
    target.write_text("original")
    rows, _ = build([pairing()])
    for invalid in ([], [rows[0], {**rows[0], "unexpected": "value"}]):
        with pytest.raises(ValueError):
            ingest_one.save_rows(invalid, target)
        assert target.read_text() == "original"
        assert list(tmp_path.iterdir()) == [target]
    ingest_one.save_rows(rows, target)
    with target.open(newline="") as stream:
        saved = list(csv.DictReader(stream))
    assert len(saved) == 1 and saved[0]["phase"] == "1"
