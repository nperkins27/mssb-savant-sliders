#!/usr/bin/env python3
"""Build the MSSB Savant Sliders site data: one file per season plus a manifest.

Run it any time -- it only does the work that is still due.

  * Seasons are discovered from tag_set, never hardcoded: main-line Superstars
    Off names ("S15 Superstars Off", "Stars Off, Season 7", "Interim Superstars
    Off") that also carry the Disable Superstars gecko code, from Season 7 on.
  * A season that has started and is not final gets rebuilt. It becomes final
    on the first build that runs more than GRACE_DAYS after its end_date, and
    is never queried again after that.
  * Every season records the SHA-256 of the SQL that built it. Editing the SQL
    makes every season stale, so a metric change rebuilds the history once,
    automatically.

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
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ET = ZoneInfo("America/New_York")

FIRST_SEASON = "starsoffseason7"   # name_lowercase of the oldest season on the site
DISABLE_SUPERSTARS_TAG = 10        # tag.id of the gecko code every stars-off season carries
GRACE_DAYS = 2                     # games finishing after midnight, late uploads
ALERT_GAP_DAYS = 21                # no recognised season for this long -> alert
DAILY_AT_ET = dt.time(4, 0)

# tag_set.name_lowercase has every non-alphanumeric stripped ("S15 Superstars
# Off" -> "s15superstarsoff"). Anchored at both ends so that "...Hazards",
# "Netplay Superstars 16" and "SLICE 2026 Superstars Off" never match.
SEASON_NAME_PATTERN = (
    r"^(s[0-9]+superstarsoff|starsoffseason[0-9]+|interim[a-z0-9]*superstarsoff)$"
)

DISCOVER_SQL = """
select ts.id, ts.name, ts.name_lowercase, ts.start_date, ts.end_date,
       lower(ts.name)                                  as tag_filter,
       to_char(to_timestamp(ts.start_date), 'YYYY-MM-DD') as query_start,
       to_char(to_timestamp(ts.end_date), 'YYYY-MM-DD')   as query_end
from tag_set ts
where ts.name_lowercase ~ %(pattern)s
  and exists (select 1 from tag_set_tag tst
              where tst.tagset_id = ts.id and tst.tag_id = %(tag)s)
  and ts.start_date >= (select start_date from tag_set
                        where name_lowercase = %(first)s)
order by ts.start_date
"""

# Stars-off tag sets that look like a season but don't match the pattern --
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
  and ts.name_lowercase !~ %(pattern)s
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
# query
# --------------------------------------------------------------------------

def sql_fingerprint(template: str) -> str:
    # Normalise line endings: a Windows checkout (CRLF) and the Linux runner
    # (LF) must agree, or every season would look stale on the first CI run.
    return hashlib.sha256(template.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def render_query(template: str, start: str, end: str, tag: str) -> str:
    tag_literal = tag.replace("'", "''")
    replacements = {
        "'2023-06-01'": f"'{start}'",
        "'2023-12-31'": f"'{end}'",
        "('stars off, season 7')": f"('{tag_literal}')",
    }
    sql = template
    for old, new in replacements.items():
        if sql.count(old) != 1:
            raise SystemExit(
                f"ERROR: expected exactly 1 occurrence of {old} in the SQL file "
                f"(found {sql.count(old)}). The query has drifted from what this "
                "script expects -- aborting instead of guessing."
            )
        sql = sql.replace(old, new)
    # Only SELECT-family statements: never let a write slip through.
    for line in sql.splitlines():
        s = line.strip().lower()
        if s.startswith(("insert ", "update ", "delete ", "drop ", "alter ",
                         "create ", "truncate ", "grant ", "revoke ")):
            raise SystemExit(f"ERROR: refusing to run non-read statement: {line.strip()[:80]}")
    return sql


def run_query(conn, sql: str):
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [[float(v) if isinstance(v, Decimal) else v for v in r]
                for r in cur.fetchall()]
    return cols, rows


def discover(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(DISCOVER_SQL, {"pattern": SEASON_NAME_PATTERN,
                                   "tag": DISABLE_SUPERSTARS_TAG,
                                   "first": FIRST_SEASON})
        names = [d[0] for d in cur.description]
        seasons = [dict(zip(names, r)) for r in cur.fetchall()]
    if not seasons:
        raise SystemExit(
            f"ERROR: no seasons discovered (is '{FIRST_SEASON}' still a tag set?)"
        )
    return seasons


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


def write_season(out_dir: Path, slug: str, cols, rows) -> str:
    rel = f"seasons/{slug}.js"
    payload = json.dumps({"columns": cols, "rows": rows}, separators=(",", ":"))
    atomic_write(out_dir / rel,
                 "/* Generated by build_seasons.py -- do not edit by hand. */\n"
                 f"(window.MSSB_SEASONS = window.MSSB_SEASONS || {{}})[{json.dumps(slug)}] = "
                 + payload + ";\n")
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


def plan_season(s: dict, prev: dict | None, sql_hash: str, now: float,
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
    if prev.get("sql_sha256") != sql_hash:
        return "build", "SQL changed"
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
    print("Stars-off Season/League tag sets created since then that did NOT match:")
    with conn.cursor() as cur:
        cur.execute(CANDIDATES_SQL, {"tag": DISABLE_SUPERSTARS_TAG,
                                     "since": latest_end - 7 * 86400,
                                     "pattern": SEASON_NAME_PATTERN})
        found = cur.fetchall()
    for name, typ, starts, recent in found:
        print(f"  {name!r:40} {typ:8} starts {starts}  games in last 14 days: {recent}")
    if not found:
        print("  (none)")
    return (f"No Superstars Off season recognised since {et_date(latest_end)}. "
            "If a new season started under a different name, update "
            "SEASON_NAME_PATTERN in build_seasons.py (candidates are in the build log).")


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sql", default=str(HERE / "mssb_savant_sliders.sql"))
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

    template = Path(args.sql).read_text(encoding="utf-8")
    sql_hash = sql_fingerprint(template)
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
                action, reason = plan_season(s, prev_by_slug.get(slug), sql_hash, now,
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

        current = {slug: e for slug, e in prev_by_slug.items()}
        todo = [s for s, action in plan if action == "build"]
        for n, s in enumerate(todo, 1):
            slug = s["name_lowercase"]
            print(f"[{n}/{len(todo)}] {s['name']}  "
                  f"({s['query_start']} .. {s['query_end']})  running...", flush=True)
            t0 = time.time()
            sql = render_query(template, s["query_start"], s["query_end"], s["tag_filter"])
            cols, rows = run_query(conn, sql)
            built = time.time()
            final = built > s["end_date"] + GRACE_DAYS * 86400
            current[slug] = {
                "slug": slug,
                "name": s["name"],
                "tag_set_id": s["id"],
                "start": et_date(s["start_date"]),
                "end": et_date(s["end_date"]),
                "final": final,
                "users": len(rows),
                "built_at": iso_utc(built),
                "file": write_season(out_dir, slug, cols, rows),
                "sql_sha256": sql_hash,
            }
            # Save after every season, so a long first build that dies midway
            # keeps what it finished.
            manifest["seasons"] = entries(current)
            manifest["updated_at"] = iso_utc(built)
            save_manifest(out_dir, manifest)
            print(f"        {len(rows)} users in {built - t0:.0f}s"
                  + ("  -> final" if final else ""), flush=True)

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
