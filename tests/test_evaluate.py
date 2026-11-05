import csv
import json

import pytest

from evaluate import brier_both_orientations, evaluate, main, read_feature_rows


def feature_row(event="one", table=1, day="2025-09-01", label=1):
    return {
        "tournament_id": event, "date": day, "phase": 1, "round": 1, "table": table,
        "leader_1": "A", "leader_2": "B", "label": label,
        "leader_1_win_rate": 0.6, "leader_2_win_rate": 0.4, "matchup_win_rate": 0.7,
        "leader_1_matches": 10, "leader_2_matches": 10, "matchup_matches": 5,
        "leader_1_recent_win_rate": 0.6, "leader_2_recent_win_rate": 0.4,
        "leader_1_recent_matches": 5, "leader_2_recent_matches": 5,
    }


def write_rows(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_hand_calculated_losses_are_match_weighted_and_date_filtered():
    rows = [feature_row(), feature_row(table=2), feature_row("two", label=0),
            feature_row("outside", day="2025-10-01", label=0)]
    summary, events = evaluate(rows, "2025-09-01", "2025-09-30")
    assert summary["matches"] == 3 and summary["tournaments"] == 2
    assert summary["brier_constant"] == 0.25
    assert summary["brier_leader"] == pytest.approx((0.16 + 0.16 + 0.36) / 3)
    assert summary["brier_pair"] == pytest.approx((0.09 + 0.09 + 0.49) / 3)
    assert events[0]["pair_minus_leader"] == pytest.approx(-0.07)
    assert events[1]["pair_minus_leader"] == pytest.approx(0.13)
    assert summary["tournament_pair_minus_leader"]["pair_better"] == 1
    assert summary["tournament_pair_minus_leader"]["pair_worse"] == 1


def test_swapping_leaders_and_the_label_keeps_each_match_loss():
    forward = feature_row()
    reverse = {**forward, "leader_1": "B", "leader_2": "A", "label": 0,
               "leader_1_win_rate": 0.4, "leader_2_win_rate": 0.6,
               "matchup_win_rate": 0.3}
    first, _ = evaluate([forward], "2025-09-01", "2025-09-30")
    swapped, _ = evaluate([reverse], "2025-09-01", "2025-09-30")
    for name in ("brier_constant", "brier_leader", "brier_pair"):
        assert first[name] == pytest.approx(swapped[name])
    assert brier_both_orientations(0.7, 1) == pytest.approx(0.09)


@pytest.mark.parametrize("change", [
    {"label": 2}, {"matchup_win_rate": "nan"}, {"leader_1_win_rate": 1.1},
    {"matchup_matches": -1}, {"phase": 0}, {"table": 0}, {"date": "20250901"},
    {"leader_1_matches": 0}, {"leader_1_recent_matches": 11},
    {"leader_2": "A"}, {"leader_1": " "},
])
def test_invalid_features_fail_before_scoring(tmp_path, change):
    path = tmp_path / "features.csv"
    write_rows(path, [{**feature_row(), **change}])
    with pytest.raises(ValueError):
        read_feature_rows(path)


def test_duplicate_matches_and_inconsistent_dates_are_rejected(tmp_path):
    path = tmp_path / "features.csv"
    write_rows(path, [feature_row(), feature_row()])
    with pytest.raises(ValueError, match="Duplicate physical match"):
        read_feature_rows(path)
    write_rows(path, [feature_row(), feature_row(table=2, day="2025-09-02")])
    with pytest.raises(ValueError, match="conflicting dates"):
        read_feature_rows(path)


def test_valid_feature_csv_and_invalid_periods(tmp_path):
    path = tmp_path / "features.csv"
    write_rows(path, [feature_row()])
    rows = read_feature_rows(path)
    assert rows[0]["label"] == 1 and rows[0]["leader_1_matches"] == 10
    with pytest.raises(ValueError, match="Start date"):
        evaluate(rows, "2025-10-01", "2025-09-01")
    with pytest.raises(ValueError, match="No matches"):
        evaluate(rows, "2025-10-01", "2025-10-31")


def test_cli_writes_both_reports_and_preserves_an_existing_run(tmp_path, monkeypatch):
    source, output = tmp_path / "features.csv", tmp_path / "report"
    write_rows(source, [feature_row()])
    monkeypatch.setattr("sys.argv", ["evaluate.py", str(source), "--start", "2025-09-01",
                                   "--end", "2025-09-30", "--output", str(output)])
    main()
    original = (output / "summary.json").read_text()
    assert json.loads(original)["matches"] == 1
    assert len(list(csv.DictReader((output / "tournaments.csv").open()))) == 1
    with pytest.raises(FileExistsError):
        main()
    assert (output / "summary.json").read_text() == original
