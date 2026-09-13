# MSSB Savant Sliders — site

Stars Off advanced player percentiles for Mario Superstar Baseball, published as a
static site on GitHub Pages and refreshed automatically from the Rio database.

## Layout

| Path | What it is |
|---|---|
| `site/index.html` | The dashboard page |
| `site/data/manifest.js` / `.json` | List of seasons: dates, final or in progress, when each was built |
| `site/data/seasons/<slug>.js` | One season's players and all 14 metrics, loaded when that season is picked |
| `build_seasons.py` | Builds whatever season data is due (read-only against the database) |
| `season_metrics.py` | Metric definitions, floors, adjusted ELO and percentile ranking. **Vendored verbatim** from ProjectRio-web |
| `season_metrics_sql.py` | The season discovery rule and the three per-season queries, vendored from ProjectRio-web |
| `.github/workflows/refresh.yml` | Daily refresh + deploy to GitHub Pages |

## The metrics

The site computes Project Rio's season metrics: the same 14 metrics, floors and
percentiles as the `season_metric` table added in
[ProjectRio-web PR #154](https://github.com/ProjectRio/ProjectRio-web/pull/154).
The two definition files are copied from that PR rather than rewritten, and
`build_seasons.py` makes the same three queries per season as Rio's job, so the
numbers match.

Each season file stores, for every player and metric, the same columns as a
`season_metric` row: value, percentile, pool size, numerator, denominator and
whether the player qualified. Players who played at least one game are included,
qualified or not, so anyone can look themselves up.

## How the refresh works

- **Seasons are discovered, not listed**, with Rio's own rule: `tag_set` rows
  typed Season whose name ends in "Superstars Off" or starts with "Stars Off,
  Season", plus S9 Superstars Off (typed League). That is S4 through the current
  season, including Interim. Hazards, Randoms and tournaments never match.
- **Only unfinished seasons are queried.** A season is rebuilt on every run until
  the first run more than 2 days after its `end_date`. That run is its final build,
  and it is never queried again.
- **Season changeover is automatic.** The next season appears once its tag set
  exists and its start date has passed. Nothing needs editing.
- **Daily at about 4 AM ET.** The schedule fires at 08:17 and 09:17 UTC. The first
  run at or after 4 AM Eastern does the work and the other skips, so it stays at
  4 AM through daylight saving changes.
- **Changing the definitions rebuilds everything once.** Each season records a
  fingerprint of `season_metrics.py` and `season_metrics_sql.py`, so editing either
  makes every season stale and the next run rebuilds the whole history.
- **Alert.** If no recognised season has run for 21 days and none is scheduled, the
  workflow fails, and GitHub emails you. The build log lists stars-off tag sets that
  weren't discovered, which is where a renamed season would show up. Fix it by
  adjusting `SEASON_DISCOVERY_SQL` (and the same rule upstream in Rio).

## Run it locally

```
python -m pip install -r requirements.txt
python build_seasons.py --dry-run                   # show what would be built
python build_seasons.py                             # build whatever is due
python build_seasons.py --season s15superstarsoff   # rebuild just one season
```

Locally, credentials come from `DATABASE_CONNECTION.md` in this folder or any
parent folder. Open `site/index.html` directly in a browser; no server is needed.

## Publish on GitHub Pages (one-time setup)

1. **Create a public GitHub repository** and push this folder to its `main` branch.
   Run `git init` **inside `savant-sliders-site`**, never in the parent `Project Rio`
   folder, which holds `DATABASE_CONNECTION.md`. `.gitignore` excludes that file as
   a backstop; still check `git status` before the first commit.
2. **Add the database credentials as secrets** under *Settings → Secrets and
   variables → Actions*: `RIO_DB_HOST`, `RIO_DB_PORT`, `RIO_DB_NAME`,
   `RIO_DB_USER`, `RIO_DB_PASSWORD`.
3. **Turn on Pages** under *Settings → Pages → Build and deployment → Source:
   GitHub Actions*.
4. **Run the workflow once** from *Actions → Refresh Savant Sliders → Run workflow*.
   The site URL appears on the deploy job.

**Before step 4, check that the database accepts connections from GitHub.** If
DigitalOcean *Trusted Sources* is enabled on the database, GitHub's runners (which
have no fixed IP address) will be refused, and the build step fails with a
connection timeout.

## Changing the metrics

Change them upstream in ProjectRio-web first, then copy `app/season_metrics.py` over
`season_metrics.py` unchanged (keep the three-line provenance comment at the top),
and carry any query change into `season_metrics_sql.py`, writing SQLAlchemy's
`:name` parameters as `%(name)s`. If a metric is added, removed or renamed, update
the `METRICS` list in `site/index.html` too. Push: the new fingerprint rebuilds
every season. The page looks metrics up by name, so if the data and the page
disagree it lists what is missing rather than showing wrong numbers.

Once PR #154 is merged and its backfill has run, the build could read the
`season_metric` table directly instead of computing the metrics itself. Only
`collect()` and `season_payload()` would change; the files, manifest and page stay
the same.
