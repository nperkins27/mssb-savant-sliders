"""Character Frame Results: what happens when a character makes contact on each
frame of the swing, pooled across every Stars Off season and tournament the
site covers (the same tag sets build_seasons.py discovers).

Only counts are stored. Every slap, charge and star swing contact is reduced to
one cell -- batter character, batting hand, contact type, swing type, frame,
stick input, result, stadium and chemistry links on base -- and the page sums
the cells that match its filters, so every combination of filters is exact.

Refreshed on the same model as the season data, so a finished season or
tournament is queried once and never again:
  * data/frames/final/ pools every finished tag set. A tag set joins the pool
    on the first run after it becomes final, by adding its counts to the pool
    already on disk.
  * data/frames/live/ pools the tag sets still in progress, rebuilt every run.
  * Editing this file changes its fingerprint, which rebuilds the final pool
    from the database once.
"""
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent

# Bump when the shape of what is written under data/frames changes.
FRAMES_FORMAT = 1

HANDS = ("Righty", "Lefty")                               # character_game_summary.batting_hand false / true
CONTACTS = ("Sour left", "Nice left", "Perfect", "Nice right", "Sour right")   # type_of_contact 0-4
SWINGS = ("Slap", "Charge", "Star")                       # type_of_swing 1-3 (0 is no swing: bunts)
FRAMES = tuple(range(2, 11))                              # frame_of_swing_upon_contact
STADIUMS = ("Mario Stadium", "Bowser's Castle", "Wario's Palace", "Yoshi's Island",
            "Peach's Garden", "DK's Jungle")              # stadium_id 0-5 (6, Toy Field, isn't baseball)
CHEM = ("0", "1", "2", "3")                               # event.chem_links_ob


def stick_label(mask: int) -> str:
    """input_direction_stick is a bitmask: 1 left, 2 right, 4 down, 8 up."""
    parts = [name for bit, name in ((8, "up"), (4, "down"), (1, "left"), (2, "right")) if mask & bit]
    if not parts:
        return "none"
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


STICKS = tuple(stick_label(m) for m in range(16))
# Menu order: the common inputs first, the rare multi-direction masks last.
STICK_ORDER = (0, 1, 2, 4, 5, 6, 8, 9, 10, 3, 7, 11, 12, 13, 14, 15)

OUTCOMES = ("foul", "homerun", "on_base", "out")
# Result labels (the page's Result filter) and the outcome each counts toward.
# Labels follow Rio-Sabermetrics' FrameData.pgsql, plus foul catch and
# fielder's choice, which that query folds into out or leaves blank.
RESULTS = (
    ("single", "on_base"),
    ("double", "on_base"),
    ("triple", "on_base"),
    ("homerun", "homerun"),
    ("induced error", "on_base"),
    ("foul", "foul"),
    ("out", "out"),
    ("foul catch", "out"),
    ("double play", "out"),
    ("fielder's choice", "out"),
    ("bunt", "out"),
)
_RESULT = {label: i for i, (label, _) in enumerate(RESULTS)}

# One cell key is these dimensions as a mixed-radix number, first most significant.
DIMS = (
    ("hand", HANDS),
    ("contact", CONTACTS),
    ("swing", SWINGS),
    ("frame", FRAMES),
    ("stick", STICKS),
    ("result", tuple(label for label, _ in RESULTS)),
    ("stadium", STADIUMS),
    ("chem", CHEM),
)


def result_code(result_of_ab: int, fielders_choice: bool) -> int | None:
    """Classified by what the at-bat did, not by contact_summary.secondary_result
    alone, which calls some fouls outs and some force outs fouls:
      * result_of_ab 0 -- the at-bat went on after contact, so it was a foul
        (same batter, a strike added below two, no outs or runs).
      * secondary_result 4 is a fielder's choice: result_of_ab 4 (out), but the
        batter reaches base while a runner is put out."""
    if result_of_ab == 0:
        return _RESULT["foul"]
    if result_of_ab == 4 and fielders_choice:
        return _RESULT["fielder's choice"]
    return {
        1: _RESULT["out"], 4: _RESULT["out"], 5: _RESULT["out"], 6: _RESULT["out"], 14: _RESULT["out"],
        7: _RESULT["single"], 8: _RESULT["double"], 9: _RESULT["triple"], 10: _RESULT["homerun"],
        11: _RESULT["induced error"], 12: _RESULT["induced error"],
        13: _RESULT["bunt"], 15: _RESULT["double play"], 16: _RESULT["foul catch"],
    }.get(result_of_ab)


CELLS_SQL = """
WITH sg AS (
    SELECT DISTINCT gh.game_id
    FROM game_history gh
    WHERE gh.tag_set_id = ANY(%(ids)s)
      AND gh.game_id IS NOT NULL
)
SELECT bcgs.char_id,
       bcgs.batting_hand,
       cs.type_of_contact,
       ps.type_of_swing,
       cs.frame_of_swing_upon_contact,
       cs.input_direction_stick,
       e.result_of_ab,
       cs.secondary_result = 4 AS fielders_choice,
       g.stadium_id,
       e.chem_links_ob,
       COUNT(*)
FROM sg
JOIN game g ON g.game_id = sg.game_id
JOIN event e ON e.game_id = sg.game_id
JOIN pitch_summary ps ON ps.id = e.pitch_summary_id
JOIN contact_summary cs ON cs.id = ps.contact_summary_id
JOIN character_game_summary bcgs ON bcgs.id = e.batter_id
WHERE ps.type_of_swing IN (1, 2, 3)
  -- Aborted uploads record 0 innings and a zeroed roster, which reads as all
  -- Mario (S7 has 10 such games with contacts).
  AND g.innings_played > 0
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
"""


def collect(conn, ids: list[int]) -> dict[int, Counter]:
    """{char_id: Counter(cell key -> contacts)} for these tag sets, one query."""
    pool: dict[int, Counter] = {}
    skipped: Counter = Counter()
    with conn.cursor() as cur:
        cur.execute(CELLS_SQL, {"ids": ids})
        for char_id, lefty, contact, swing, frame, stick, ab, fc, stadium, chem, n in cur.fetchall():
            result = result_code(ab, bool(fc))
            coords = (
                None if lefty is None else int(lefty),
                contact if contact in range(len(CONTACTS)) else None,
                swing - 1,
                frame - FRAMES[0] if frame in FRAMES else None,
                stick if stick in range(len(STICKS)) else None,
                result,
                stadium if stadium in range(len(STADIUMS)) else None,
                chem if chem in range(len(CHEM)) else None,
            )
            missing = [name for (name, _), c in zip(DIMS, coords) if c is None]
            if char_id is None or missing:
                skipped[", ".join(missing) or "character"] += n
                continue
            key = 0
            for (_, labels), c in zip(DIMS, coords):
                key = key * len(labels) + c
            pool.setdefault(char_id, Counter())[key] += n
    if skipped:
        print("        frame results skipped (value outside the known range): "
              + "; ".join(f"{why}: {n}" for why, n in skipped.most_common()))
    return pool


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------

def definitions_fingerprint() -> str:
    h = hashlib.sha256(f"frames format {FRAMES_FORMAT}\n".encode("utf-8"))
    h.update((HERE / "frame_results.py").read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8"))
    return h.hexdigest()


def generation(fingerprint: str, final_ids: list[int]) -> str:
    """Names one version of the final pool. Live files record the generation
    they were built against, so the page can tell a stale mix from a real one."""
    return hashlib.sha256(f"{fingerprint} {sorted(final_ids)}".encode("utf-8")).hexdigest()[:16]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _cells_text(kind: str, char_id: int, cells: Counter, gen: str) -> str:
    """Keys sorted and delta-encoded, so most are a few digits."""
    keys = sorted(cells)
    deltas = [b - a for a, b in zip([0] + keys, keys)]
    payload = {"gen": gen, "k": deltas, "n": [cells[k] for k in keys]}
    return ("/* Generated by build_seasons.py -- do not edit by hand. */\n"
            f"(window.MSSB_FRAME_CELLS = window.MSSB_FRAME_CELLS || {{}})[{json.dumps(f'{kind}/{char_id}')}] = "
            + json.dumps(payload, separators=(",", ":")) + ";\n")


def _read_cells(path: Path) -> dict | None:
    if not path.is_file():
        return None
    m = re.search(r"\] = (\{.*\});\s*$", path.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1)) if m else None


def _write_pool(folder: Path, kind: str, pool: dict[int, Counter], gen: str) -> None:
    for char_id, cells in pool.items():
        _write(folder / f"c{char_id}.js", _cells_text(kind, char_id, cells, gen))
    for stale in folder.glob("c*.js"):
        if stale.stem[1:].isdigit() and int(stale.stem[1:]) not in pool:
            stale.unlink()


def read_final_pool(out_dir: Path, index: dict) -> dict[int, Counter] | None:
    """The final pool on disk, or None if any file is missing, from another
    generation, or doesn't hold the count the index recorded (an interrupted
    run) -- in which case the pool is rebuilt rather than trusted."""
    gen = (index.get("final") or {}).get("gen")
    pool = {}
    for char_id, _name, final_contacts, _live in index.get("characters", []):
        if not final_contacts:
            continue
        d = _read_cells(out_dir / "final" / f"c{char_id}.js")
        if not d or d.get("gen") != gen or sum(d["n"]) != final_contacts:
            return None
        keys, k = [], 0
        for delta in d["k"]:
            k += delta
            keys.append(k)
        pool[char_id] = Counter(dict(zip(keys, d["n"])))
    return pool


def load_index(out_dir: Path) -> dict:
    path = out_dir / "index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------

def refresh(conn, discovered: list[dict], now: float, grace_seconds: int, out_dir: Path,
            dry_run: bool = False) -> None:
    """Bring data/frames up to date. discovered: build_seasons.discover() output."""
    fingerprint = definitions_fingerprint()
    index = load_index(out_dir)
    started = [s for s in discovered if s["start_date"] <= now]
    names = {s["id"]: s["name"] for s in discovered}

    # pool: the finished tag sets already counted, or None to rebuild it all.
    if index.get("definitions_sha256") != fingerprint:
        pool, plan = None, "rebuild, definitions changed" if index else "first build"
    elif dry_run:
        pool, plan = {}, "kept"      # the plan trusts the index; files are checked on a real run
    else:
        pool = read_final_pool(out_dir, index)
        plan = "kept" if pool is not None else "rebuild, final files incomplete"
    pooled = set((index.get("final") or {}).get("tag_set_ids", [])) if pool is not None else set()
    finished = {s["id"] for s in started if now > s["end_date"] + grace_seconds}
    new_final = sorted(finished - pooled)
    # A tag set already pooled stays final, even if its end date later moves.
    live_ids = sorted(s["id"] for s in started if s["id"] not in finished and s["id"] not in pooled)

    if pool is not None and new_final:
        plan += ", adding " + ", ".join(names.get(i, str(i)) for i in new_final)
    print(f"  frame results: final pool {plan}; in progress: "
          + (", ".join(names[i] for i in live_ids) or "none"))
    if dry_run:
        return

    final_changed = pool is None or bool(new_final)
    pool = pool if pool is not None else {}
    if new_final:
        print(f"  frame results: querying {len(new_final)} finished tag set(s)...", flush=True)
        for char_id, cells in collect(conn, new_final).items():
            pool.setdefault(char_id, Counter()).update(cells)
    final_ids = sorted(pooled | set(new_final))
    gen = generation(fingerprint, final_ids)

    live = {}
    if live_ids:
        print(f"  frame results: querying {len(live_ids)} tag set(s) in progress...", flush=True)
        live = collect(conn, live_ids)

    # Final files first, index last: an interrupted run leaves files whose
    # generation the old index doesn't name, which forces a clean rebuild.
    if final_changed:
        _write_pool(out_dir / "final", "final", pool, gen)
    _write_pool(out_dir / "live", "live", live, gen)

    with conn.cursor() as cur:
        cur.execute("SELECT char_id, name FROM character")
        char_names = dict(cur.fetchall())
    built = now
    characters = sorted(([cid, char_names.get(cid, f"Character {cid}"),
                          sum(pool.get(cid, {}).values()), sum(live.get(cid, {}).values())]
                         for cid in set(pool) | set(live)), key=lambda c: c[1].lower())
    prev_final = index.get("final") or {}
    index = {
        "format": FRAMES_FORMAT,
        "definitions_sha256": fingerprint,
        "dims": [[name, list(labels)] for name, labels in DIMS],
        "stick_order": list(STICK_ORDER),
        "outcomes": list(OUTCOMES),
        "result_outcome": [OUTCOMES.index(outcome) for _, outcome in RESULTS],
        "characters": characters,
        "final": {"gen": gen, "tag_set_ids": final_ids, "contacts": sum(c[2] for c in characters),
                  "built_at": _iso(built) if final_changed else prev_final.get("built_at", _iso(built))},
        "live": {"tag_set_ids": live_ids, "contacts": sum(c[3] for c in characters), "built_at": _iso(built)},
    }
    body = json.dumps(index, indent=1)
    _write(out_dir / "index.json", body + "\n")
    _write(out_dir / "index.js", "/* Generated by build_seasons.py -- do not edit by hand. */\n"
                                 "window.MSSB_FRAMES = " + body + ";\n")
    print(f"  frame results: {index['final']['contacts']:,} finished + {index['live']['contacts']:,} "
          f"in-progress contacts, {len(characters)} characters")
