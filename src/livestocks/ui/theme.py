"""Design tokens and global CSS ported from the approved dashboard mock.
Colours are CSS variables, dark by default with a light override class.
FONTS_HEAD loads IBM Plex and CSS is injected once per page.
"""

FONTS_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
"""

CSS = r"""

:root {
  --bg: #0c111b; --surface: #131a28; --surface-2: #182134; --line: #243049;
  --fg: #e6ebf5; --muted: #8a97b2; --faint: #5c6985;
  --accent: #6ea0ff; --accent-soft: #6ea0ff22;
  --pos: #34c38f; --neg: #f0616d; --warn: #e8b04a;
  --pos-soft: #34c38f1f; --neg-soft: #f0616d1f; --warn-soft: #e8b04a1f;
  --track: #263250; --shadow: 0 1px 0 #ffffff08 inset;
  --sans: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Consolas, monospace;
  color-scheme: dark;
}
body.body--light {
  --bg: #f3f5f9; --surface: #ffffff; --surface-2: #f6f8fc; --line: #dfe4ee;
  --fg: #121a2b; --muted: #5a6781; --faint: #8591aa;
  --accent: #2e62d9; --accent-soft: #2e62d91a;
  --pos: #0f8f63; --neg: #c8323f; --warn: #a96f0a;
  --pos-soft: #0f8f6318; --neg-soft: #c8323f14; --warn-soft: #a96f0a18;
  --track: #dde3ef; --shadow: 0 1px 2px #1a2a4a0f;
  color-scheme: light;
}
* { box-sizing: border-box; }
body, .q-page, .q-layout { background: var(--bg) !important; color: var(--fg); font: 14px/1.45 var(--sans); }
.nicegui-content { padding: 0 !important; gap: 0 !important; align-items: stretch !important; padding-bottom: 40px !important; }
button, input { font: inherit; color: inherit; }
button { cursor: pointer; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.num { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.wrap { max-width: 1280px; width: 100%; margin-inline: auto; padding-inline: 16px; }

/* header */
.top { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 20; background: color-mix(in srgb, var(--bg) 88%, transparent); backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); }
.top .wrap { display: flex; align-items: center; gap: 16px; padding-block: 12px; flex-wrap: wrap; }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 600; letter-spacing: .01em; cursor: pointer; background: none; border: 0; padding: 0; }
.brand svg { display: block; }
.brand small { display: block; font-weight: 400; color: var(--muted); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; }
.add { flex: 1 1 320px; display: flex; gap: 8px; max-width: 520px; margin-inline: auto; }
.add input { flex: 1; min-width: 0; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 9px 12px; }
.add input::placeholder { color: var(--faint); }
.btn { background: var(--accent); color: #fff; border: 0; border-radius: 8px; padding: 9px 14px; font-weight: 500; }
.btn.ghost { background: var(--surface); color: var(--fg); border: 1px solid var(--line); }
.btn.icon { padding: 8px 10px; line-height: 0; }
.status { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; margin-left: auto; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--pos); box-shadow: 0 0 0 3px var(--pos-soft); }
.dot.busy { background: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: .35; } }

main { padding-block: 24px; display: grid; gap: 20px; }
.page-title { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
h1 { margin: 0; font-size: 20px; font-weight: 600; text-wrap: balance; }
.sample { font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--warn); background: var(--warn-soft); border-radius: 999px; padding: 2px 10px; }
.sub { color: var(--muted); }

/* cards */
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; box-shadow: var(--shadow); min-width: 0; }
.card h2 { margin: 0; font-size: 13px; font-weight: 600; color: var(--fg); }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px 0; flex-wrap: wrap; }
.card-body { padding: 14px 16px 16px; }
.kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.kpi { padding: 14px 16px; }
.kpi .label { color: var(--muted); font-size: 12px; letter-spacing: .04em; text-transform: uppercase; }
.kpi .value { font-family: var(--mono); font-size: 26px; font-weight: 500; margin-top: 6px; letter-spacing: -.01em; }
.kpi .note { color: var(--muted); font-size: 12px; margin-top: 2px; }
.pos { color: var(--pos); } .neg { color: var(--neg); } .warn { color: var(--warn); }

/* table */
.tablewrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; min-width: 940px; }
th { text-align: left; font-weight: 500; font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); padding: 12px 12px; border-bottom: 1px solid var(--line); white-space: nowrap; background: var(--surface); position: sticky; top: 0; }
th.r, td.r { text-align: right; }
th button { background: none; border: 0; padding: 0; color: inherit; font: inherit; letter-spacing: inherit; text-transform: inherit; display: inline-flex; gap: 4px; align-items: center; }
th button:hover { color: var(--fg); }
th[aria-sort] button { color: var(--fg); }
td { padding: 12px; border-bottom: 1px solid var(--line); vertical-align: middle; white-space: nowrap; }
tbody tr { cursor: pointer; transition: background .12s; }
tbody tr:hover { background: var(--surface-2); }
tbody tr:last-child td { border-bottom: 0; }
.tk { display: flex; align-items: center; gap: 10px; }
.tk .badge-ex { width: 34px; height: 34px; border-radius: 8px; background: var(--surface-2); border: 1px solid var(--line); display: grid; place-items: center; font-family: var(--mono); font-size: 10px; color: var(--muted); }
.tk b { font-weight: 600; letter-spacing: .02em; }
.tk span.nm { display: block; color: var(--muted); font-size: 12px; }
.chip { display: inline-flex; align-items: center; gap: 4px; font-family: var(--mono); font-size: 12px; padding: 2px 8px; border-radius: 6px; }
.chip.pos { background: var(--pos-soft); } .chip.neg { background: var(--neg-soft); } .chip.warn { background: var(--warn-soft); }
.chg { font-family: var(--mono); font-size: 12px; margin-top: 2px; }
.rate { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; padding: 3px 9px; border-radius: 999px; border: 1px solid currentColor; }
.rate.buy { color: var(--pos); } .rate.hold { color: var(--warn); } .rate.sell { color: var(--neg); }
.rate i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.muted { color: var(--muted); }
.act { background: none; border: 0; color: var(--faint); padding: 6px; border-radius: 6px; line-height: 0; }
.act:hover { color: var(--neg); background: var(--neg-soft); }

/* range bar */
.range { position: relative; width: 190px; height: 34px; }
.range .track { position: absolute; left: 0; right: 0; top: 11px; height: 4px; border-radius: 2px; background: var(--track); }
.range .fill { position: absolute; top: 11px; height: 4px; border-radius: 2px; background: var(--accent); opacity: .55; }
.range .avg { position: absolute; top: 6px; width: 2px; height: 14px; background: var(--accent); border-radius: 1px; transform: translateX(-1px); }
.range .px { position: absolute; top: 7px; width: 12px; height: 12px; border-radius: 50%; background: var(--fg); border: 2px solid var(--surface); box-shadow: 0 0 0 1px var(--fg); transform: translateX(-6px); }
.range .lo, .range .hi { position: absolute; top: 20px; font-family: var(--mono); font-size: 10px; color: var(--faint); }
.range .lo { left: 0; } .range .hi { right: 0; }
.legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px; color: var(--muted); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.sw { display: inline-block; }
.sw.px { width: 10px; height: 10px; border-radius: 50%; background: var(--fg); }
.sw.avg { width: 2px; height: 12px; background: var(--accent); }
.sw.span { width: 16px; height: 4px; border-radius: 2px; background: var(--accent); opacity: .55; }

/* states */
.spin { width: 14px; height: 14px; border-radius: 50%; border: 2px solid var(--track); border-top-color: var(--accent); animation: rot .8s linear infinite; display: inline-block; vertical-align: -2px; margin-right: 6px; }
@keyframes rot { to { transform: rotate(360deg); } }
.err { color: var(--neg); font-size: 12px; }
.empty { display: grid; place-items: center; text-align: center; padding: 56px 16px; gap: 10px; }
.empty h3 { margin: 0; font-size: 16px; }
.empty p { margin: 0; color: var(--muted); max-width: 44ch; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; margin-top: 6px; }

/* lower grid */
.grid2 { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 12px; }
.rank { display: grid; gap: 8px; }
.rank-row { display: grid; grid-template-columns: 52px 1fr 64px; align-items: center; gap: 10px; font-size: 12px; }
.rank-row .t { font-weight: 600; letter-spacing: .02em; }
.rank-row .bar { position: relative; height: 14px; }
.rank-row .bar i { position: absolute; top: 0; height: 100%; border-radius: 3px; }
.rank-row .bar::before { content: ""; position: absolute; left: var(--zero); top: -4px; bottom: -4px; width: 1px; background: var(--line); }
.rank-row .v { text-align: right; }
.dist { display: flex; height: 14px; gap: 2px; border-radius: 4px; overflow: hidden; margin-block: 10px 14px; }
.dist i { display: block; min-width: 4px; }
.dist-list { display: grid; gap: 8px; font-size: 13px; }
.dist-list div { display: flex; justify-content: space-between; gap: 8px; }
.dist-list span { display: inline-flex; align-items: center; gap: 8px; }
.dist-list i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }

/* detail */
.crumb { display: flex; align-items: center; gap: 8px; color: var(--muted); }
.crumb button { background: none; border: 0; color: var(--accent); padding: 0; }
.dhead { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; flex-wrap: wrap; }
.dhead .big { font-family: var(--mono); font-size: 34px; font-weight: 500; letter-spacing: -.02em; line-height: 1.1; }
.dgrid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 12px; }
.facts { display: grid; gap: 0; }
.facts div { display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--line); }
.facts div:last-child { border-bottom: 0; }
.facts dt { color: var(--muted); } .facts dd { margin: 0; font-family: var(--mono); text-align: right; }
.seg { display: inline-flex; background: var(--surface-2); border: 1px solid var(--line); border-radius: 8px; padding: 2px; }
.seg button { background: none; border: 0; padding: 4px 10px; border-radius: 6px; color: var(--muted); font-size: 12px; }
.seg button[aria-pressed="true"] { background: var(--accent-soft); color: var(--accent); }
.big-range { position: relative; height: 96px; margin: 22px 8px 4px; }
.big-range .track { position: absolute; left: 0; right: 0; top: 46px; height: 8px; border-radius: 4px; background: var(--track); }
.big-range .fill { position: absolute; top: 46px; height: 8px; border-radius: 4px; background: linear-gradient(90deg, color-mix(in srgb, var(--accent) 35%, transparent), var(--accent)); }
.pin { position: absolute; top: 0; transform: translateX(-50%); text-align: center; font-size: 11px; color: var(--muted); }
.pin b { display: block; font-family: var(--mono); font-size: 13px; color: var(--fg); font-weight: 500; }
.pin::after { content: ""; display: block; width: 1px; height: 22px; background: var(--faint); margin: 2px auto 0; }
.pin.below { top: auto; bottom: -4px; }
.pin.below::after { display: none; }
.pin.px b { color: var(--fg); }
.pin.avg::after { background: var(--accent); width: 2px; }
.gauge-wrap { display: grid; place-items: center; }
.tip { position: absolute; pointer-events: none; background: var(--surface-2); border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; font-size: 12px; box-shadow: 0 6px 20px #0006; display: none; z-index: 5; min-width: 150px; }
.tip .row { display: flex; justify-content: space-between; gap: 14px; }
.chartbox { position: relative; }
footer { color: var(--faint); font-size: 12px; display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
footer button { background: none; border: 0; color: var(--accent); padding: 0; text-decoration: underline; }

@media (max-width: 900px) {
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid2, .dgrid { grid-template-columns: minmax(0, 1fr); }
  .status { margin-left: 0; }
}
@media (max-width: 520px) {
  .kpis { grid-template-columns: minmax(0, 1fr); }
  .kpi .value { font-size: 22px; }
  .dhead .big { font-size: 28px; }
}
@media (prefers-reduced-motion: reduce) { .dot.busy, .spin { animation: none; } }
"""

EXTRA_CSS = r"""
h1, h2, h3 { line-height: 1.25; letter-spacing: normal; font-family: var(--sans); }
.add .add-field input { border: 0 !important; background: transparent !important; padding: 0 !important; box-shadow: none !important; }
.add { align-items: stretch; }
.add .add-field { flex: 1; min-width: 0; }
.add .q-field__control { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 0 12px; height: 38px; }
.add .q-field__native, .add input { color: var(--fg) !important; font-family: var(--sans); }
.add .q-field__native::placeholder, .add input::placeholder { color: var(--faint); opacity: 1; }
.add .q-field--focused .q-field__control { border-color: var(--accent); }
.crumb button { cursor: pointer; }
.foot { padding-block: 8px 0; color: var(--faint); font-size: 12px; }
td.r .act { margin-left: 2px; }
.act.retry:hover { color: var(--accent); background: var(--accent-soft); }
.page-title { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
main { display: grid; grid-template-columns: minmax(0, 1fr); gap: 20px; padding-block: 24px; width: 100%; min-width: 0; }
.wrap, .nicegui-content, .q-page { min-width: 0; max-width: 100%; }
body { overflow-x: hidden; }
.nicegui-content > .wrap { align-self: center; }
"""
CSS = CSS + EXTRA_CSS

EXTRA_CSS_2 = r"""
.gauge-wrap { flex-direction: column; }
.fingrid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.tablewrap.fin { margin-top: 8px; }
.fintable { min-width: 0; width: max-content; min-width: 100%; font-size: 12px; }
.fintable th, .fintable td { padding: 8px 10px; }
.fintable thead th { position: static; }
.fintable thead th:first-child, .fintable tbody th { position: sticky; left: 0; z-index: 1; min-width: 84px; background: var(--surface); box-shadow: 1px 0 0 var(--line); }
.fintable tbody tr:last-child th { border-bottom: 0; }
.fintable tbody th { text-align: left; text-transform: none; letter-spacing: normal; font-size: 12px; font-weight: 500; color: var(--muted); position: sticky; left: 0; background: var(--surface); }
.fintable tbody tr { cursor: default; }
.fintable tbody tr:hover { background: transparent; }
@media (max-width: 1000px) { .fingrid { grid-template-columns: minmax(0, 1fr); } }
"""
CSS = CSS + EXTRA_CSS_2

EXTRA_CSS_3 = r"""
.chartcard { display: flex; flex-direction: column; }
.chartcard .chartbody { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.chartcard .chartbody > .nicegui-echart { flex: 1; }
@media (max-width: 900px) { .chartcard .chartbody > .nicegui-echart { min-height: 340px !important; } }
"""
CSS = CSS + EXTRA_CSS_3

EXTRA_CSS_4 = r"""
.fine { font-size: 12px; }
.sugtable { min-width: 720px; }
.sugtable tbody tr { cursor: default; }
.sugtable tbody tr:hover { background: transparent; }
.sugtable tbody tr:not(.why) td { border-bottom: 0; padding-bottom: 4px; }
.sugtable .why td { padding-top: 0; white-space: normal; font-size: 12px; }
.sug-head { display: grid; gap: 8px; }
.sug-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.sug-chips:empty { display: none; }
.sug-summary { margin: 0; max-width: 90ch; }
.sug-moves { display: grid; gap: 8px; margin-top: 10px; }
.sug-move { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.btn.fine { padding: 6px 10px; }
.sug-dash .sug-head { gap: 12px; }
.sug-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); gap: 12px; }
.sug-card { background: var(--surface-2); border: 1px solid var(--line); border-left: 3px solid var(--line); border-radius: 10px; padding: 14px; display: grid; gap: 10px; align-content: start; min-width: 0; }
.sug-card.buy { border-left-color: var(--pos); } .sug-card.sell { border-left-color: var(--neg); }
.sug-card header { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.sug-card .tk b { font-size: 16px; }
.sug-badges { display: flex; gap: 6px; flex-wrap: wrap; }
.sug-badges .chip { font-size: 11px; background: var(--track); color: var(--muted); }
.sug-badges .chip.warn { background: var(--warn-soft); color: var(--warn); }
.sug-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; background: var(--line); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.sug-m { background: var(--surface); padding: 8px 10px; display: grid; gap: 2px; align-content: start; min-width: 0; }
.sug-m span { font-size: 10px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.sug-m b { font-size: 14px; font-weight: 500; }
.sug-m small { font-size: 11px; font-family: var(--mono); color: var(--muted); overflow-wrap: anywhere; }
.sug-m.pos b { color: var(--pos); } .sug-m.neg b, .sug-m.neg small { color: var(--neg); }
.sug-why { margin: 0; font-size: 13px; line-height: 1.5; }
.sug-hold { border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; }
.sug-hold summary { cursor: pointer; display: flex; align-items: center; gap: 10px; }
.sug-hold ul { list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 8px; }
.sug-hold li { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 10px; font-size: 12px; }
@media (max-width: 520px) { .sug-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
"""
CSS = CSS + EXTRA_CSS_4
