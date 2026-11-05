# From a match to a useful row

The feature pipeline prepares the information that a model can learn from later.
It does not train the model yet.

## 1. Start with checked matches

For the first small run, we use two completed ChinoizeCup tournaments from
25 and 26 August 2025. Each had 32 players and five Swiss rounds. Their public
pages say Standard format. We kept 73 matches from the first and 70 from the
second. Two byes from the second were left out.

Each row records the tournament, date, phase, round, table, both Leader IDs and
the winner. The result is called `label`: 1 means the first listed player won,
0 means that player lost. Feature rows do not contain player names, player IDs or final placings.
Private source snapshots retain only the player IDs and Leader mappings needed
for the join, rather than names, countries or full decklists.

Sources: [first event](https://play.limitlesstcg.com/tournament/688b10d5dd3aa218838a6840/details),
[second event](https://play.limitlesstcg.com/tournament/688b11db8c0cf80c508d286d/details)
and the [completed-event listing](https://play.limitlesstcg.com/tournaments/completed?game=OP&type=online&time=2025-08&show=100).

## 2. Calculate what was known earlier

`compute.py` works through the dates in order. Before adding a day's results to
history, it calculates every row for that day. This also keeps two tournaments
on the same date from using each other's results.

For each Leader, we calculate its earlier win rate and how many appearances
support it. We also calculate these values for the preceding 28 days. A Leader
with no history starts at 50%, with a count of zero. That means we have no evidence
yet; it does not mean we have established that the Leader wins half its games.

For the exact pairing, we use the smoothing rule recorded in
`MS2_BASELINE_PLAN.md`. Fewer than five earlier meetings means using the overall
Leader reference. Otherwise, we combine the direct results with that reference
using weight 64. These settings came from the development study and still need
the later evaluation. `matchup_win_rate` is this adjusted estimate, rather than
the raw fraction of earlier direct wins. Identical Leaders get 50%.

## 3. Look at one real row

In round 1, table 2 of the second tournament, the Leaders were EB02-010 and
OP12-020. Using only the first tournament in this small example:

| Input | Leader A | Leader B |
|---|---:|---:|
| Earlier wins | 12 | 12 |
| Earlier appearances | 19 | 29 |
| Earlier win rate | 63.2% | 41.4% |

They had five direct meetings. The adjusted matchup estimate is 60.8% for A.
The recent and overall rates are equal in this original two-event example because
all its history is one day old. It is preserved in `data/features/smoke.csv` and
the smoke feature group. In a mirror match,
both players count towards their Leader's appearances, while the pairing count
increases once.

Our expanded local table now uses eight checked events from June to September 2025.
For this same row, Leader A has 154 earlier wins in 277 appearances, or 55.6%.
Only 19 appearances fall in the preceding 28 days, with 12 wins, or 63.2%.
Leader B still has 12 wins in 29 appearances. The direct meeting count is still
five, but the adjusted estimate is now 57.3% because its overall Leader reference
has changed. Adding older data changes our evidence; it does not change the result
of the match. The 28-day feature shows recent form separately. We have not added
extra weights to recent matches or tournament placings.

The actual result for this row is 1. We store it as the answer for later training
and evaluation. The calculation does not use it to produce this row's inputs.

## 4. Save the table and check it

`prepare.py` checks dates, result values and duplicate match keys, then writes
the local feature CSV. `store.py` sends the same calculation to Hopsworks and
reads it back to compare keys and every value. Its `match_features_smoke` group
keeps the original example separate from the new pipeline's `match_features_draft`.

`feature_date` is midnight on the tournament date, used as the calculation
cutoff. It is not a measured match time or the time results were published.
The archive cannot establish historical publication times. This limits what
we can claim about a historical replay, even when the date calculations pass.
`source_fetched_at` in the pipeline records when we downloaded the source; it
does not establish when the result was first available.

## 5. Repeat the calculation as a pipeline

From the repository root:

```sh
uv run --locked src/optcg/features/run.py --mode backfill
uv run --locked src/optcg/features/run.py --mode daily --publish
```

The first command processes approved events, reusing cached source snapshots.
The second refreshes them, checks the latest 100 completed-listing entries and
publishes verified features. Both use the same feature calculation above.
The approved list currently contains eight checked events. A new ID goes
into `data/pending_events.json`; a person must check eligibility and add evidence
to `config/approved_events.json` before its matches enter the calculation.

Each run keeps a dated snapshot with fetch times, minimized source data,
eligibility evidence and excluded-row counts. Publishing uploads that snapshot
to Hopsworks `Resources` and restores earlier match history from the draft group,
so an empty runner can recover feature history. Data stays outside Git.
The script refuses to replace an event if previously saved match keys disappear.

For published daily runs, the pending review list is also restored from Hopsworks
Resources. The code merges saved and newly found IDs, removes approved events and
saves a new checkpoint. This lets a fresh runner retain candidates from an earlier
run even if they have left the latest listing page. A real run from an empty local
data folder restored the earlier review list. A separate read-only check then
recovered all 30 records from the newly saved checkpoint.
One listing page can still miss events never seen by a run. Admission requires
review, and historical discovery is not yet complete.

On 4 November, the first backfill produced 143 local feature rows. A real daily published
run made seven source requests, found 30 pending IDs, uploaded its source snapshot
and read back all 143 draft rows with matching values. The original smoke group
remained separate. The later local backfill added six checked tournaments and now
contains 1,290 rows. It excludes 16 byes, five draws or missing results and 15
top-cut matches. It includes two tournaments on the same day, and older history
makes the recent and overall counts differ in 861 rows. The later fresh-start daily
run made 25 source requests and saved all 1,290 rows to Hopsworks. Readback matched
every key, label and feature value. The original smoke group still has 143 rows.
These checks demonstrate the calculation and storage
path; they do not establish predictive quality or complete historical coverage.

## Follow the example

Follow the second event's example row: where does its label come from, which
matches support 63.2%, and why does the row not use its own result? Then explain
why a discovered event needs approval, why the snapshot time differs from the
event date, and how publishing restores history on a fresh runner.

The daily GitHub workflow is enabled at 21:17 UTC. The final
July–September 2026 test remains unopened. `evaluate.py` implements the planned
baseline comparison and has toy tests. A real command scored only the 70 matches
from our 26 August 2025 smoke example, saving `data/evaluation/smoke_aug26`; it did
not score the held-out period or change settings. All 92 tests pass on local
Python 3.14 and Linux AMD64 Python 3.12. The Docker image built and reproduced all
1,290 local rows exactly using cached sources, no network and no credentials.
The scheduled job receives its Hopsworks key through GitHub Actions secrets.
This key expires on 11 November.
W&B, model training and live predictions belong to later milestones.

On 5 November, a temporary macOS calendar timer automatically started the published daily job on GitHub. The job saved its source snapshot and verified all 1,290 Hopsworks rows. [See the trigger, times and run evidence](MS2_SCHEDULE_EVIDENCE.md).
