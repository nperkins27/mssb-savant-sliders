# MSSB Savant Sliders — site

Stars Off advanced player percentiles for Mario Superstar Baseball, published as a
static site on GitHub Pages and refreshed automatically from the Rio database.

## Layout

| Path | What it is |
|---|---|
| `site/index.html` | The dashboard page |
| `site/data/manifest.js` / `.json` | List of seasons: dates, final or in progress, when each was built |
| `site/data/seasons/<slug>.js` | One season's player rows, loaded when that season is picked |
| `build_seasons.py` | Builds whatever season data is due (read-only against the database) |
| `mssb_savant_sliders.sql` | The Savant Sliders query the build runs once per season |
| `.github/workflows/refresh.yml` | Daily refresh + deploy to GitHub Pages |

## How the refresh works

- **Seasons are discovered, not listed.** Each run reads `tag_set` for main-line
  Superstars Off seasons (`S15 Superstars Off`, `Stars Off, Season 7`,
  `Interim Superstars Off`) that carry the Disable Superstars code, starting at
  Season 7. Hazards, Randoms, tournaments and so on never match.
- **Only unfinished seasons are queried.** A season is rebuilt on every run until
  the first run more than 2 days after its `end_date`. That run is its final build,
  and it is never queried again.
- **Season changeover is automatic.** The next season appears once its tag set
  exists and its start date has passed. Nothing needs editing.
- **Daily at about 4 AM ET.** The schedule fires at 08:17 and 09:17 UTC. The first
  run at or after 4 AM Eastern does the work and the other skips, so it stays at
  4 AM through daylight saving changes.
- **Changing the SQL rebuilds everything once.** Each season records a fingerprint
  of the query that built it, so editing `mssb_savant_sliders.sql` makes every
  season stale and the next run rebuilds the whole history (about 17 minutes).
- **Alert.** If no recognised season has run for 21 days and none is scheduled, the
  workflow fails, and GitHub emails you. The build log lists stars-off tag sets that
  didn't match, which is where a renamed season would show up. Fix it by adjusting
  `SEASON_NAME_PATTERN` in `build_seasons.py`.

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

The page reads columns by name. To change the metric set, edit
`mssb_savant_sliders.sql` and the `METRICS` list in `site/index.html` together, then
push. The push triggers a run, and the new SQL fingerprint rebuilds every season.
If the two disagree, the page names the missing columns rather than showing
wrong numbers.
