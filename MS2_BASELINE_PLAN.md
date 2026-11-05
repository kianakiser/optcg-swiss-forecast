# MS2 baseline study plan

## Development results, 3 November 2026

A historical replay used 1,689 decided matches from 17 September 2025 tournaments. Every tournament on a given date received the same earlier-history snapshot. Lower Brier loss is better.

| Rule | Development Brier loss |
| --- | ---: |
| Always 50% | 0.25000 |
| Overall Leader estimate | 0.24582 |
| Pair estimate with reference weight 64 and a five-meeting fallback | 0.24510 |

The pair rule improved by 0.00072 overall and had lower loss in 10 of 17 tournaments. A lightly smoothed estimate did poorly when the pairing had only 1–4 earlier meetings. That observation motivated the fallback. The figures come from development data used to explore settings.

We tried reference weights 1, 4, 16 and 64, each with a minimum of one or five earlier meetings. At weight 64, starting from the first meeting scored 0.244973 and beat the Leader reference in 9 of 17 tournaments. Waiting until five meetings scored 0.245100 and beat the reference in 10. The cutoff slightly worsened match-weighted loss. We kept it as a conservative candidate, not a demonstrated improvement. We chose powers of four to cover a wide range in four trials. With five direct games, weights 1, 4, 16 and 64 give those games 83%, 56%, 24% and 7% of the estimate. In a follow-up on the same development games, we extended the same spacing to 256 and 1,024. With the five-game cutoff their losses were 0.245430 and 0.245698 versus 0.245100 at 64. With the one-game cutoff they were 0.245391 and 0.245688 versus 0.244973 at 64. This supports carrying 64 forward among the six values tried. It does not establish an optimum. At five meetings, the direct record gets only 5/69 of the weight. Keep this candidate fixed for the later comparison and report the result even if it misses the margin.

Across the 17 development tournaments, the pair rule's loss minus the Leader reference
ranged from -0.00685 to +0.00411. Fourteen events, containing 1,461 of the 1,689
matches, came from one organiser. These differences describe this sample and are
not a confidence interval.

On 4 November, details metadata for all 66 history events and 17 development events
confirmed OP, at least 32 official participants and an explicitly Swiss first phase.
Dates and participant counts matched the archive. That does not establish when
results were published. The later evaluation below remains unopened.

## Protocol for the later comparison

Use archived events dated 1 July through 30 September 2026 inclusive. Available event dates currently end on 17 September. Of 43 archived events, one is explicitly marked 3v3. The other 42 are candidates. Verify game, individual format, participant count of at least 32, Swiss phases and decided results. Apply the same eligibility rules to the historical inputs. Keep an exclusion log.

Before each test date, use only eligible results from earlier dates that were already available. Freeze history for all events sharing a date. Then update it for subsequent dates. Check completion and possible overlaps. Where availability cannot be established, exclude those inputs from the verified run and report coverage. If reliable history is insufficient, label any date-based replay preliminary.

For Leader A against B, the reference probability q is the average of A’s earlier win rate and B’s earlier loss rate. Use 50% for an unseen Leader’s rate. Below five earlier direct meetings, predict q. From five meetings onward, predict (w + 64 × q) / (n + 64), where w is A’s earlier direct wins and n is the number of earlier physical meetings. Identical Leaders receive 50%. The weight of 64 controls how strongly the estimate moves toward q.

Compare the three rules on identical matches. Score both orientations, average them within each physical match, and report the match-weighted overall Brier loss plus paired differences per tournament. For this comparison, a practically useful gain means the pair rule reduces overall Brier loss by at least 0.0025 against the Leader reference. This threshold equals 1% of the 0.25 coin-flip loss. It is a project judgment about useful improvement. Also report performance against the coin flip, the spread across tournaments and organiser concentration. Report the outcome even if the pair rule misses the threshold.

## Remaining checks

Verify that swapped forecasts sum to one. Investigate listing order separately when pre-round seed information is available. Explore deck composition as an independent input only if both lists could legitimately be known before prediction. No placement or age multiplier enters these three rules.

The 28-day features are now implemented in the local draft. They are inputs for
later model training and do not change the three baseline formulas above.

[Probability scoring](https://doi.org/10.1198/016214506000001437) · [Estimating rates with sparse sports data](https://doi.org/10.1214/07-AOAS138) · [Forecast comparison uncertainty](https://arxiv.org/abs/2605.03997v2)
