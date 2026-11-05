import csv
import pytest

from prepare import read_matches, write_features


def write_match(path, label="1"):
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["tournament_id", "date", "round", "table", "leader_1", "leader_2", "label"])
        writer.writerow(["event", "2026-01-01", 1, 1, "A", "B", label])


def test_duplicates_are_not_counted_twice_and_conflicts_stop_the_run(tmp_path):
    first, second = tmp_path / "one.csv", tmp_path / "two.csv"
    write_match(first)
    write_match(second)
    assert len(read_matches([first, second])) == 1
    write_match(second, "0")
    with pytest.raises(ValueError, match="conflicting"):
        read_matches([first, second])


def test_invalid_label_is_rejected(tmp_path):
    path = tmp_path / "one.csv"
    write_match(path, "2")
    with pytest.raises(ValueError, match="label"):
        read_matches([path])


def test_mixed_date_formats_and_inconsistent_tournament_dates_are_rejected(tmp_path):
    first, second = tmp_path / "one.csv", tmp_path / "two.csv"
    write_match(first)
    second.write_text(first.read_text().replace("2026-01-01", "20260101"))
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        read_matches([second])
    second.write_text(first.read_text().replace("2026-01-01", "2026-01-02"))
    with pytest.raises(ValueError, match="conflicting dates"):
        read_matches([first, second])


def test_failed_write_keeps_the_previous_file(tmp_path):
    target = tmp_path / "features.csv"
    target.write_text("original")
    with pytest.raises(ValueError):
        write_features([{"a": 1}, {"a": 2, "unexpected": 3}], target)
    assert target.read_text() == "original"
    assert list(tmp_path.iterdir()) == [target]
