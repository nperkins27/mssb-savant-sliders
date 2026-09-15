/* Shared by profile.html (one player) and players.html (all players combined).
   The page says which with <body data-mode="player"> or data-mode="all".
   Load data/manifest.js, data/games/index.js and shared.js first. */
"use strict";
const MODE = document.body.dataset.mode === "all" ? "all" : "player";
const {esc, fmt, METRICS} = MSSB;
const GI = window.MSSB_GAMES_INDEX;
const F = GI ? Object.fromEntries(GI.fields.map((f, i)=>[f, i])) : {};
const SETS = GI ? GI.sets : [];
const setBySlug = new Map(SETS.map((s, i)=>[s.slug, Object.assign({idx: i}, s)]));
const playerById = new Map((GI ? GI.players : []).map(p=>[p[0], p]));
const CHAR = GI ? new Map(GI.characters) : new Map();
const CODE = GI ? new Map([...GI.roster_alphabet].map((c, i)=>[c, i])) : new Map();
const R9 = METRICS.find(m=>m.k === "gen_runs_per_9"), RA9 = METRICS.find(m=>m.k === "gen_runs_against_per_9");
const ELO = METRICS.find(m=>m.k === "gen_adjusted_elo");
const STEPS = 7;

const dayYear = d=>new Date(d * 864e5).getUTCFullYear();
const dayLabel = d=>new Date(d * 864e5).toLocaleDateString([], {timeZone: "UTC", dateStyle: "medium"});
const pct = (a, b)=>b ? (100 * a / b).toFixed(1) + "%" : "—";
const plural = (n, word)=>`${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
const ordinal = n=>{ const s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
const roster = s=>[...(s || "")].map(c=>CODE.get(c));

/* The view: "all", "y2025", or a season/tournament slug. uid is null on the All players page. */
const state = {uid: null, view: "all", side: true, pick: true, charpick: true, sort: "all"};

/* ---- the address bar keeps the page: #u=<user id>&v=<view> (just #v= for all players) ---- */
function readHash(){
  const u = location.hash.match(/[#&]u=(\d+)/), v = location.hash.match(/[#&]v=([^&]+)/);
  return {uid: u ? +u[1] : null, view: v ? decodeURIComponent(v[1]) : null};
}
function writeHash(){
  history.replaceState(null, "", (MODE === "all" ? "#" : `#u=${state.uid}&`) + `v=${encodeURIComponent(state.view)}`);
}

/* ---- data ---- */
const loadingGames = {};
function loadGames(slug){
  const s = setBySlug.get(slug), file = "data/games/" + s.file;
  if(!loadingGames[slug]) loadingGames[slug] = new Promise((resolve, reject)=>{
    const tag = document.createElement("script");
    tag.src = file + (location.protocol === "file:" ? "" : "?v=" + encodeURIComponent(s.built_at));
    tag.onload = ()=>{
      const d = (window.MSSB_GAMES || {})[slug];
      d ? resolve(d) : reject(new Error(`${file} loaded but held no games. Re-run build_seasons.py.`));
    };
    tag.onerror = ()=>{ delete loadingGames[slug]; reject(new Error(`Could not load ${file}.`)); };
    document.head.appendChild(tag);
  });
  return loadingGames[slug];
}

/* The seasons and tournaments the view covers: the player's, or everyone's. */
function setsInView(player, view){
  const played = player ? SETS.filter((s, i)=>player[2][i]) : SETS;
  if(view === "all") return played;
  if(view[0] === "y"){
    const y = +view.slice(1);
    return played.filter(s=>dayYear(s.first_day) <= y && dayYear(s.last_day) >= y);
  }
  return played.filter(s=>s.slug === view);
}

/* Add up games from one side's point of view: record, runs, stadium records
   and character picks. With a player, that's their side of each of their
   games; with uid null, both sides of every game, so every game counts once
   for each team. */
function summarize(uid, loaded, year){
  const rec = ()=>({w: 0, l: 0, t: 0});
  const stad = GI.stadiums.map(()=>({all: {all: rec(), 1: rec(), 2: rec()},
                                     home: {all: rec(), 1: rec(), 2: rec()},
                                     away: {all: rec(), 1: rec(), 2: rec()}}));
  const bucket = ()=>({games: 0, chars: new Map()});
  const picks = {all: bucket(), stad: GI.stadiums.map(()=>({all: bucket(), 1: bucket(), 2: bucket()}))};
  const S = {games: 0, matches: 0, w: 0, l: 0, t: 0, rs: 0, ob: 0, ra: 0, of: 0, stad, picks, players: new Set(),
             seasons: new Set(), tournaments: new Set(), first: null, last: null};
  const addPick = (b, chars)=>{ b.games++; chars.forEach(c=>b.chars.set(c, (b.chars.get(c) || 0) + 1)); };
  for(const [slug, d] of loaded){
    const kind = setBySlug.get(slug).kind;
    for(const g of d.games){
      if(year != null && dayYear(g[F.day]) !== year) continue;
      const sides = uid == null ? ["away", "home"]
        : g[F.home] === uid ? ["home"] : g[F.away] === uid ? ["away"] : [];
      if(!sides.length) continue;
      S.matches++;
      S.players.add(g[F.away]).add(g[F.home]);
      for(const me of sides){
        const them = me === "home" ? "away" : "home";
        const mine = roster(g[F[me + "_roster"]]), theirs = roster(g[F[them + "_roster"]]);
        const st = g[F.stadium];
        const pick = st === GI.peachs_garden ? null
          : mine.includes(GI.bowser) ? 1 : theirs.includes(GI.bowser) ? 2 : null;
        const diff = g[F[me + "_score"]] - g[F[them + "_score"]];
        const res = diff > 0 ? "w" : diff < 0 ? "l" : "t";
        S.games++; S[res]++;
        S.rs += g[F[them + "_runs_allowed"]]; S.ob += g[F[them + "_outs"]];
        S.ra += g[F[me + "_runs_allowed"]]; S.of += g[F[me + "_outs"]];
        for(const side of ["all", me]) for(const pk of ["all", pick]) if(pk != null) stad[st][side][pk][res]++;
        const chars = new Set(mine);
        addPick(picks.all, chars);
        addPick(picks.stad[st].all, chars);
        if(pick) addPick(picks.stad[st][pick], chars);
      }
      (kind === "tournament" ? S.tournaments : S.seasons).add(slug);
      S.first = S.first == null ? g[F.day] : Math.min(S.first, g[F.day]);
      S.last = S.last == null ? g[F.day] : Math.max(S.last, g[F.day]);
    }
  }
  return S;
}

/* ---- page ---- */
let seq = 0;

function init(){
  if(!GI){
    document.getElementById("warn").innerHTML = `<div class="warn">No player data found. Run
      <code>python build_seasons.py</code> to generate <code>site/data/games/</code>.</div>`;
    return;
  }
  document.getElementById("view").onchange = e=>{ state.view = e.target.value; render(); };
  document.querySelectorAll(".switch[data-split]").forEach(btn=>{
    btn.onclick = ()=>{
      const key = btn.dataset.split;
      state[key] = !state[key];
      btn.setAttribute("aria-checked", String(state[key]));
      drawTables();
    };
  });
  const want = readHash();

  if(MODE === "all"){
    fillViewMenu(null);
    if(want.view && [...document.getElementById("view").options].some(o=>o.value === want.view)) state.view = want.view;
    document.getElementById("view").value = state.view;
    render();
    return;
  }

  document.getElementById("player-list").innerHTML =
    GI.players.map(p=>`<option value="${esc(p[1])}"></option>`).join("");
  const input = document.getElementById("player");
  const choose = ()=>{
    const text = input.value.trim().toLowerCase();
    if(!text) return;
    const exact = GI.players.find(p=>p[1].toLowerCase() === text);
    const starts = GI.players.filter(p=>p[1].toLowerCase().startsWith(text));
    const p = exact || (starts.length === 1 ? starts[0] : null);
    if(p){ input.value = p[1]; selectPlayer(p[0]); }
    else document.getElementById("warn").innerHTML =
      `<div class="warn">${starts.length ? `${starts.length} players start with &ldquo;${esc(input.value)}&rdquo;; pick one from the list.`
                                         : `No Stars Off player named &ldquo;${esc(input.value)}&rdquo;.`}</div>`;
  };
  input.addEventListener("change", choose);
  input.addEventListener("keydown", e=>{ if(e.key === "Enter") choose(); });

  if(want.uid != null && playerById.has(want.uid)){
    if(want.view) state.view = want.view;
    selectPlayer(want.uid);
    return;
  }
  /* No player in the address: the leaderboard's top player in the newest
     season -- unless the visitor picks someone before that file arrives. */
  MSSB.loadSeason(MSSB.latestSeason().slug).then(season=>{
    if(state.uid != null) return;
    const top = season.board(ELO)[0] || season.board(METRICS.find(m=>m.k === "gen_games_played"))[0];
    selectPlayer(top && playerById.has(top.id) ? top.id : GI.players[0][0]);
  }, ()=>{ if(state.uid == null) selectPlayer(GI.players[0][0]); });
}

/* The view menu: all time, years, seasons, then tournaments by series, with
   game counts -- the player's own, or every game on the All players page. */
function fillViewMenu(player){
  const option = (value, label, n)=>`<option value="${esc(value)}">${esc(label)} (${plural(n, "game")})</option>`;
  const years = Object.entries(player ? player[3] : GI.years).sort((a, b)=>b[0] - a[0]);
  const played = SETS.map((s, i)=>[s, player ? player[2][i] : s.games]).filter(([, n])=>n).reverse();   /* newest first */
  const total = played.reduce((t, [, n])=>t + n, 0);
  const seasons = played.filter(([s])=>s.kind === "season");
  const groups = MSSB.TOURNAMENT_SERIES.map(([key, , heading])=>
    [heading, played.filter(([s])=>s.kind === "tournament" && s.series === key)]).filter(([, list])=>list.length);
  document.getElementById("view").innerHTML = option("all", "All time", total) +
    `<optgroup label="Years">${years.map(([y, n])=>option("y" + y, y, n)).join("")}</optgroup>` +
    (seasons.length ? `<optgroup label="Stars Off seasons">${seasons.map(([s, n])=>option(s.slug, s.name, n)).join("")}</optgroup>` : "") +
    groups.map(([heading, list])=>`<optgroup label="${esc(heading)}">${list.map(([s, n])=>option(s.slug, s.name, n)).join("")}</optgroup>`).join("");
}

function selectPlayer(uid){
  const player = playerById.get(uid);
  state.uid = uid;
  document.getElementById("player").value = player[1];
  document.getElementById("warn").innerHTML = "";
  fillViewMenu(player);   /* only what this player played */
  const select = document.getElementById("view");
  state.view = [...select.options].some(o=>o.value === state.view) ? state.view : "all";
  select.value = state.view;
  render();
}

let current = null;   /* what's on screen: {player, S, view, sets, single, year} */
function render(){
  const mine = ++seq, player = MODE === "all" ? null : playerById.get(state.uid), view = state.view;
  const sets = setsInView(player, view);
  const profile = document.getElementById("profile");
  const slow = setTimeout(()=>profile.classList.add("loading"), 150);
  writeHash();
  const single = view !== "all" && view[0] !== "y" ? setBySlug.get(view) : null;
  Promise.all([Promise.all(sets.map(s=>loadGames(s.slug).then(d=>[s.slug, d]))),
               single && player ? MSSB.loadSeason(single.slug).catch(()=>null) : null]).then(([loaded, season])=>{
    clearTimeout(slow);
    if(mine !== seq) return;
    profile.classList.remove("loading");
    profile.hidden = false;
    const year = view[0] === "y" ? +view.slice(1) : null;
    const S = summarize(player ? state.uid : null, loaded, year);
    current = {player, S, view, sets, single, year};
    drawHeader(season);
    drawTables();
    drawTrophies();
  }, err=>{
    clearTimeout(slow);
    if(mine !== seq) return;
    profile.classList.remove("loading");
    document.getElementById("warn").innerHTML = `<div class="warn">${esc(err.message)}</div>`;
  });
}

const tile = (label, value, sub)=>`<div class="tile"><div class="l">${label}</div><div class="v">${value}</div>` +
  `<div class="s">${sub}</div></div>`;

function drawHeader(season){
  const {player, S, single, year} = current;
  document.getElementById("p-name").textContent = player ? player[1] : "All players";
  const scope = single ? single.name + (single.final ? "" : " (in progress)")
    : year != null ? String(year) : "All time";
  const parts = [S.seasons.size && plural(S.seasons.size, "season"),
                 S.tournaments.size && plural(S.tournaments.size, "tournament")].filter(Boolean);
  const setsLine = single || !parts.length ? "" : " in " + parts.join(" and ");
  document.getElementById("p-meta").innerHTML = `<b>${esc(scope)}</b> &middot; ${plural(S.matches, "game")}${esc(setsLine)}` +
    (S.first != null ? ` &middot; ${esc(dayLabel(S.first))} to ${esc(dayLabel(S.last))}` : "");

  /* "6,309 in 3,943.1 inn": outs as innings, with thousands separators for big totals. */
  const inn = outs=>Math.floor(outs / 3).toLocaleString() + (outs % 3 ? "." + outs % 3 : "");
  const runs = (m, num, den)=>tile(m.label, den ? fmt(m, 27 * num / den) : "—",
    `<span title="${esc(`${num.toLocaleString()} ${m.n} in ${inn(den)} innings (${den.toLocaleString()} outs)`)}">` +
    `${num.toLocaleString()} in ${inn(den)} inn</span>`);
  if(!player){
    /* Every game has a winner and a loser, so wins and losses are even; show
       what the combined games do say. */
    const total = (side, pk)=>S.stad.reduce((t, st)=>({w: t.w + st[side][pk].w, l: t.l + st[side][pk].l}), {w: 0, l: 0});
    const home = total("home", "all"), first = total("all", 1);
    document.getElementById("tiles").innerHTML =
      tile("Games", S.matches.toLocaleString(), S.t ? `${plural(S.t / 2, "tied game")}` : "&nbsp;") +
      tile("Players", S.players.size.toLocaleString(),
           S.players.size ? `${(S.games / S.players.size).toFixed(1)} games each on average` : "") +
      runs(R9, S.rs, S.ob) +
      tile("Home win %", pct(home.w, home.w + home.l), `${home.w.toLocaleString()}&ndash;${home.l.toLocaleString()} for the home team`) +
      tile("1st pick win %", pct(first.w, first.w + first.l),
           `${first.w.toLocaleString()}&ndash;${first.l.toLocaleString()}, outside Peach&rsquo;s Garden`);
    return;
  }
  let elo = "";
  if(single){
    const p = season && season.byId.get(state.uid), c = p && season.cell(p, ELO);
    const sub = !c ? "not available" : c.ok
      ? `${ordinal(Math.round(c.pct))} percentile of ${c.pool}`
      : esc(MSSB.whyNot(ELO, c, season.games(p), season.entry));
    elo = tile("ELO", c ? fmt(ELO, c.value) : "—", sub);
  }
  const decided = S.w + S.l;
  document.getElementById("tiles").innerHTML = elo +
    tile("Wins", S.w.toLocaleString(), decided ? `${pct(S.w, decided)} win rate` : "no decided games") +
    tile("Losses", S.l.toLocaleString(), S.t ? `plus ${plural(S.t, "tied game")}` : plural(S.games, "game")) +
    runs(R9, S.rs, S.ob) + runs(RA9, S.ra, S.of);
}

function drawTables(){
  if(!current) return;
  drawStadiums();
  drawPicks();
}

/* ---- stadium record ---- */
function drawStadiums(){
  const {S} = current, peach = GI.peachs_garden;
  const groups = state.side ? [["all", "All games"], ["home", "Home"], ["away", "Away"]] : [["all", null]];
  const subs = state.pick ? [["all", "Overall"], [1, "1st pick"], [2, "2nd pick"]] : [["all", "Overall"]];
  const cell = (r, na)=>{
    if(na) return `<td class="na" title="No reliable draft data at Peach&rsquo;s Garden">n/a</td>`;
    const n = r.w + r.l;
    if(!n && !r.t) return `<td class="na">—</td>`;
    return `<td title="${r.w} won, ${r.l} lost${r.t ? `, ${r.t} tied` : ""}"><span class="p">${pct(r.w, n)}</span>` +
           `<span class="r">${r.w.toLocaleString()}&ndash;${r.l.toLocaleString()}${r.t ? `&ndash;${r.t}` : ""}</span></td>`;
  };
  const sum = (side, pk)=>S.stad.reduce((t, st)=>{ const r = st[side][pk]; return {w: t.w + r.w, l: t.l + r.l, t: t.t + r.t}; },
                                        {w: 0, l: 0, t: 0});
  let head;
  if(state.side && state.pick){
    head = `<tr><th rowspan="2"></th>${groups.map(([, g])=>`<th class="group" colspan="${subs.length}">${g}</th>`).join("")}</tr>` +
           `<tr>${groups.map(()=>subs.map(([, s])=>`<th>${s}</th>`).join("")).join("")}</tr>`;
  } else {
    const labels = state.side ? groups.map(([, g])=>g) : subs.map(([, s])=>s);
    head = `<tr><th></th>${labels.map(l=>`<th>${l}</th>`).join("")}</tr>`;
  }
  const row = (label, get, isPeach, cls = "")=>`<tr${cls ? ` class="${cls}"` : ""}><th scope="row">${label}</th>` +
    groups.map(([side])=>subs.map(([pk])=>cell(get(side, pk), isPeach && pk !== "all")).join("")).join("") + `</tr>`;
  document.getElementById("stadiums").innerHTML = `<thead>${head}</thead><tbody>` +
    GI.stadiums.map((name, i)=>row(esc(name), (side, pk)=>S.stad[i][side][pk], i === peach)).join("") +
    row("All stadiums", sum, false, "total") + `</tbody>`;
}

/* ---- character picks ---- */
function drawPicks(){
  const {S} = current, peach = GI.peachs_garden;
  const unit = MODE === "all" ? "teams" : "g";
  /* Columns: all games, then each stadium, split by pick where the draft is known. */
  const cols = [{key: "all", group: null, label: "All games", b: S.picks.all}];
  GI.stadiums.forEach((name, i)=>{
    if(state.charpick && i !== peach){
      cols.push({key: `s${i}p1`, group: name, label: "1st", b: S.picks.stad[i][1]},
                {key: `s${i}p2`, group: name, label: "2nd", b: S.picks.stad[i][2]});
    } else {
      cols.push({key: `s${i}`, group: name, label: state.charpick ? "All" : name, b: S.picks.stad[i].all});
    }
  });
  if(!cols.some(c=>c.key === state.sort)) state.sort = "all";
  const sortCol = cols.find(c=>c.key === state.sort);
  const rate = (b, id)=>b.games ? (b.chars.get(id) || 0) / b.games : null;
  const chars = [...S.picks.all.chars.keys()].sort((a, b)=>
    (rate(sortCol.b, b) ?? -1) - (rate(sortCol.b, a) ?? -1) ||
    rate(S.picks.all, b) - rate(S.picks.all, a) || String(CHAR.get(a)).localeCompare(String(CHAR.get(b))));

  const sortBtn = c=>`<button type="button" class="sort" data-sort="${c.key}"${c.key === state.sort ? ` aria-sort="descending"` : ""}>` +
    `${esc(c.label)}${c.key === state.sort ? " &#9662;" : ""}<span class="n">${c.b.games.toLocaleString()} ${unit}</span></button>`;
  let head;
  if(state.charpick){
    const spans = [];
    cols.slice(1).forEach(c=>{ const last = spans[spans.length - 1];
      if(last && last.group === c.group) last.n++; else spans.push({group: c.group, n: 1}); });
    head = `<tr><th rowspan="2"></th><th rowspan="2">${sortBtn(cols[0])}</th>` +
      spans.map(s=>`<th class="group" colspan="${s.n}">${esc(s.group)}</th>`).join("") + `</tr>` +
      `<tr>${cols.slice(1).map(c=>`<th>${sortBtn(c)}</th>`).join("")}</tr>`;
  } else {
    head = `<tr><th></th>${cols.map(c=>`<th>${sortBtn(c)}</th>`).join("")}</tr>`;
  }
  const noun = MODE === "all" ? "teams" : "games";
  const td = (c, id)=>{
    if(!c.b.games) return `<td class="na">—</td>`;
    const n = c.b.chars.get(id) || 0, r = n / c.b.games;
    const step = r ? Math.max(1, Math.ceil(r * STEPS)) : 0;
    const where = c.key === "all" ? "all games" : c.group + (c.label === "1st" ? ", 1st pick" : c.label === "2nd" ? ", 2nd pick" : "");
    return `<td class="${step ? "h" + step : "zero"}" title="${esc(`${CHAR.get(id)}: ${n.toLocaleString()} of ${c.b.games.toLocaleString()} ${noun} (${where})`)}">` +
           `${Math.round(r * 100)}%</td>`;
  };
  const table = document.getElementById("picks");
  table.innerHTML = `<thead>${head}</thead><tbody>` +
    chars.map(id=>`<tr><th scope="row">${esc(CHAR.get(id) ?? `Character ${id}`)}</th>${cols.map(c=>td(c, id)).join("")}</tr>`).join("") +
    `</tbody>`;
  table.querySelectorAll(".sort").forEach(btn=>{
    btn.onclick = ()=>{ state.sort = btn.dataset.sort; drawPicks(); table.querySelector(`[data-sort="${state.sort}"]`).focus(); };
  });
}

/* ---- trophy case: a tournament, a year or all time; seasons have no trophies.
   Only on the player page. ---- */
const TROPHY = `<svg width="34" height="34" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor"
  d="M7 2h10v2h4v3.5A4.5 4.5 0 0 1 16.9 12 5 5 0 0 1 13 14.9V18h3.5v2h-9v-2H11v-3.1A5 5 0 0 1 7.1 12 4.5 4.5 0 0 1 3 7.5V4h4V2zm0 4H5v1.5a2.5 2.5 0 0 0 2 2.45V6zm10 0v3.95a2.5 2.5 0 0 0 2-2.45V6h-2zM6 21h12v1H6z"/></svg>`;
function drawTrophies(){
  const panel = document.getElementById("trophy-panel");
  if(!panel || !current.player) return;
  const {S, single, year} = current, box = document.getElementById("trophies");
  panel.hidden = !!(single && single.kind !== "tournament");
  if(panel.hidden) return;
  const card = t=>{
    const s = setBySlug.get(t.slug);
    return `<div class="trophy">${TROPHY}<div><div class="t-name">${esc(s.name)}</div>` +
      `<div class="t-meta">Champion &middot; ${esc(dayLabel(s.last_day))} &middot; ${t.record[0]}&ndash;${t.record[1]}</div></div></div>`;
  };
  if(single){
    const t = GI.trophies.find(t=>t.slug === single.slug);
    if(!t){
      box.innerHTML = `<p class="sub">${single.final ? "No champion recorded for this tournament."
                                                     : "The champion is decided once this tournament is over."}</p>`;
    } else if(t.user_id === state.uid){
      box.innerHTML = `<div class="trophies">${card(t)}</div>`;
    } else {
      const champ = playerById.get(t.user_id);
      box.innerHTML = `<p class="sub">No trophy in this one. Champion: <b>${esc(champ ? champ[1] : "unknown")}</b>` +
        ` (${t.record[0]}&ndash;${t.record[1]}).</p>`;
    }
    return;
  }
  const won = GI.trophies.filter(t=>t.user_id === state.uid && (year == null || t.year === year))
    .sort((a, b)=>setBySlug.get(b.slug).last_day - setBySlug.get(a.slug).last_day);
  const entered = S.tournaments.size, when = year != null ? ` in ${year}` : "";
  box.innerHTML = won.length
    ? `<div class="trophies">${won.map(card).join("")}</div>` +
      `<p class="note">${plural(won.length, "tournament")} won${when}, from ${plural(entered, "tournament")} played.</p>`
    : `<p class="sub">No tournament wins${when}${entered ? ` (${plural(entered, "tournament")} played)` : ""}.</p>`;
}

init();
