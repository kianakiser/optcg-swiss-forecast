import pandas as pd
import pytest

from store import connect, verify_saved


def test_non_interactive_run_fails_clearly_without_a_key(monkeypatch):
    monkeypatch.delenv("HOPSWORKS_API_KEY", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(ValueError, match="HOPSWORKS_API_KEY"):
        connect()


def test_storage_check_accepts_reordered_rows_and_rejects_changed_values():
    expected = pd.DataFrame({
        "tournament_id": ["event", "event"], "phase": [1, 1],
        "round": [1, 1], "table": [1, 2], "label": [1, 0],
        "leader_1_win_rate": [0.6, 0.4],
        "feature_date": pd.to_datetime(["2025-08-25", "2025-08-25"], utc=True),
    })
    verify_saved(expected, expected.iloc[::-1].copy())
    changed = expected.copy()
    changed.loc[0, "leader_1_win_rate"] = 0.9
    with pytest.raises(AssertionError):
        verify_saved(expected, changed)
    with pytest.raises(ValueError, match="duplicate"):
        verify_saved(expected, pd.concat([expected, expected.iloc[:1]]))
