"""Find candidate IDs on a Limitless completed-tournaments page.

The caller fetches and retains the page. Discovery does not establish the game's
format or eligibility: new IDs still need the project's approval checks.
"""

from html.parser import HTMLParser
import re
from urllib.parse import urlsplit


class CompletedTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.table_depth = 0
        self.found_table = False
        self.ids = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            if self.table_depth:
                self.table_depth += 1
            elif "completed-tournaments" in (attrs.get("class") or "").split():
                self.table_depth = 1
                self.found_table = True
        if tag != "a" or not self.table_depth:
            return
        link = urlsplit(attrs.get("href") or "")
        if link.netloc not in ("", "play.limitlesstcg.com") or link.scheme not in ("", "https"):
            return
        match = re.fullmatch(r"/tournament/([0-9a-f]{24})/(?:standings|details)/?", link.path)
        if match:
            self.ids[match[1]] = None

    def handle_endtag(self, tag):
        if tag == "table" and self.table_depth:
            self.table_depth -= 1


def completed_event_ids(html):
    """Return unique candidate IDs in page order; reject a missing or broken table."""
    parser = CompletedTable()
    parser.feed(html)
    parser.close()
    if not parser.found_table or parser.table_depth:
        raise ValueError("Completed tournament table missing or incomplete; check the saved page")
    return list(parser.ids)
