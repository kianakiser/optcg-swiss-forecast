from math import isclose

from optcg.features.compute import compute_features, matchup_probability


def match(day, leader_1="A", leader_2="B", label=1):
    return {"date": day, "leader_1": leader_1, "leader_2": leader_2, "label": label}


def test_same_date_and_future_results_cannot_change_features():
    first = match("2026-01-01")
    same_day = match("2026-01-01", label=0)
    tomorrow = match("2026-01-02")
    rows = list(compute_features([tomorrow, first, same_day]))
    assert rows[0]["leader_1_matches"] == rows[1]["leader_1_matches"] == 0
    assert rows[0]["matchup_win_rate"] == rows[1]["matchup_win_rate"] == 0.5
    assert rows[2]["leader_1_matches"] == 2
    assert rows[2]["leader_1_win_rate"] == 0.5
    changed = list(compute_features([first, same_day, {**tomorrow, "label": 0}]))
    assert rows[0] == changed[0] and rows[1] == changed[1]
    assert rows[2]["matchup_win_rate"] == changed[2]["matchup_win_rate"]


def test_recent_window_includes_28_days_ago_and_excludes_29():
    rows = list(compute_features([
        match("2026-01-01", label=0),
        match("2026-01-02"),
        match("2026-01-30"),
    ]))
    assert rows[-1]["leader_1_matches"] == 2
    assert rows[-1]["leader_1_recent_matches"] == 1
    assert rows[-1]["leader_1_recent_win_rate"] == 1


def test_pair_rule_uses_the_recorded_fallback_and_smoothing():
    assert matchup_probability(0.6, 0.5, 4, 4) == 0.55
    assert isclose(matchup_probability(0.6, 0.5, 4, 5), (4 + 64 * 0.55) / 69)
    for n in (0, 4, 5, 20):
        wins = n * 0.6
        forward = matchup_probability(0.7, 0.4, wins, n)
        reverse = matchup_probability(0.4, 0.7, n - wins, n)
        assert isclose(forward + reverse, 1)


def test_mirror_has_half_probability_and_counts_each_meeting_once():
    history = [match("2026-01-01", "A", "A") for _ in range(5)]
    rows = list(compute_features(history + [match("2026-01-02", "A", "A")]))
    assert rows[-1]["leader_1_matches"] == 10
    assert rows[-1]["matchup_matches"] == 5
    assert rows[-1]["matchup_win_rate"] == 0.5


def test_unseen_leader_has_a_neutral_rate_and_no_support():
    rows = list(compute_features([
        match("2026-01-01"),
        match("2026-01-02", "new", "B"),
    ]))
    assert rows[-1]["leader_1_win_rate"] == 0.5
    assert rows[-1]["leader_1_matches"] == 0
    assert rows[-1]["leader_1_recent_matches"] == 0
