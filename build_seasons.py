#!/usr/bin/env python3
"""Build the MSSB Savant Sliders site data: one file per season plus a manifest.

Run it any time -- it only does the work that is still due.

  * The metrics are Project Rio's season metrics. season_metrics.py and
    season_metrics_sql.py are vendored from ProjectRio-web PR #154, and
    collect() below makes the same three queries as Rio's job, so every number
    matches what the season_metric table holds.
  * Seasons are discovered with Rio's own rule: main-line Stars Off tag sets
    from Season 4 on, plus S9, which is typed League.
  * A season that has started and is not final gets rebuilt. It becomes final
    on the first build that runs more than GRACE_DAYS after its end_date, and
    is never queried again after that.
  * Every season records a fingerprint of the definitions that built it.
    Editing either vendored file makes every season stale, so a metric change
    rebuilds the history once, automatically.

Credentials come from the RIO_DB_HOST / _PORT / _NAME / _USER / _PASSWORD
environment variables (GitHub Actions secrets) or, failing that, from
DATABASE_CONNECTION.md in this folder or a parent. The connection is forced
read-only server-side, so a bug here cannot write to the database.

Usage:
    python build_seasons.py                              # build whatever is due
    python build_seasons.py --dry-run                    # show the plan only
    python build_seasons.py --season s15superstarsoff    # rebuild just this one
    python build_seasons.py --scheduled                  # cron mode (see due_today)

Requires: pip install -r requirements.txt
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import season_metrics as sm
import season_metrics_sql as q

HERE = Path(__file__).resolve().parent
ET = ZoneInfo("America/New_York")

DISABLE_SUPERSTARS_TAG = 10        # tag.id of the gecko code every stars-off season carries
GRACE_DAYS = 2                     # games finishing after midnight, late uploads
ALERT_GAP_DAYS = 21                # no recognised season for this long -> alert
DAILY_AT_ET = dt.time(4, 0)

# The files whose content defines the numbers. Bump DATA_FORMAT when the shape
# of what is written under site/data changes, so every season is rewritten.
DEFINITION_FILES = ("season_metrics.py", "season_metrics_sql.py")
DATA_FORMAT = 2

# What is stored for each (player, metric), in this order -- the same columns
# as a season_metric row.
FIELDS = ("value", "percentile", "pool_size", "numerator", "denominator", "qualified")

SEASONS_SQL = """
select id, name, name_lowercase, start_date, end_date
from tag_set
where id in (""" + q.SEASON_DISCOVERY_SQL + """)
order by start_date
"""

# Stars-off tag sets that look like a season but were not discovered --
# printed when the gap alert fires, to show what the new season is called.
CANDIDATES_SQL = """
select ts.name, ts.type,
       to_char(to_timestamp(ts.start_date), 'YYYY-MM-DD') as starts,
       count(gh.id) filter (
           where gh.date_created > extract(epoch from now()) - 14 * 86400
       ) as games_last_14_days
from tag_set ts
join tag_set_tag tst on tst.tagset_id = ts.id and tst.tag_id = %(tag)s
left join game_history gh on gh.tag_set_id = ts.id
where ts.type in ('Season', 'League')
  and ts.start_date > %(since)s
  and not ts.id = any(%(known)s)
group by ts.id
order by ts.start_date desc
"""


# --------------------------------------------------------------------------
# credentials
# --------------------------------------------------------------------------

def find_guide() -> Path:
    """Look for DATABASE_CONNECTION.md next to this script, then up the tree."""
    for d in (HERE, *HERE.parents):
        c = d / "DATABASE_CONNECTION.md"
        if c.is_file():
            return c
        if d.name.lower() in ("users", "home") or d == d.parent:
            break
    return HERE / "DATABASE_CONNECTION.md"  # non-existent; caller reports it


def parse_guide(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")

    def grab(pattern: str, label: str) -> str:
        m = re.search(pattern, text)
        if not m:
            raise SystemExit(f"ERROR: could not find {label} in {path}")
        return m.group(1).strip()

    host, port = grab(r"POSTGRES_URL\s*=\s*(\S+)", "POSTGRES_URL").rsplit(":", 1)
    return {
        "host": host,
        "port": port,
        "name": grab(r"POSTGRES_DB\s*=\s*(\S+)", "POSTGRES_DB"),
        "user": grab(r"POSTGRES_USER\s*=\s*(\S+)", "POSTGRES_USER"),
        "password": grab(r"password\s*=\s*(\S+)", "password"),
    }


def db_params(guide_arg: str | None) -> dict:
    keys = ("host", "port", "name", "user", "password")
    env = {k: os.environ.get("RIO_DB_" + k.upper(), "") for k in keys}
    if all(env.values()):
        creds, source = env, "RIO_DB_* environment variables"
    elif any(env.values()):
        missing = ", ".join("RIO_DB_" + k.upper() for k in keys if not env[k])
        raise SystemExit(f"ERROR: some RIO_DB_* variables are set but not: {missing}")
    else:
        guide = Path(guide_arg) if guide_arg else find_guide()
        if not guide.is_file():
            raise SystemExit(
                "ERROR: no credentials. Set the RIO_DB_HOST, RIO_DB_PORT, "
                "RIO_DB_NAME, RIO_DB_USER and RIO_DB_PASSWORD environment "
                "variables, or put DATABASE_CONNECTION.md in this folder or a "
                "parent (or pass --guide)."
            )
        creds, source = parse_guide(guide), str(guide)
    print(f"credentials: {source}")
    # Never print these values: on a public repository the Actions log is public.
    return {
        "host": creds["host"],
        "port": int(creds["port"]),
        "dbname": creds["name"],
        "user": creds["user"],
        "password": creds["password"],
        "sslmode": "require",
        # The server itself rejects any write, whatever the SQL says.
        "options": "-c default_transaction_read_only=on -c statement_timeout=30min",
        "connect_timeout": 15,
    }


def redact(message: str, params: dict) -> str:
    """Strip connection details from a driver error before it reaches a log.
    GitHub masks secret values, but not the server IP a connection error
    names, and Actions logs on a public repository are public."""
    for key in ("password", "host", "user", "dbname"):
        if params.get(key):
            message = message.replace(str(params[key]), "***")
    message = re.sub(r"hostaddr: '[^']*'", "hostaddr: '***'", message)
    message = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "***", message)                  # IPv4
    return re.sub(r"(?i)(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\w:])",    # IPv6,
                  "***", message)                                                    # incl. ::1


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------

def definitions_fingerprint() -> str:
    # Line endings normalised: a Windows checkout (CRLF) and the Linux runner
    # (LF) must agree, or every season would look stale on the first CI run.
    h = hashlib.sha256(f"data format {DATA_FORMAT}\n".encode("utf-8"))
    for name in DEFINITION_FILES:
        h.update((HERE / name).read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8"))
    return h.hexdigest()


def discover(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(SEASONS_SQL, {"exceptions": list(q.SEASON_ID_EXCEPTIONS)})
        names = [d[0] for d in cur.description]
        seasons = [dict(zip(names, r)) for r in cur.fetchall()]
    if not seasons:
        raise SystemExit("ERROR: no seasons discovered")
    return seasons


def collect(conn, tag_set_id: int) -> dict:
    """Everything season_metrics.build_rows() needs for one season. The same
    four queries as Rio's season_metrics_db.collect(), on one connection."""
    per_user = {}

    def record(user_id):
        if user_id not in per_user:
            per_user[user_id] = {"games": 0, "elo_rating": None, "elo_wins": 0,
                                 "elo_games": 0, "counts": {}}
        return per_user[user_id]

    with conn.cursor() as cur:
        cur.execute(q.GAMES_SQL, {"tag_set_id": tag_set_id})
        for user_id, games in cur.fetchall():
            record(user_id)["games"] = games

        cur.execute(q.ELO_SQL, {"tag_set_id": tag_set_id})
        for user_id, wins, games, rating in cur.fetchall():
            rec = record(user_id)
            rec["elo_wins"] = wins
            rec["elo_games"] = games
            rec["elo_rating"] = rating

        cur.execute(q.AGGREGATE_SQL, {"tag_set_id": tag_set_id,
                                      "charge_chars": list(sm.cCHARGE_TIMING_CHARS),
                                      "power_chars": list(sm.cPOWER_CHARS)})
        for row in cur.fetchall():
            role, user_id = row[0], row[1]
            order = q.BATTING_ORDER if role == "bat" else q.PITCHING_ORDER
            counts = record(user_id)["counts"]
            for i, metric in enumerate(order):
                counts[metric] = (row[2 + i * 2], row[3 + i * 2])

        # After the aggregate: special catches take their denominator from here.
        cur.execute(q.RUNS_SQL, {"tag_set_id": tag_set_id})
        for user_id, *sums in cur.fetchall():
            # SUM() arrives as Decimal; the counts are whole numbers.
            runs_scored, outs_batting, runs_allowed, outs_fielding = (int(s or 0) for s in sums)
            counts = record(user_id)["counts"]
            counts["gen_runs_per_9"] = (runs_scored, outs_batting)
            counts["gen_runs_against_per_9"] = (runs_allowed, outs_fielding)
            special = counts.get("pitch_special_catches_per_9", (0, None))[0] or 0
            counts["pitch_special_catches_per_9"] = (special, outs_fielding)
    return per_user


def season_payload(conn, per_user: dict) -> tuple[dict, int]:
    """build_rows() output reshaped for the page: one entry per player holding
    every metric. Returns (payload, players who met the games floor)."""
    slot = {m: i for i, m in enumerate(sm.cSEASON_METRICS)}
    by_user = {uid: [None] * len(slot) for uid in per_user}
    for r in sm.build_rows(per_user):
        by_user[r["user_id"]][slot[r["metric"]]] = [
            round(r[f], 6) if isinstance(r[f], float) else r[f] for f in FIELDS]

    with conn.cursor() as cur:
        cur.execute("select id, username from rio_user where id = any(%s)", (list(by_user),))
        names = dict(cur.fetchall())
    players = sorted(([uid, names.get(uid) or f"user {uid}", metrics]
                      for uid, metrics in by_user.items()),
                     key=lambda p: p[1].lower())
    games_slot, qualified_field = slot["gen_games_played"], FIELDS.index("qualified")
    qualified = sum(1 for p in players if p[2][games_slot][qualified_field])
    return {"metrics": list(sm.cSEASON_METRICS), "fields": list(FIELDS),
            "players": players}, qualified


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------

def iso_utc(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat(timespec="seconds")


def et_date(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, ET).date().isoformat()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def load_manifest(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"seasons": []}


def save_manifest(out_dir: Path, manifest: dict) -> None:
    body = json.dumps(manifest, indent=1)
    atomic_write(out_dir / "manifest.json", body + "\n")
    atomic_write(out_dir / "manifest.js",
                 "/* Generated by build_seasons.py -- do not edit by hand. */\n"
                 "window.MSSB_MANIFEST = " + body + ";\n")


def write_season(out_dir: Path, slug: str, payload: dict) -> str:
    rel = f"seasons/{slug}.js"
    atomic_write(out_dir / rel,
                 "/* Generated by build_seasons.py -- do not edit by hand. */\n"
                 f"(window.MSSB_SEASONS = window.MSSB_SEASONS || {{}})[{json.dumps(slug)}] = "
                 + json.dumps(payload, separators=(",", ":")) + ";\n")
    return rel


def emit(**outputs) -> None:
    """Hand results to later GitHub Actions steps; a no-op when run locally."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in outputs.items():
                f.write(f"{k}={v}\n")


# --------------------------------------------------------------------------
# planning
# --------------------------------------------------------------------------

def due_today(manifest: dict, now: float) -> bool:
    """Cron mode. GitHub cron is UTC with no daylight saving, so the workflow
    fires twice (08:17 and 09:17 UTC). Whichever run is the first at or after
    4 AM Eastern does the work; the other one skips. A delayed run still
    counts, and a failed run leaves the day open for the second one."""
    local = dt.datetime.fromtimestamp(now, ET)
    if local.time() < DAILY_AT_ET:
        print(f"scheduled: {local:%H:%M} ET is before {DAILY_AT_ET:%H:%M} ET -- skipping")
        return False
    if manifest.get("last_scheduled_run_et") == local.date().isoformat():
        print(f"scheduled: already ran for {local.date()} ET -- skipping")
        return False
    return True


def plan_season(s: dict, prev: dict | None, fingerprint: str, now: float,
                forced: bool, out_dir: Path) -> tuple[str, str]:
    """-> (action, reason) where action is 'skip', 'keep' or 'build'."""
    if s["start_date"] > now:
        return "skip", f"starts {et_date(s['start_date'])}"
    ends_final = now > s["end_date"] + GRACE_DAYS * 86400
    if forced:
        return "build", "forced"
    if prev is None:
        return "build", "new season"
    if not (out_dir / prev["file"]).is_file():
        return "build", "data file missing"
    if prev.get("definitions_sha256") != fingerprint:
        return "build", "definitions changed"
    if prev.get("final"):
        return "keep", "final"
    return "build", "final build" if ends_final else "in progress"


def season_gap_alert(conn, seasons: list[dict], now: float) -> str:
    grace = GRACE_DAYS * 86400
    if any(s["start_date"] <= now <= s["end_date"] + grace for s in seasons):
        return ""   # a season is running
    if any(s["start_date"] > now for s in seasons):
        return ""   # the next season already exists and is scheduled
    latest_end = max(s["end_date"] for s in seasons)
    if now - latest_end < ALERT_GAP_DAYS * 86400:
        return ""   # an ordinary break between seasons
    print(f"\nALERT: no recognised season since {et_date(latest_end)}.")
    print("Stars-off Season/League tag sets created since then that were NOT discovered:")
    with conn.cursor() as cur:
        cur.execute(CANDIDATES_SQL, {"tag": DISABLE_SUPERSTARS_TAG,
                                     "since": latest_end - 7 * 86400,
                                     "known": [s["id"] for s in seasons]})
        found = cur.fetchall()
    for name, typ, starts, recent in found:
        print(f"  {name!r:40} {typ:8} starts {starts}  games in last 14 days: {recent}")
    if not found:
        print("  (none)")
    return (f"No Superstars Off season recognised since {et_date(latest_end)}. "
            "If a new season started under a name the discovery rule misses, update "
            "SEASON_DISCOVERY_SQL (candidates are in the build log).")


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", default=str(HERE / "site" / "data"))
    ap.add_argument("--guide", default=None, help="path to DATABASE_CONNECTION.md")
    ap.add_argument("--season", action="append", default=[], metavar="SLUG",
                    help="rebuild only this season, even if final (repeatable), "
                         "e.g. s15superstarsoff")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be built, write nothing")
    ap.add_argument("--scheduled", action="store_true",
                    help="cron mode: run once per Eastern day, at or after 4 AM")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    manifest = load_manifest(out_dir / "manifest.json")
    now = time.time()

    if args.scheduled and not due_today(manifest, now):
        emit(ran="false")
        return

    fingerprint = definitions_fingerprint()
    params = db_params(args.guide)

    import psycopg
    print("connecting to the Rio database (read-only enforced)...", flush=True)
    try:
        conn = psycopg.connect(**params)
    except psycopg.OperationalError as e:
        raise SystemExit("ERROR: could not connect: " + redact(str(e), params)) from None
    with conn:
        discovered = discover(conn)
        known = {s["name_lowercase"] for s in discovered}
        unknown = [slug for slug in args.season if slug not in known]
        if unknown:
            raise SystemExit("ERROR: unknown season(s): " + ", ".join(unknown)
                             + "\nknown: " + ", ".join(sorted(known)))

        prev_by_slug = {e["slug"]: e for e in manifest.get("seasons", [])}
        plan = []
        print()
        for s in discovered:
            slug = s["name_lowercase"]
            if args.season and slug not in args.season:
                action, reason = "skip", "not selected"
            else:
                action, reason = plan_season(s, prev_by_slug.get(slug), fingerprint, now,
                                             bool(args.season), out_dir)
            plan.append((s, action))
            print(f"  {s['name']:28} {action:5}  {reason}")
        vanished = set(prev_by_slug) - known
        for slug in sorted(vanished):
            print(f"  WARNING: {slug} is in the manifest but no longer discovered; "
                  "keeping its data as-is")
        print()

        if args.dry_run:
            print("dry run -- nothing written")
            return

        def entries(current: dict) -> list[dict]:
            """Manifest season list in discovery order, vanished seasons kept."""
            out = [current[s["name_lowercase"]] for s, _ in plan
                   if s["name_lowercase"] in current]
            return out + [prev_by_slug[v] for v in sorted(vanished)]

        manifest["metric_rules"] = {m: list(rule) for m, rule in sm.cMETRIC_RULES.items()}
        current = dict(prev_by_slug)
        todo = [s for s, action in plan if action == "build"]
        for n, s in enumerate(todo, 1):
            slug = s["name_lowercase"]
            print(f"[{n}/{len(todo)}] {s['name']}  running...", flush=True)
            t0 = time.time()
            payload, qualified = season_payload(conn, collect(conn, s["id"]))
            built = time.time()
            final = built > s["end_date"] + GRACE_DAYS * 86400
            current[slug] = {
                "slug": slug,
                "name": s["name"],
                "tag_set_id": s["id"],
                "start": et_date(s["start_date"]),
                "end": et_date(s["end_date"]),
                "final": final,
                "players": len(payload["players"]),
                "qualified": qualified,
                "built_at": iso_utc(built),
                "file": write_season(out_dir, slug, payload),
                "definitions_sha256": fingerprint,
            }
            # Save after every season, so a long first build that dies midway
            # keeps what it finished.
            manifest["seasons"] = entries(current)
            manifest["updated_at"] = iso_utc(built)
            save_manifest(out_dir, manifest)
            print(f"        {len(payload['players'])} players, {qualified} qualified, "
                  f"in {built - t0:.0f}s" + ("  -> final" if final else ""), flush=True)

        alert = season_gap_alert(conn, discovered, now)

    manifest["seasons"] = entries(current)
    manifest["checked_at"] = iso_utc(time.time())
    if args.scheduled:
        manifest["last_scheduled_run_et"] = dt.datetime.fromtimestamp(now, ET).date().isoformat()
    save_manifest(out_dir, manifest)
    print(f"built {len(todo)} season(s); manifest at {out_dir / 'manifest.json'}")
    emit(ran="true", built=len(todo), alert=alert)


if __name__ == "__main__":
    main()
