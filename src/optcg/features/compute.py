"""Calculate features from earlier tournament dates.

Input rows must already meet the project's tournament and match eligibility rules.
Event dates alone do not establish when results became public. An archived replay
using this calculation remains preliminary until availability is checked.
"""

from collections import Counter, deque
from datetime import date, timedelta
from itertools import groupby


PAIR_WEIGHT = 64
MIN_PAIR_MATCHES = 5
RECENT_DAYS = 28


def win_rate(wins, matches):
    return wins / matches if matches else 0.5


def matchup_probability(leader_1_rate, leader_2_rate, pair_wins, pair_matches):
    reference = (leader_1_rate + 1 - leader_2_rate) / 2
    if pair_matches < MIN_PAIR_MATCHES:
        return reference
    return (pair_wins + PAIR_WEIGHT * reference) / (pair_matches + PAIR_WEIGHT)


def compute_features(matches):
    """Yield one row per match, updating history only after all events of a date."""
    games, wins, recent_games, recent_wins = (Counter() for _ in range(4))
    pair_games, pair_wins = Counter(), Counter()
    recent_days = deque()
    ordered = sorted(matches, key=lambda row: row["date"])

    for day_text, day_matches in groupby(ordered, key=lambda row: row["date"]):
        day = date.fromisoformat(day_text)
        rows = list(day_matches)
        oldest_day = day - timedelta(days=RECENT_DAYS)
        while recent_days and recent_days[0][0] < oldest_day:
            _, old_games, old_wins = recent_days.popleft()
            recent_games.subtract(old_games)
            recent_wins.subtract(old_wins)

        for row in rows:
            leader_1, leader_2 = row["leader_1"], row["leader_2"]
            rate_1 = win_rate(wins[leader_1], games[leader_1])
            rate_2 = win_rate(wins[leader_2], games[leader_2])
            pairing = tuple(sorted((leader_1, leader_2)))
            meetings = pair_games[pairing]
            direct_wins = pair_wins[leader_1, leader_2]
            probability = matchup_probability(rate_1, rate_2, direct_wins, meetings)
            if leader_1 == leader_2:
                probability = 0.5
            yield {
                **row,
                "leader_1_win_rate": rate_1,
                "leader_1_matches": games[leader_1],
                "leader_2_win_rate": rate_2,
                "leader_2_matches": games[leader_2],
                "matchup_win_rate": probability,
                "matchup_matches": meetings,
                "leader_1_recent_win_rate": win_rate(recent_wins[leader_1], recent_games[leader_1]),
                "leader_1_recent_matches": recent_games[leader_1],
                "leader_2_recent_win_rate": win_rate(recent_wins[leader_2], recent_games[leader_2]),
                "leader_2_recent_matches": recent_games[leader_2],
            }

        day_games, day_wins = Counter(), Counter()
        # Same-date results become history together, after every row has its features.
        for row in rows:
            leader_1, leader_2, outcome = row["leader_1"], row["leader_2"], row["label"]
            for leader, won in ((leader_1, outcome), (leader_2, 1 - outcome)):
                day_games[leader] += 1
                day_wins[leader] += won
            pair_games[tuple(sorted((leader_1, leader_2)))] += 1
            if leader_1 != leader_2:
                pair_wins[leader_1, leader_2] += outcome
                pair_wins[leader_2, leader_1] += 1 - outcome
        games.update(day_games)
        wins.update(day_wins)
        recent_games.update(day_games)
        recent_wins.update(day_wins)
        recent_days.append((day, day_games, day_wins))
