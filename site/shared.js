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

/* Why a metric shows n/a, from the same floors the build used. */
function whyNot(m, c, games){
  const r = rules[m.k] || [];
  if(r[1]!=null && (games||0) < r[1]) return `needs ${r[1]} games (has ${games||0})`;
  if(r[2]!=null && (c.den||0) < r[2]) return `needs ${r[2]} ${m.d} (has ${c.den||0})`;
  if(c.value==null) return "no data this season";
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
        (r[2]!=null ? ` Also needs ${r[2]} ${esc(m.d)} to qualify.` : "");
      return `<dt>${esc(m.label)}</dt>
        <dd>${esc(DEFINITIONS[m.k])}<span class="defs-rule">${rule}</span></dd>`;
    }).join("") + `</dl>`;
  }).join("");
  return `<div class="defs-inner">
    <div class="defs-head">
      <h2 id="defs-title">Metric definitions</h2>
      <button type="button" class="defs-close" aria-label="Close">&times;</button>
    </div>
    <p class="defs-note">Every metric needs ${minGames} games in the season to qualify.
      Percentiles rank a player against others in the same season, and 100 is always best.</p>
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
        fmt, counts, menuLabel, esc, badge, updatedLabel, whyNot, loadSeason, openDefinitions};
})();
