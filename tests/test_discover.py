import pytest

from discover import completed_event_ids


FIRST = "111111111111111111111111"
SECOND = "222222222222222222222222"


def table(body):
    # This table class was checked on the public completed-event page.
    return f'<table class="striped completed-tournaments">{body}</table>'


def test_only_completed_table_links_are_used_and_duplicates_keep_page_order():
    html = f'<a href="/tournament/{SECOND}/standings">outside table</a>' + table(
        f'<a href="/tournament/{FIRST}/standings">date</a>'
        f'<a href="/tournament/{FIRST}/details">same event</a>'
        f'<a href="https://play.limitlesstcg.com/tournament/{SECOND}/standings?view=all">next</a>'
    )
    assert completed_event_ids(html) == [FIRST, SECOND]


def test_other_hosts_paths_and_malformed_ids_are_ignored():
    html = table(
        f'<a href="https://other.example/tournament/{FIRST}/standings">external</a>'
        f'<a href="/tournament/{FIRST}/player/someone">player</a>'
        '<a href="/tournament/not-an-id/standings">invalid</a>'
    )
    assert completed_event_ids(html) == []


@pytest.mark.parametrize("html", ["<html>Service unavailable</html>", table("")[:-8]])
def test_missing_or_incomplete_completed_table_fails_instead_of_claiming_no_events(html):
    with pytest.raises(ValueError, match="missing or incomplete"):
        completed_event_ids(html)


def test_a_complete_empty_table_is_valid():
    assert completed_event_ids(table("")) == []
