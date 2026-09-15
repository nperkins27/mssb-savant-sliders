"""Player profile data: every game of every Stars Off season and tournament the
site covers, one file per tag set, plus each tournament's champion.

A game is stored once, with both players, the stadium, the score, each team's
runs allowed and outs recorded (for Runs/9 and Runs Against/9, the same sums
the season metrics use) and both rosters. The profile page adds games up for
whatever it shows -- one season or tournament, a calendar year, or all time --
so nothing is precomputed per player.

Built on the same plan as the season files (build_seasons.plan_season): a tag
set is rebuilt while it is in progress and never queried again once final.
Editing this file rebuilds every tag set once.

Tournament champions are not recorded anywhere in Rio, so they are inferred
from each finished tournament's results (see pick_champion), and any pick can
be replaced by hand in trophy_overrides.json.
"""
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from frame_results import STADIUMS

HERE = Path(__file__).resolve().parent
ET = ZoneInfo("America/New_York")

# Bump when the shape of what is written under data/games changes.
GAMES_FORMAT = 1

BOWSER = 9            # character.char_id. Outside Peach's Garden, the team with Bowser had 1st pick.
PEACHS_GARDEN = 4     # game.stadium_id. No reliable draft data there.

# One game row, in this order.
FIELDS = ("day", "stadium", "away", "home", "away_score", "home_score",
          "away_runs_allowed", "away_outs", "home_runs_allowed", "home_outs",
          "away_roster", "home_roster")
# A roster is 9 characters, one symbol per char_id (0-53).
ROSTER_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"

OVERRIDES_FILE = HERE / "trophy_overrides.json"

# "Top players only" on the All players page keeps, as games between top players:
#   * every game of these tournament series (the MBA Champions League);
#   * the last TOP_FINAL_GAMES games of every other tournament, by when they ended;
#   * season games where both players' lifetime Stars Off win rate (wins over
#     decided games, every season and tournament here) is at least TOP_WIN_PCT
#     percent, counting players with at least TOP_MIN_DECIDED decided games
#     (0 = anyone with a decided game).
TOP_ALL_GAMES_SERIES = ("mba",)
TOP_FINAL_GAMES = 6
TOP_WIN_PCT = 65
TOP_MIN_DECIDED = 0

GAMES_SQL = """
SELECT g.game_id, g.date_time_end, g.stadium_id, g.away_player_id, g.home_player_id,
       g.away_score, g.home_score,
       gh.id, gh.date_created, wcu.user_id, lcu.user_id, gh.winner_result_elo, gh.loser_result_elo
FROM game_history gh
JOIN game g ON g.game_id = gh.game_id
LEFT JOIN community_user wcu ON wcu.id = gh.winner_comm_user_id
LEFT JOIN community_user lcu ON lcu.id = gh.loser_comm_user_id
WHERE gh.tag_set_id = %(tag_set_id)s
  -- Aborted uploads: 0 innings, 0-0, and a zeroed roster that reads as all Mario.
  AND g.innings_played > 0
"""

# team_id 0 is the away team and 1 the home team in every Stars Off game.
ROSTERS_SQL = """
SELECT c.game_id, c.team_id, array_agg(c.char_id ORDER BY c.roster_loc),
       SUM(c.runs_allowed), SUM(c.outs_pitched)
FROM game_history gh
JOIN character_game_summary c ON c.game_id = gh.game_id
WHERE gh.tag_set_id = %(tag_set_id)s
GROUP BY c.game_id, c.team_id
"""


def et_day(epoch: float) -> int:
    """Days since 1970-01-01 of the Eastern date the game ended on."""
    return (dt.datetime.fromtimestamp(epoch, ET).date() - dt.date(1970, 1, 1)).days


def day_year(day: int) -> int:
    return (dt.date(1970, 1, 1) + dt.timedelta(days=day)).year


def collect(conn, tag_set_id: int) -> dict:
    """One tag set's games (oldest first) and each player's standing in it."""
    with conn.cursor() as cur:
        cur.execute(ROSTERS_SQL, {"tag_set_id": tag_set_id})
        teams = {(gid, team): (chars, int(ra or 0), int(outs or 0))
                 for gid, team, chars, ra, outs in cur.fetchall()}
        cur.execute(GAMES_SQL, {"tag_set_id": tag_set_id})
        found = cur.fetchall()

    # Final rating: the result ELO on each player's latest rated game, ordered
    # as the season metrics' ELO query orders them.
    elo = {}
    for *_, win_user, lose_user, win_elo, lose_elo in sorted(found, key=lambda r: (r[8] or 0, r[7])):
        for uid, rating in ((win_user, win_elo), (lose_user, lose_elo)):
            if uid is not None and rating is not None:
                elo[uid] = rating

    found.sort(key=lambda r: (r[1], r[8] or 0, r[7]))
    games, skipped = [], 0
    wins, losses = Counter(), Counter()
    for gid, ended, stadium, away, home, a_score, h_score, *_ in found:
        if stadium not in range(len(STADIUMS)) or away is None or home is None:
            skipped += 1
            continue
        a_chars, a_ra, a_outs = teams.get((gid, 0), ([], 0, 0))
        h_chars, h_ra, h_outs = teams.get((gid, 1), ([], 0, 0))
        games.append([et_day(ended), stadium, away, home, a_score, h_score, a_ra, a_outs, h_ra, h_outs,
                      "".join(ROSTER_ALPHABET[c] for c in a_chars if c in range(len(ROSTER_ALPHABET))),
                      "".join(ROSTER_ALPHABET[c] for c in h_chars if c in range(len(ROSTER_ALPHABET)))])
        if a_score != h_score:
            winner, loser = (away, home) if a_score > h_score else (home, away)
            wins[winner] += 1
            losses[loser] += 1
    if skipped:
        print(f"        player games: skipped {skipped} game(s) with no stadium or player")
    players = sorted(set(wins) | set(losses) | {g[2] for g in games} | {g[3] for g in games})
    return {"fields": list(FIELDS), "games": games,
            "standings": [[u, wins[u], losses[u], elo.get(u)] for u in players]}


# --------------------------------------------------------------------------
# tournament champions
# --------------------------------------------------------------------------

def pick_champion(payload: dict) -> dict | None:
    """Rio records no tournament winner, so infer one from the results.

    The champion is the player with the highest final ELO in the tournament
    (ties: more wins, then fewer losses). A tournament's final rating reflects
    who beat whom, including the last rounds, and unlike the last game played
    it isn't thrown off by a stray game uploaded after the bracket ended.

    Three other signals are recorded, and how many agree is kept so doubtful
    picks can be checked by hand:
      * most wins;
      * fewest losses, among players with at least half the most wins;
      * won the final -- the last game played between two of the four highest
        rated players, most likely the grand final.
    """
    standings = [s for s in payload["standings"] if s[1] or s[2]]
    if not standings:
        return None
    by_elo = sorted(standings, key=lambda s: (-(s[3] if s[3] is not None else -1e9), -s[1], s[2]))
    champion = by_elo[0][0]
    max_wins = max(s[1] for s in standings)
    most_wins = [s[0] for s in standings if s[1] == max_wins]
    contenders = [s for s in standings if s[1] >= max_wins / 2]
    fewest = min(s[2] for s in contenders)
    fewest_losses = [s[0] for s in contenders if s[2] == fewest]
    top = {s[0] for s in by_elo[:4]}
    final = None
    i = {f: n for n, f in enumerate(FIELDS)}
    for g in reversed(payload["games"]):
        if g[i["away"]] in top and g[i["home"]] in top and g[i["away_score"]] != g[i["home_score"]]:
            final = g[i["away"]] if g[i["away_score"]] > g[i["home_score"]] else g[i["home"]]
            break
    w, l = next((s[1], s[2]) for s in standings if s[0] == champion)
    return {"user_id": champion, "record": [w, l], "method": "results",
            "signals": {"most_wins": most_wins, "fewest_losses": fewest_losses, "won_final": final},
            "agree": (champion in most_wins) + (champion in fewest_losses) + (final == champion)}


def load_overrides() -> dict:
    if not OVERRIDES_FILE.is_file():
        return {}
    return {k: v for k, v in json.loads(OVERRIDES_FILE.read_text(encoding="utf-8")).items()
            if not k.startswith("_")}


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------

def definitions_fingerprint() -> str:
    h = hashlib.sha256(f"games format {GAMES_FORMAT}\n".encode("utf-8"))
    h.update((HERE / "player_games.py").read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8"))
    return h.hexdigest()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _read_set(path: Path) -> dict | None:
    if not path.is_file():
        return None
    m = re.search(r"\] = (\{.*\});\s*$", path.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1)) if m else None


def load_index(out_dir: Path) -> dict:
    path = out_dir / "index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------

def refresh(conn, discovered: list[dict], now: float, grace_seconds: int, out_dir: Path,
            plan, forced: list[str], dry_run: bool = False) -> None:
    """Bring data/games up to date. plan: build_seasons.plan_season, so games
    follow exactly the same build / keep / skip rules as the season files."""
    fingerprint = definitions_fingerprint()
    index = load_index(out_dir)
    prev = {e["slug"]: e for e in index.get("sets", [])}
    todo, kept = [], 0
    for s in discovered:
        slug = s["name_lowercase"]
        action, _ = plan(s, prev.get(slug), fingerprint, now, slug in forced, out_dir)
        if action == "build":
            todo.append(s)
        kept += action == "keep"
    print(f"  player games: {kept} kept; building {len(todo)}"
          + (": " + "; ".join(s["name"] for s in todo) if todo else ""))
    if dry_run:
        return

    for n, s in enumerate(todo, 1):
        slug = s["name_lowercase"]
        payload = collect(conn, s["id"])
        built = now
        rel = f"{slug}.js"
        _write(out_dir / rel, "/* Generated by build_seasons.py -- do not edit by hand. */\n"
               f"(window.MSSB_GAMES = window.MSSB_GAMES || {{}})[{json.dumps(slug)}] = "
               + json.dumps(payload, separators=(",", ":")) + ";\n")
        days = [g[0] for g in payload["games"]]
        prev[slug] = {
            "slug": slug, "name": s["name"], "kind": s["kind"], **({"series": s["series"]} if s["series"] else {}),
            "tag_set_id": s["id"], "file": rel, "games": len(payload["games"]),
            "first_day": min(days, default=None), "last_day": max(days, default=None),
            "final": built > s["end_date"] + grace_seconds, "built_at": _iso(built),
            "definitions_sha256": fingerprint,
        }
        print(f"  player games: [{n}/{len(todo)}] {s['name']}: {len(payload['games'])} games", flush=True)

    # Everything below is recomputed on every run from the files on disk:
    # the player list (names change), years played, and the champions, so an
    # edit to trophy_overrides.json takes effect on the next build.
    order = [s["name_lowercase"] for s in discovered if s["name_lowercase"] in prev]
    order += sorted(set(prev) - set(order))          # no longer discovered: kept as-is
    sets = [prev[slug] for slug in order]
    players: dict[int, dict] = {}
    years = Counter()        # games per year, for the All players page
    wins, losses = Counter(), Counter()   # lifetime, for top players
    trophies = []
    overrides = load_overrides()
    payloads = {}
    for n, entry in enumerate(sets):
        payload = _read_set(out_dir / entry["file"])
        if payload is None:
            raise SystemExit(f"ERROR: {entry['file']} is missing or unreadable; rebuild with --season {entry['slug']}")
        payloads[entry["slug"]] = payload
        for g in payload["games"]:
            year = day_year(g[0])
            years[year] += 1
            if g[4] != g[5]:
                winner, loser = (g[2], g[3]) if g[4] > g[5] else (g[3], g[2])
                wins[winner] += 1
                losses[loser] += 1
            for uid in (g[2], g[3]):
                p = players.setdefault(uid, {"sets": Counter(), "years": Counter()})
                p["sets"][n] += 1
                p["years"][year] += 1

    with conn.cursor() as cur:
        cur.execute("SELECT id, username FROM rio_user WHERE id = ANY(%s)", (list(players),))
        names = dict(cur.fetchall())
        cur.execute("SELECT char_id, name FROM character ORDER BY char_id")
        characters = [list(r) for r in cur.fetchall()]
    by_name = {(names.get(u) or "").lower(): u for u in players}

    for entry in sets:
        if entry["kind"] != "tournament" or not entry["final"]:
            continue
        payload = payloads[entry["slug"]]
        pick = pick_champion(payload)
        if pick is None:
            continue
        manual = overrides.get(entry["slug"])
        if manual:
            uid = by_name.get(str(manual).lower())
            if uid is None:
                print(f"  WARNING: trophy_overrides.json names {manual!r} for {entry['slug']}, "
                      "but no player by that name has played a Stars Off game; keeping the automatic pick")
            else:
                w, l = next(([s[1], s[2]] for s in payload["standings"] if s[0] == uid), [0, 0])
                pick.update({"user_id": uid, "record": [w, l], "method": "manual"})
        trophies.append({"slug": entry["slug"], "year": day_year(entry["last_day"]), **pick})
    unknown = sorted(set(overrides) - {t["slug"] for t in trophies})
    if unknown:
        print("  WARNING: trophy_overrides.json names tournaments that aren't finished Stars Off "
              "tournaments: " + ", ".join(unknown))

    # index.json is the build's own state (small, read back next run);
    # index.js is everything the page needs.
    _write(out_dir / "index.json", json.dumps({"format": GAMES_FORMAT, "definitions_sha256": fingerprint,
                                               "sets": sets}, indent=1) + "\n")
    index = {
        "format": GAMES_FORMAT,
        "updated_at": _iso(now),
        "fields": list(FIELDS),
        "roster_alphabet": ROSTER_ALPHABET,
        "bowser": BOWSER,
        "peachs_garden": PEACHS_GARDEN,
        "stadiums": list(STADIUMS),
        "characters": characters,
        "sets": sets,
        "years": dict(sorted(years.items())),
        "players": sorted(([uid, names.get(uid) or f"user {uid}", dict(p["sets"]), dict(p["years"])]
                           for uid, p in players.items()), key=lambda r: r[1].lower()),
        "trophies": trophies,
        "top_players": {
            "all_games_series": list(TOP_ALL_GAMES_SERIES),
            "final_games": TOP_FINAL_GAMES,
            "min_win_pct": TOP_WIN_PCT,
            "min_decided": TOP_MIN_DECIDED,
            # [user_id, lifetime wins, lifetime losses], most decided games first
            "players": sorted(([u, wins[u], losses[u]] for u in set(wins) | set(losses)
                               if wins[u] + losses[u] >= max(TOP_MIN_DECIDED, 1)
                               and 100 * wins[u] >= TOP_WIN_PCT * (wins[u] + losses[u])),
                              key=lambda r: (-(r[1] + r[2]), (names.get(r[0]) or "").lower())),
        },
    }
    body = json.dumps(index, separators=(",", ":"))
    _write(out_dir / "index.js", "/* Generated by build_seasons.py -- do not edit by hand. */\n"
                                 "window.MSSB_GAMES_INDEX = " + body + ";\n")
    doubtful = [t for t in trophies if t["method"] == "results" and t["agree"] < 2]
    print(f"  player games: {sum(e['games'] for e in sets):,} games, {len(players):,} players, "
          f"{len(trophies)} champions ({sum(t['method'] == 'manual' for t in trophies)} set by hand"
          + (f"; worth checking: {', '.join(t['slug'] for t in doubtful)}" if doubtful else "") + ")")
