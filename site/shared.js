/* Shared by index.html (leaderboard) and compare.html: metric definitions,
   formatting, the metric definitions dialog, and on-demand season loading.
   A plain script rather than a module so both pages still work opened straight
   from disk. Load data/manifest.js first. */
"use strict";
window.MSSB = (() => {

/* Keys are Rio's season_metric names. Pages look metrics up BY NAME in each
   season file, so a change in the data's order cannot misalign them.
   n / d name the numerator and denominator shown under a rate. Per-9 metrics
   ("per9") have outs as their denominator, shown as innings. */
const METRICS = [
  {k:"gen_adjusted_elo",          label:"ELO",                 g:"general",  f:"int"},
  {k:"gen_games_played",          label:"Games Played",        g:"general",  f:"int"},
  {k:"gen_runs_per_9",            label:"Runs/9",              g:"general",  f:"per9",                         n:"runs scored"},
  {k:"gen_runs_against_per_9",    label:"Runs Against/9",      g:"general",  f:"per9",                         n:"runs allowed"},
  {k:"bat_barrel_pct",            label:"Barrel %",            g:"batting",  f:"pct", menu:"Barrel % (bat)",  n:"barrels",           d:"contacts"},
  {k:"bat_chase_pct",             label:"Chase %",             g:"batting",  f:"pct",                          n:"chases",            d:"out-of-zone pitches"},
  {k:"bat_whiff_pct",             label:"Whiff %",             g:"batting",  f:"pct", menu:"Whiff % (bat)",   n:"whiffs",            d:"swings"},
  {k:"bat_ozone_contact_pct",     label:"O-Zone Contact %",    g:"batting",  f:"pct",                          n:"contacts",          d:"out-of-zone swings"},
  {k:"bat_k_pct",                 label:"K %",                 g:"batting",  f:"pct", menu:"K % (bat)",       n:"strikeouts",        d:"plate appearances"},
  {k:"bat_charge_timing_pct",     label:"Charge Timing",       g:"batting",  f:"pct",                          n:"well-timed swings", d:"charge swings"},
  {k:"bat_slap_timing_pct",       label:"Slap Timing",         g:"batting",  f:"pct",                          n:"well-timed swings", d:"slap swings"},
  {k:"bat_charge_down_input_pct", label:"Charge Down-Input %", g:"batting",  f:"pct",                          n:"down inputs",       d:"contacted charge swings"},
  {k:"pitch_barrels_allowed_pct", label:"Barrels Allowed %",   g:"pitching", f:"pct",                          n:"barrels",           d:"contacts allowed"},
  {k:"pitch_whiff_pct",           label:"Whiff %",             g:"pitching", f:"pct", menu:"Whiff % (pitch)", n:"whiffs",            d:"swings induced"},
  {k:"pitch_k_pct",               label:"K %",                 g:"pitching", f:"pct", menu:"K % (pitch)",     n:"strikeouts",        d:"batters faced"},
  {k:"pitch_hr_allowed_pct",      label:"HR % Allowed",        g:"pitching", f:"pct",                          n:"home runs",         d:"at-bats vs power hitters"},
  {k:"pitch_special_catches_per_9", label:"Special Catches/9", g:"pitching", f:"per9",                         n:"special catches"},
];

/* ==========================================================================
   METRIC DEFINITIONS -- the text shown in the "Metric definitions" dialog.
   Edit freely. Say what the metric measures only: the dialog adds "Higher /
   Lower is better" and any extra qualification floor itself, from the same
   rules the build uses, so those can never drift from the data. Only metrics
   with an entry here appear in the dialog (ELO and Games Played have none).
   ========================================================================== */
const DEFINITIONS = {
  gen_runs_per_9:
    "Runs the player's team scores per 9 innings at bat (every 27 outs made).",
  gen_runs_against_per_9:
    "Runs the player's team allows per 9 innings in the field (every 27 outs recorded on defense).",
  bat_barrel_pct:
    "Share of the batter's contacts that are nice or perfect (nice-left, perfect, nice-right) rather than sour.",
  bat_chase_pct:
    "Share of pitches outside the strike zone that the batter swings at.",
  bat_whiff_pct:
    "Share of the batter's swings that miss the ball entirely.",
  bat_ozone_contact_pct:
    "Share of the batter's swings at pitches outside the strike zone that still make contact.",
  bat_k_pct:
    "Share of the batter's plate appearances that end in a strikeout.",
  bat_charge_timing_pct:
    "Share of charge swings that make contact on frames 7–9, out of charge swings making contact on frames 2–10. " +
    "Counts only Bowser, Petey, DK and the Bro and Pianta variants.",
  bat_slap_timing_pct:
    "Share of slap swings that make contact on frames 3–5, out of slap swings making contact on frames 2–10. " +
    "Counts every character.",
  bat_charge_down_input_pct:
    "Share of charge swings that make contact while the stick is held down, down-left or down-right. " +
    "Counts only the power hitters: Bowser, Petey, DK, King Boo, Wario and the Bro and Pianta variants.",
  pitch_barrels_allowed_pct:
    "Share of contacts allowed that are nice or perfect rather than sour.",
  pitch_whiff_pct:
    "Share of opposing batters' swings that miss the ball entirely.",
  pitch_k_pct:
    "Share of batters faced (plate appearances) that end in a strikeout.",
  pitch_hr_allowed_pct:
    "Home runs allowed per at-bat against the power hitters (Bowser, Petey, DK, King Boo, Wario and the " +
    "Bro and Pianta variants), not counting walks or hit-by-pitches.",
  pitch_special_catches_per_9:
    "Catches that record an out and are made with a dive, a wall jump or a jump, per 9 innings in the field. " +
    "Includes sac flies and foul catches.",
};

const GROUPS = [["general",null],["batting","Batting"],["pitching","Pitching/Fielding"]];

/* Colour marks the GROUP, not the value: green for general, blue for the rest,
   as on the source dashboard. */
const GCOLOR = {general:"var(--green)", batting:"var(--blue)", pitching:"var(--blue)"};

const FIELDS = ["value","percentile","pool_size","numerator","denominator","qualified"];
const manifest = window.MSSB_MANIFEST || {seasons: []};
const seasons = manifest.seasons || [];           /* oldest first */
const rules = manifest.metric_rules || {};        /* key -> [higher_is_better, min_games, min_denominator] */
const bySlug = Object.fromEntries(seasons.map(s=>[s.slug, s]));
const GAMES = METRICS.find(m=>m.k==="gen_games_played");

function fmt(m, v){
  if(v==null) return "—";
  if(m.f==="int") return Math.round(v).toLocaleString();
  if(m.f==="per9") return v.toFixed(2);
  return (v*100).toFixed(1)+"%";
}
/* Outs as innings in baseball notation: 136 outs is 45.1 (45 and one third). */
function innings(outs){ return Math.floor(outs/3) + (outs % 3 ? "." + (outs % 3) : ""); }
/* The counts behind a rate, for the line under its label and its tooltip.
   null for metrics with no counts (ELO, games played). */
function counts(m, c){
  if(!c || c.den==null) return null;
  return m.f==="per9"
    ? {text:`${c.num} in ${innings(c.den)} inn`, title:`${c.num} ${m.n} in ${innings(c.den)} innings (${c.den} outs)`}
    : {text:`${c.num}/${c.den}`, title:`${c.num} ${m.n} of ${c.den} ${m.d}`};
}
function menuLabel(m){ return m.menu || m.label; }
/* Usernames come from the database and are rendered on a public page. */
function esc(s){
  return String(s).replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function badge(s){
  return s.final ? `<span class="badge">FINAL</span>` : `<span class="badge live">IN PROGRESS</span>`;
}
function updatedLabel(s){
  return s.built_at
    ? new Date(s.built_at).toLocaleString([], {dateStyle:"medium", timeStyle:"short"}) : "?";
}

/* ---- Netplay Superstars tournaments ----
   Built like seasons but ranked with no minimums (see build_seasons.py). */
const isTournament = s => !!s && s.kind === "tournament";
const TOURNAMENT_NOTE =
  "Every player who played is ranked on every metric, however few games, swings or at-bats, " +
  "so small samples can produce extreme percentiles.";
/* The newest Stars Off season, which pages open on (a tournament can be newer). */
function latestSeason(){
  return [...seasons].reverse().find(s=>!isTournament(s)) || seasons[seasons.length-1];
}
/* ---- multiple selections ----
   Several seasons and/or tournaments shown as one: players are ranked on
   their totals across the selection (see combine()). */
const isCombined = s => !!s && s.kind === "combined";
/* Tournaments have no minimums, and so does any selection that includes one. */
const noMinimums = s => isTournament(s) || (isCombined(s) && s.includesTournament);
const ELO_NOTE = "ELO isn't shown when more than one season or tournament is selected.";
/* Manifest order (oldest first), unknown slugs dropped, duplicates removed. */
function orderSlugs(slugs){ return seasons.filter(s=>slugs.includes(s.slug)).map(s=>s.slug); }
const selectionKey = slugs => orderSlugs(slugs).join("+");
function shortName(s){
  let m;
  if((m = s.name.match(/^S(\d+) Superstars Off$/i)) || (m = s.name.match(/^Stars Off, Season (\d+)$/i))) return "S" + m[1];
  if((m = s.name.match(/^(?:Netplay Superstars|NPSS)\s*(\d+)$/i))) return "NPSS " + m[1];
  if(/^Interim/i.test(s.name)) return "Interim";
  return s.name;
}
/* "S15 Superstars Off" for one; "S11 + S12 + S13" for a few; "6 selected" beyond that. */
function selectionLabel(slugs){
  const list = orderSlugs(slugs).map(sl=>bySlug[sl]);
  if(list.length === 1) return list[0].name;
  return list.length <= 4 ? list.map(shortName).join(" + ") : `${list.length} selected`;
}

/* Why a metric shows n/a, from the same floors the build used. Tournaments
   (and selections that include one) have no floors, so there it only ever
   means the player has no data. */
function whyNot(m, c, games, entry){
  if(isCombined(entry) && m.k === "gen_adjusted_elo") return "not shown for multiple selections";
  if(noMinimums(entry)) {
    return c.value==null ? `no data in this ${isCombined(entry) ? "selection" : "tournament"}` : "not qualified";
  }
  const r = rules[m.k] || [], scope = isCombined(entry) ? " combined" : "";
  if(r[1]!=null && (games||0) < r[1]) return `needs ${r[1]} games${scope} (has ${games||0})`;
  if(r[2]!=null && (c.den||0) < r[2]) return `needs ${r[2]} ${m.d}${scope} (has ${c.den||0})`;
  if(c.value==null) return isCombined(entry) ? "no data in this selection" : "no data this season";
  return "not qualified";
}

/* Wrap one season file with lookups. Percentiles inside it are ranked within
   that season only -- never mix players across seasons in one ranking. */
function makeSeason(entry, d){
  const slot = {}, fi = {};
  (d.metrics||[]).forEach((k,n)=>{ slot[k]=n; });
  (d.fields||[]).forEach((f,n)=>{ fi[f]=n; });
  const missing = METRICS.map(m=>m.k).filter(k=>!(k in slot))
    .concat(FIELDS.filter(f=>!(f in fi)));
  const players = missing.length ? [] : d.players.map(([id, name, m])=>({id, name, m}));
  const cell = (p, m)=>{
    const c = p.m[slot[m.k]];
    return c ? {value:c[fi.value], pct:c[fi.percentile], pool:c[fi.pool_size],
                num:c[fi.numerator], den:c[fi.denominator], ok:c[fi.qualified]} : null;
  };
  /* Qualified players for one metric, best first; ties broken by name, like
     Rio's leaderboard endpoint. */
  const board = m => players.filter(p=>{ const c=cell(p,m); return c && c.ok; })
    .sort((a,b)=> cell(b,m).pct - cell(a,m).pct || a.name.localeCompare(b.name));
  const games = p => (cell(p, GAMES)||{}).value;
  return {entry, players, missing, cell, board, games,
          byId: new Map(players.map(p=>[p.id, p]))};
}

/* Load a season's file once, however many callers ask for it at the same time. */
const loading = {};
function loadSeason(slug){
  const entry = bySlug[slug];
  if(!entry) return Promise.reject(new Error(`Unknown season "${slug}".`));
  if(!loading[slug]) loading[slug] = new Promise((resolve, reject)=>{
    const ready = ()=>{
      const d = (window.MSSB_SEASONS||{})[slug];
      if(d) resolve(makeSeason(entry, d));
      else reject(new Error(`data/${entry.file} loaded but did not contain ${entry.name}. Re-run build_seasons.py.`));
    };
    if(window.MSSB_SEASONS && window.MSSB_SEASONS[slug]){ ready(); return; }
    const tag = document.createElement("script");
    /* built_at changes whenever the file is rebuilt, so browsers never show a
       stale copy of the current season. */
    const bust = location.protocol === "file:" ? "" : "?v=" + encodeURIComponent(entry.built_at || "");
    tag.src = "data/" + entry.file + bust;
    tag.onload = ready;
    tag.onerror = ()=>{ delete loading[slug]; reject(new Error(`Could not load data/${entry.file}.`)); };
    document.head.appendChild(tag);
  });
  return loading[slug];
}

/* Port of Rio's season_metrics.percentile_ranks(): 0-100 where 100 is always
   best, tied values take the lower rank (like Postgres percent_rank()), and a
   lone qualifier scores 100. */
function percentileRanks(values, higherIsBetter){
  const n = values.length;
  if(!n) return [];
  if(n === 1) return [100];
  const below = new Map();
  [...values].sort((a,b)=>a-b).forEach((v,i)=>{ if(!below.has(v)) below.set(v, i); });
  return values.map(v=>{ const pr = below.get(v) / (n-1); return (higherIsBetter ? pr : 1 - pr) * 100; });
}

/* Rank players on their totals across several seasons/tournaments. Mirrors
   Rio's build_rows() and qualifies() on summed counts: each rate is recomputed
   from the summed numerator and denominator (27 x runs / outs for per-9s),
   games are summed, and the season floors apply to those totals -- unless a
   tournament is included, when there are none. ELO has no meaningful total,
   so it is never ranked here. Returns the same shape as a single season. */
const PER_9 = new Set(METRICS.filter(m=>m.f==="per9").map(m=>m.k));
function combine(views){
  const entries = views.map(v=>v.entry);
  const includesTournament = entries.some(isTournament);
  const acc = new Map();
  views.forEach(v=>v.players.forEach(p=>{
    let a = acc.get(p.id);
    if(!a) acc.set(p.id, a = {id: p.id, name: p.name, games: 0, counts: {}});
    a.name = p.name;                       /* views run oldest first: newest name wins */
    a.games += v.games(p) || 0;
    METRICS.forEach(m=>{
      const c = v.cell(p, m);
      if(!c || c.den == null) return;
      const t = a.counts[m.k] || (a.counts[m.k] = [0, 0]);
      t[0] += c.num || 0;
      t[1] += c.den || 0;
    });
  }));
  const people = [...acc.values()].filter(a=>a.games > 0)
    .sort((x,y)=>{ const a = x.name.toLowerCase(), b = y.name.toLowerCase(); return a < b ? -1 : a > b ? 1 : 0; });

  const cells = new Map(people.map(a=>[a.id, []]));
  METRICS.forEach((m, mi)=>{
    const r = rules[m.k] || [true, null, null];
    const staged = people.map(a=>{
      let value = null, num = null, den = null;
      if(m.k === "gen_games_played") value = a.games;
      else if(m.k !== "gen_adjusted_elo"){
        [num, den] = a.counts[m.k] || [0, 0];
        value = den ? (PER_9.has(m.k) ? 27 : 1) * num / den : null;
      }
      let ok = value != null;
      if(ok && !includesTournament){
        if(r[1] != null && a.games < r[1]) ok = false;
        if(r[2] != null && (den || 0) < r[2]) ok = false;
      }
      if(den != null && den <= 0) ok = false;
      return {id: a.id, cell: [value, null, null, num, den, ok]};   /* FIELDS order */
    });
    const pool = staged.filter(s=>s.cell[5]);
    percentileRanks(pool.map(s=>s.cell[0]), r[0] !== false).forEach((pct, i)=>{
      pool[i].cell[1] = pct;
      pool[i].cell[2] = pool.length;
    });
    staged.forEach(s=>{ cells.get(s.id)[mi] = s.cell; });
  });

  const slugs = entries.map(e=>e.slug);
  const builtAt = entries.map(e=>e.built_at || "").sort().pop();
  const entry = {
    kind: "combined", slug: slugs.join("+"), slugs, includesTournament,
    name: entries.map(e=>e.name).join(" + "), label: selectionLabel(slugs),
    seasonCount: entries.filter(e=>!isTournament(e)).length,
    tournamentCount: entries.filter(isTournament).length,
    start: entries.map(e=>e.start).sort()[0], end: entries.map(e=>e.end).sort().pop(),
    final: entries.every(e=>e.final), built_at: builtAt, players: people.length,
  };
  const view = makeSeason(entry, {metrics: METRICS.map(m=>m.k), fields: FIELDS,
                                  players: people.map(a=>[a.id, a.name, cells.get(a.id)])});
  entry.qualified = view.players.filter(p=>(view.cell(p, GAMES)||{}).ok).length;
  return view;
}

/* One slug: that season as built. Several: their combination, computed once. */
const combos = {};
function loadSelection(slugs){
  const ordered = orderSlugs(slugs);
  if(!ordered.length) return Promise.reject(new Error("Nothing selected."));
  if(ordered.length === 1) return loadSeason(ordered[0]);
  const key = ordered.join("+");
  if(!combos[key]) combos[key] = Promise.all(ordered.map(loadSeason)).then(views=>{
    const broken = views.find(v=>v.missing.length);
    if(broken) throw new Error(`${broken.entry.name} is missing ${broken.missing.join(", ")}.`);
    return combine(views);
  }).catch(err=>{ delete combos[key]; throw err; });
  return combos[key];
}

/* ---- season / tournament picker ----
   A button that opens a checkbox list. Clicking a name shows just that one;
   ticking boxes combines several. At least one always stays selected. */
let pickerCount = 0;
function seasonPicker(host, {selected, onChange, buttonId}){
  const uid = "pk" + (++pickerCount);
  let current = orderSlugs(selected);
  const meta = s => (s.final ? "" : "in progress · ") +
    (isTournament(s) ? `${s.players} players` : `${s.qualified} qualified`);
  const groups = [["Stars Off seasons", s=>!isTournament(s)], ["Netplay Superstars tournaments", isTournament]]
    .map(([title, keep])=>{
      const list = seasons.filter(keep);
      return list.length ? `<div class="picker-group-title">${esc(title)}</div>` + list.map(s=>`
        <div class="picker-row">
          <input type="checkbox" id="${uid}-${esc(s.slug)}" value="${esc(s.slug)}" aria-label="${esc(s.name)}">
          <button type="button" class="picker-name" data-slug="${esc(s.slug)}"
                  title="Show only ${esc(s.name)}">${esc(s.name)}</button>
          <span class="picker-meta">${esc(meta(s))}</span>
        </div>`).join("") : "";
    }).join("");
  host.classList.add("picker");
  host.innerHTML = `
    <button type="button" class="picker-btn" ${buttonId ? `id="${esc(buttonId)}"` : ""} aria-expanded="false">
      <span class="picker-label"></span><span class="picker-caret" aria-hidden="true">&#9662;</span>
    </button>
    <div class="picker-panel" hidden>
      <p class="picker-hint">Click a name to show just that one, or tick boxes to combine several.</p>
      ${groups}
    </div>`;
  const btn = host.querySelector(".picker-btn"), panel = host.querySelector(".picker-panel"),
        hint = host.querySelector(".picker-hint"), label = host.querySelector(".picker-label");

  const sync = ()=>{
    host.querySelectorAll("input[type=checkbox]").forEach(cb=>{ cb.checked = current.includes(cb.value); });
    label.textContent = selectionLabel(current);
    btn.title = current.map(sl=>bySlug[sl].name).join(", ");
  };
  const emit = ()=>{ sync(); onChange(current.slice()); };
  const open = ()=>{
    panel.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    panel.style.left = ""; panel.style.right = "";
    if(panel.getBoundingClientRect().right > window.innerWidth - 8){ panel.style.left = "auto"; panel.style.right = "0"; }
    const first = host.querySelector("input:checked");
    if(first){ first.closest(".picker-row").scrollIntoView({block: "nearest"}); first.focus({preventScroll: true}); }
  };
  const HINT = hint.textContent;
  const close = (focusButton)=>{
    if(panel.hidden) return;
    panel.hidden = true;
    btn.setAttribute("aria-expanded", "false");
    hint.textContent = HINT;
    hint.classList.remove("picker-warn");
    if(focusButton) btn.focus();
  };

  btn.addEventListener("click", ()=> panel.hidden ? open() : close());
  panel.addEventListener("change", e=>{
    const cb = e.target;
    if(cb.type !== "checkbox") return;
    if(!cb.checked && current.length === 1){
      cb.checked = true;
      hint.textContent = "At least one season or tournament has to stay selected.";
      hint.classList.add("picker-warn");
      return;
    }
    current = cb.checked ? orderSlugs([...current, cb.value]) : current.filter(sl=>sl !== cb.value);
    emit();
  });
  panel.addEventListener("click", e=>{
    const name = e.target.closest(".picker-name");
    if(!name) return;
    current = [name.dataset.slug];
    emit();
    close(true);
  });
  document.addEventListener("pointerdown", e=>{ if(!host.contains(e.target)) close(); });
  host.addEventListener("keydown", e=>{ if(e.key === "Escape"){ e.stopPropagation(); close(true); } });

  sync();
  return {get: ()=>current.slice(), set: slugs=>{ current = orderSlugs(slugs); sync(); }, close};
}

/* ---- metric definitions dialog ---- */
function definitionsHTML(){
  const minGames = (rules.bat_barrel_pct || [])[1] ?? 10;
  /* One section per group, in page order, listing the metrics that have a
     definition. General's heading is blank on the pages, so it is named here. */
  const sections = GROUPS.map(([g, title])=>{
    const defined = METRICS.filter(m=>m.g===g && DEFINITIONS[m.k]);
    if(!defined.length) return "";
    return `<h3>${esc(title || "General")}</h3><dl>` + defined.map(m=>{
      const r = rules[m.k] || [];
      const rule = (r[0] === false ? "Lower is better." : "Higher is better.") +
        (r[2]!=null ? ` In seasons, also needs ${r[2]} ${esc(m.d)} to qualify.` : "");
      return `<dt>${esc(m.label)}</dt>
        <dd>${esc(DEFINITIONS[m.k])}<span class="defs-rule">${rule}</span></dd>`;
    }).join("") + `</dl>`;
  }).join("");
  return `<div class="defs-inner">
    <div class="defs-head">
      <h2 id="defs-title">Metric definitions</h2>
      <button type="button" class="defs-close" aria-label="Close">&times;</button>
    </div>
    <p class="defs-note">In Stars Off seasons, every metric needs ${minGames} games in the season to
      qualify. Percentiles rank a player against others in the same season or tournament, and 100 is
      always best.</p>
    <p class="defs-note defs-tournament"><b>Netplay Superstars tournaments have no minimums.</b>
      Every player who played is ranked on every metric they have data for, including the extra
      minimums listed below. Tournament fields are small and the competition is strong, so a player
      with only a few games, swings or at-bats can land at either extreme.</p>
    <p class="defs-note defs-tournament"><b>Several seasons or tournaments selected at once</b> rank
      players on their combined totals across the selection. Minimums apply to those totals (10 games
      across the selection, and so on) unless the selection includes a tournament, in which case there
      are none. ELO isn't shown for a multiple selection, because a rating belongs to one season or
      tournament.</p>
    ${sections}
  </div>`;
}
function openDefinitions(){
  let dlg = document.getElementById("defs");
  if(!dlg){
    dlg = document.createElement("dialog");
    dlg.id = "defs";
    dlg.className = "defs";
    dlg.setAttribute("aria-labelledby", "defs-title");
    dlg.innerHTML = definitionsHTML();
    dlg.querySelector(".defs-close").onclick = ()=>dlg.close();
    /* The dialog has no padding of its own, so a click whose target is the
       dialog itself landed on the backdrop. */
    dlg.addEventListener("click", e=>{ if(e.target===dlg) dlg.close(); });
    document.body.appendChild(dlg);
  }
  dlg.showModal();
}

/* ---- dark mode switch ----
   With no saved choice the page follows the device's setting. Flipping the
   switch saves an explicit choice, which the script in each page's <head>
   applies before the first paint on later visits. */
function setupThemeToggle(){
  const btn = document.getElementById("theme-toggle");
  if(!btn) return;
  const root = document.documentElement;
  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  const isDark = ()=> root.dataset.theme ? root.dataset.theme === "dark" : !!(media && media.matches);
  const sync = ()=> btn.setAttribute("aria-checked", String(isDark()));
  btn.addEventListener("click", ()=>{
    const next = isDark() ? "light" : "dark";
    root.dataset.theme = next;
    try{ localStorage.setItem("mssb-theme", next); }catch(e){ /* private mode: still switches */ }
    sync();
  });
  if(media && media.addEventListener) media.addEventListener("change", sync);
  sync();
}
setupThemeToggle();

return {METRICS, GROUPS, GCOLOR, DEFINITIONS, seasons, bySlug, rules,
        fmt, counts, menuLabel, esc, badge, updatedLabel, whyNot, loadSeason, openDefinitions,
        isTournament, TOURNAMENT_NOTE, latestSeason,
        isCombined, noMinimums, ELO_NOTE, orderSlugs, selectionKey, selectionLabel,
        loadSelection, seasonPicker, _combine: combine, _percentileRanks: percentileRanks};
})();
