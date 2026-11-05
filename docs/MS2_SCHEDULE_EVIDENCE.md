# MS2 scheduled execution on 5 November 2026

The repository’s [daily workflow](../.github/workflows/features.yml) runs at 21:17 UTC on GitHub Actions. I also used a one-time macOS calendar timer to start the same published workflow when no native GitHub schedule event had appeared. The timer checked GitHub first and skipped dispatch if a native run was underway or had succeeded.

The timer was registered before 22:51 Zurich and ran automatically. Its calendar settings were month 11, day 5, hour 22 and minute 51, with no run at registration. macOS recorded one start and exit code 0. I removed the timer after that start.

The timer wrote this log (UTC):

```text
Clock started: 2026-11-05T21:51:04Z
Timezone: CET
Dispatching the reviewed daily workflow from the macOS calendar timer.
https://github.com/kianakiser/optcg-swiss-forecast/actions/runs/42116342596
Dispatch completed: 2026-11-05T21:51:07Z
```

GitHub created [the timer-triggered run](https://github.com/kianakiser/optcg-swiss-forecast/actions/runs/42116342596) at 21:51:06 UTC. Its event is `workflow_dispatch` because the external clock called the GitHub workflow. The [earlier verification run](https://github.com/kianakiser/optcg-swiss-forecast/actions/runs/42111485827) was started manually. The [native GitHub schedule history](https://github.com/kianakiser/optcg-swiss-forecast/actions/workflows/features.yml?query=event%3Aschedule) lists runs started by GitHub’s own clock.

The timer-triggered job succeeded. It found 35 tournaments awaiting review, saved the dated source snapshot and read back all 1,290 Hopsworks rows with matching keys, labels and feature values. The run log records verification at 21:52:27 UTC.
