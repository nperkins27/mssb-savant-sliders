# MSSB Savant Sliders — site

Stars Off advanced player percentiles for Mario Superstar Baseball, published as a
static site on GitHub Pages and refreshed automatically from the Rio database.

## Layout

| Path | What it is |
|---|---|
| `site/index.html` | Leaderboard page: one season, ranked by a chosen metric, with one player's sliders |
| `site/compare.html` | Compare page: 2 to 12 season + player cards, reorderable by drag. The comparison is kept in the URL (`#c=<season>[+<season>...]~<user id>,...`) |
| `site/profile.html` | Player profile page: record, runs, stadium and character-pick tables and tournament trophies, for a season, tournament, year or all time. Kept in the URL (`#u=<user id>&v=<view>`) |
| `site/players.html` | All players page: the same tables for every game combined (`#v=<view>`) |
| `site/profile.js` / `profile.css` | Code and styles shared by the two profile pages |
| `site/data/games/` | Every game, one file per season or tournament, plus `index.js` (players, years, tournament champions) |
| `player_games.py` | Builds `site/data/games/`; called by `build_seasons.py` |
| `trophy_overrides.json` | Tournament champions set by hand, replacing the automatic pick |
| `site/frames.html` | Frame results page: what happens when a character hits the ball on each frame, with ten filters |
| `site/data/frames/` | The frame results counts: `index.js`, plus one file per character in `final/` (finished seasons and tournaments) and `live/` (in progress) |
| `frame_results.py` | Builds `site/data/frames/`; called by `build_seasons.py` |
| `site/shared.js` | Used by both pages: the metric list, the **metric definitions text** (`DEFINITIONS`), season loading and the definitions dialog |
| `site/shared.css` | Styles used by both pages |
| `site/data/manifest.js` / `.json` | List of seasons: dates, final or in progress, when each was built |
| `site/data/seasons/<slug>.js` | One season's players and all 20 metrics, loaded when that season is picked |
| `build_seasons.py` | Builds whatever season data is due (read-only against the database) |
| `season_metrics.py` | Metric definitions, floors, adjusted ELO and percentile ranking. **Vendored verbatim** from ProjectRio-web |
| `season_metrics_sql.py` | The season discovery rule and the three per-season queries, vendored from ProjectRio-web |
| `.github/workflows/refresh.yml` | Daily refresh + deploy to GitHub Pages |

## The metrics

The site computes Project Rio's season metrics: the same metrics, floors and
percentiles as the `season_metric` table added in
[ProjectRio-web PR #154](https://github.com/ProjectRio/ProjectRio-web/pull/154).
The two definition files are copied from that PR rather than rewritten, and
`build_seasons.py` makes the same four queries per season as Rio's job, so the
numbers match.

**20 metrics.** The PR's 14, plus six that are not pushed to the PR yet:
Runs/9 and Runs Against/9 (general); 2-Strike Whiff % (batting: whiffs ÷ swings
on pitches thrown with two strikes already in the count), Star Swing Barrel %
(batting: Barrel % on star swing contacts only, needs 25 in a season) and Star
Slugging % (batting: bases gained on star swings ÷ stars used, needs 25 stars
used in a season); and Special Catches/9 (pitching/fielding).
Per-9 metrics are 27 × count ÷ outs: runs against and special catches over the
outs the player's team recorded in the field, runs over the outs it made at bat.
Star Slugging % counts every star swing, including misses, fouls and outs
(0 bases). A star swing uses 1 star, or 2 when a captain-eligible character who
isn't the team's captain makes contact (fouls included).

Each season file stores, for every player and metric, the same columns as a
`season_metric` row: value, percentile, pool size, numerator, denominator and
whether the player qualified. Players who played at least one game are included,
qualified or not, so anyone can look themselves up.

### Tournaments: Netplay Superstars, SLICE, Bobble and MBA Champions League

Tournaments are stars-off tag sets matched by name:

- **Netplay Superstars**: "Netplay Superstars NN" or "NPSSNN" (typed Tournament).
- **SLICE**: the official stars-off event each year ("SLICE 2023, Stars Off",
  "SLICE 2024 Superstars Off" onward; typed Tournament). Practice and Friendly
  SLICE modes are excluded.
- **Bobble**: "Bobble: Stars-Off (Bracket)" (2025) and "Bobble YYYY" (2026 on;
  typed Tournament). Big Balla and non-bracket modes are excluded.
- **MBA Champions League**: "MBA Champions League YYYY". Matched by name alone,
  since Rio types 2024 as League and 2025 as Season.

Every one must also carry the Disable Superstars tag. They are listed alongside
the seasons, with the same 20 metrics but **no qualification minimums**: every
player who played at least one game is ranked on every metric they have data for. This is a site choice; Rio's
`season_metric` table covers seasons only. `build_seasons.py` ranks them with
Rio's own `build_rows()`, switching the floors off only while a tournament is
built, and the pages say "no minimums" wherever a tournament is shown.

### Multiple selections

Both pages can select several seasons and/or tournaments at once. `shared.js`
then combines them in the browser: each player's numerators, denominators and
games are summed across the selection, every rate is recomputed from the totals,
and players are ranked with a JavaScript port of Rio's `qualifies()` and
`percentile_ranks()`. Season minimums apply to the combined totals; a selection
that includes a tournament has none. ELO has no combined value and shows n/a.
Nothing is precomputed for combinations, so the build and data files are
unchanged.

Both pages also have an optional **Minimum games** box (on the compare page it
applies to every card and is kept in the URL as `&min=N`). When it's filled in,
it replaces the games minimum for whatever is selected, up or down: only players
with at least that many games (summed across a multiple selection) are ranked,
and the same browser-side ranking recalculates every percentile, ELO included for
a single season or tournament. In seasons the other minimums still apply; with a
tournament selected there are none. Set to a selection's usual minimum, it
reproduces the built files exactly. Combining a single season reproduces its built file exactly, and
combinations match `build_rows()` run on the same summed counts in Python.

## Player profiles

The Player profile page covers every game of every season and tournament
above, for one player, filtered to a single season or tournament, a calendar
year (the Eastern date each game ended) or all time.

- **ELO** is the leaderboard's ELO for that season or tournament, so it is
  hidden for a year or all time. **Wins, losses, Runs/9 and Runs Against/9**
  are added up from the games; Runs/9 and Runs Against/9 use the same sums as
  the leaderboard.
- **Stadium Record**: win % and record per stadium, optionally split by home and
  away and by 1st and 2nd pick. 1st pick is the team with Bowser, who always
  goes first outside Peach's Garden. Peach's Garden has no reliable draft data,
  so it shows overall records only.
- **Character Picks**: the share of the player's games with each character on
  their team, per stadium and pick, sortable by any column.
- **Tournament Trophy Case** (a tournament, a year or all time): tournaments the
  player won. Rio doesn't record champions, so `player_games.pick_champion()`
  names the player with the highest final ELO in each finished tournament, and
  records whether they also had the most wins, the fewest losses and won the
  last game between top-rated players. To correct a pick, add
  `"<tournament slug>": "<username>"` to `trophy_overrides.json` and push.

The **All players** page shows the same Stadium Record and Character Picks for
every game combined, counting each game once for each team, so wins and losses
always balance. Its tiles are games, players, Runs/9 across every game, the home
team's win % and the 1st pick's win %.

Games with 0 innings played (aborted uploads with zeroed rosters) are left out.
Each tag set's games file follows the same build rules as its season file, so
finished ones are never queried again.

## Frame results

The Frame results page pools every slap, charge and star swing contact from
every season and tournament above, and shows, for each frame of the swing, how
those contacts turned out: Foul, Home Run, On Base or Out (Home Run folds into
On Base when Separate HRs is off). Ten filters narrow it down: character,
batting hand, type of contact, type of swing, frame, stick input, result,
stadium, Separate HRs and chemistry links on base.

Results are classified by what the at-bat did (`event.result_of_ab`), because
`contact_summary.secondary_result` alone calls some fouls outs and some force
outs fouls:

- **Foul**: the at-bat carried on after the contact.
- **On Base**: single, double, triple, or reached on an error.
- **Home Run**.
- **Out**: everything else, including fielder's choices (secondary result 4:
  the batter reaches but a runner is out), foul catches, sac flies, double
  plays and forced outs.

Bunts (no swing) aren't counted, and neither are aborted uploads with 0 innings
played, whose rosters read as all Mario.

The build stores counts, not contacts: contacts are counted per combination of
the nine filterable dimensions, and the page adds up the combinations that match
the filters. Finished
seasons and tournaments are pooled once into `data/frames/final/` and never
queried again; a tag set is added to that pool on the first run after it
finishes. Those still in progress are rebuilt into `data/frames/live/` on
every run. Editing `frame_results.py` rebuilds the finished pool once.

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
the `METRICS` list and `DEFINITIONS` in `site/shared.js` too. Push: the new fingerprint rebuilds
every season. The page looks metrics up by name, so if the data and the page
disagree it lists what is missing rather than showing wrong numbers.

Once PR #154 is merged and its backfill has run, the build could read the
`season_metric` table directly instead of computing the metrics itself. Only
`collect()` and `season_payload()` would change; the files, manifest and page stay
the same.
