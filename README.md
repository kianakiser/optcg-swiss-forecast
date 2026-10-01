# optcg-swiss-forecast

Predicting One Piece Card Game Leader matchup probabilities from tournament results.

Semester project for I.BA_MLOPS, BSc Artificial Intelligence & Machine Learning,
Hochschule Luzern, HS26.

## What this is

One Piece Card Game is a competitive trading card game. Each player uses a Leader
and a 50-card deck. The Leader shapes how the deck is built and played.

The planned platform will let players compare recent Leader win rates and estimate
the probability that Leader A wins against Leader B. Match counts will show how much
evidence supports the statistics. There is one ML prediction task; the recent win
rates are descriptive statistics, not a second forecast.

The scope is decided Swiss-round matches from Limitless tournaments with at least
32 players, from September 2024 onward. Swiss is a tournament format, not a
restriction to Switzerland. Top cut, byes, draws and matches without a recorded
winner are excluded.

Different deck builds, player decisions, card interactions and luck affect results.
The core model will learn from observed Leader-level outcomes, not simulate card
effects or separate player skill from deck strength. Full decklists are optional
later work. New card sets can change deck builds and matchup outcomes, which is why
the eventual system will keep collecting data and retraining.

## Current status

Week 3: proposal and documentation only. No coursework feature, training or
inference pipeline has been implemented in this repository. The architecture
below describes the planned system, not a deployed service.

| Milestone | Due | Status |
|---|---|---|
| MS1: Proposal | 2026-10-01 | Proposal in [`docs/proposal.pdf`](docs/proposal.pdf) |
| MS2: Feature pipeline | 2026-11-05 | Not started |
| MS3: Training pipeline | 2026-12-03 | Not started |
| MS4: Live system | 2027-01-10 | Not started |

Implementation will follow the weekly module tasks. Later tools listed here are
planned choices, not claims that their setup has already been completed. A personal
data collection exists outside this coursework repository; it is not the MS2
feature pipeline.

## Data and evaluation plan

Results come from [Limitless TCG](https://play.limitlesstcg.com) through its public
JSON API. The planned feature pipeline will backfill historical results and check
for finished tournaments daily. Terms for ongoing API use will be confirmed.

Inputs will include the two Leader IDs, earlier Leader win rates, the earlier rate
for the exact pairing, and each Leader's preceding 28-day win rate. Every rate will
have its supporting match count. For historical examples, features will use only
earlier tournament dates, treating events on the same date as simultaneous.

The label is 1 if the first listed player wins and 0 if that player loses. Models
will be evaluated on later tournaments, using Brier score. The target is below
0.25 and better than a historical Leader-matchup lookup on the same test matches.
Whether ML improves on the baseline has not yet been tested.

## Planned tools

| Tool | Planned role and reason |
|---|---|
| Hopsworks | Store prepared features for training and prediction; a module-supported option |
| Weights & Biases | Track training runs and version models; I have used W&B before, and the module allows it |
| GitHub Actions | Schedule jobs and run automated checks alongside the code |
| Python and scikit-learn | Prepare tabular features and train a manageable gradient boosting classifier |
| FastAPI, Docker and Google Cloud Run | Provide and host a containerised prediction endpoint |
| pytest and uv | Test the calculations and pin dependencies for reproducible environments |

Accounts, permissions and service availability will be checked when those
components are implemented. No free hosting or service plan is assumed.

## Planned architecture

![Planned FTI architecture: Limitless results feed the feature pipeline, which writes to Hopsworks. Training reads features and saves model versions in W&B. Inference reads current features and a selected model to answer a player.](docs/src/architecture.png)

- Feature pipeline: collect results daily, calculate historical rates and save
  features and labels. Backfill uses the same logic for historical results.
- Training pipeline: read prepared examples weekly, train and evaluate a model,
  compare baselines and register a model version with its scores in W&B.
- Inference pipeline: use the selected model and current matchup features to
  return a probability, recent win rates and match counts when a player asks.

The three pipelines will run separately through shared storage. Basic job logging,
deployed model identification and monitoring of changes in Leader usage belong to
the planned core final system. A detailed monitoring dashboard and full-decklist
experiments are optional, after the core works reliably.

## Proposal files

- [`docs/proposal.pdf`](docs/proposal.pdf): current two-page proposal.
- [`docs/src/proposal.typ`](docs/src/proposal.typ): editable Typst source.
- [`docs/src/architecture.svg`](docs/src/architecture.svg): editable diagram source.

To rebuild the PDF with [Typst](https://typst.app):

```sh
typst compile docs/src/proposal.typ docs/proposal.pdf
```

The PDF and Typst source reflect the revised editable proposal as of 1 October
2026. Later Google Doc edits must be synchronised explicitly; there is no automatic
Drive-to-GitHub sync. Previously submitted coursework remains a separate archive.
