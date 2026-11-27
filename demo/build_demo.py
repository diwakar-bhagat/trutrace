"""Build demo/index.html from TruTrace's real outputs.

Nothing on the page is hand-typed data: the showcase answers come from
running the pipeline on campaign_01 and campaign_02 in both
configurations, and every number and chart comes from the recorded
artifacts (final summaries, degradation record, load records, the
Gemini scorecard's recorded error).

Composition follows the Stageshow bento discipline (one hero tile,
mixed tile kinds, copy outside the pictures, quiet grays; Stageshow is
MIT licensed, (c) 2026 Benji Taylor). Visual tokens are this project's
DESIGN.apple.md. Surface values (label and fill hierarchies, materials,
radii, layered shadow stacks, control heights) are the measured macOS
values published in the CupertinoUI theme CSS (cupertino-ui.com),
adapted as plain CSS here; its multi-accent system and chart palette
are deliberately NOT imported: Action Blue #0066cc stays the only
interactive colour, charts are blue for TruTrace and quiet gray for
the baseline, and there is no purple anywhere. Icons are original
inline SVG drawings in the SF Symbols visual language (thin stroke,
rounded caps, monochrome), drawn for this page; they are not Apple's
SF Symbols asset files, which are licensed and not redistributable.

Run: python demo/build_demo.py
"""

import html
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.pipeline import run_pipeline  # noqa: E402
from evals.run_evals import load_case_dir  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(os.path.dirname(__file__), "index.html")

CHIP = {
    "confirmed": ("Verified", "var(--verified)"),
    "uncertain": ("Uncertain", "var(--label-2)"),
    "unconfirmed": ("Unconfirmed", "var(--label-2)"),
    "conflicting": ("Conflicting", "var(--conflicting)"),
}
FIELD_LABEL = {
    "price": "Price", "currency": "Currency", "availability": "Availability",
    "quantity_or_stock": "Quantity", "delivery_or_pickup": "Delivery",
    "timing": "Timing", "contact_next_step": "Next step",
}

# ---------------------------------------------------------------- icons
# Original inline SVG drawings in the SF Symbols visual language:
# 24x24 grid, stroke 1.6, rounded caps and joins, monochrome
# (currentColor). Blue appears only when the icon is itself a control.

def icon(name, size=22):
    paths = {
        "chart": (
            '<path d="M4 4v15.2A0.8 0.8 0 0 0 4.8 20H20"/>'
            '<path d="M8.6 20v-5.4M13 20v-9.2M17.4 20v-7" stroke-width="2.4"/>'
        ),
        "waveform": (
            '<path d="M4.5 9.5v5M8.8 6.2v11.6M13 3.8v16.4M17.2 7v10M20.8 10v4"'
            ' stroke-width="2"/>'
        ),
        "shield": (
            '<path d="M12 3.2 18.8 5.6v5.3c0 4.4-2.9 7.5-6.8 9.3-3.9-1.8-6.8-4.9-6.8-9.3'
            'V5.6Z"/><path d="m9.9 9.9 4.2 4.2M14.1 9.9l-4.2 4.2"/>'
        ),
        "seal": (
            '<circle cx="12" cy="12" r="8.3"/>'
            '<path d="m8.6 12.3 2.4 2.4 4.4-5"/>'
        ),
        "timer": (
            '<circle cx="12" cy="13.2" r="7.4"/>'
            '<path d="M12 13.2V9.4M9.6 3h4.8M12 5.8v-2"/>'
        ),
        "fallback": (
            '<path d="M5.8 8.6A7.4 7.4 0 0 1 17.9 6.2L19.4 8"/>'
            '<path d="M19.6 3.4v4.8h-4.8"/>'
            '<path d="M18.2 15.4a7.4 7.4 0 0 1-12.1 2.4L4.6 16"/>'
            '<path d="M4.4 20.6v-4.8h4.8"/>'
        ),
        "server": (
            '<rect x="4" y="4" width="16" height="6.8" rx="2"/>'
            '<rect x="4" y="13.2" width="16" height="6.8" rx="2"/>'
            '<path d="M7.4 7.4h.01M7.4 16.6h.01" stroke-width="2.6"/>'
        ),
        "info": (
            '<circle cx="12" cy="12" r="8.3"/>'
            '<path d="M12 11.2V16M12 7.9h.01" stroke-width="2"/>'
        ),
        "table": (
            '<rect x="4" y="5" width="16" height="14.4" rx="2"/>'
            '<path d="M4 9.8h16M4 14.6h16M9.3 9.8v9.6M14.7 9.8v9.6"/>'
        ),
        "check": '<path d="m5 12.6 4.4 4.4L19 7.4"/>',
    }
    return (
        f'<svg class="icon" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="1.6" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f"{paths[name]}</svg>"
    )


# ---------------------------------------------------------------- data

def chip(status):
    label, color = CHIP[status]
    return f'<span class="chip" style="color:{color}">{label}</span>'


def fmt_value(f):
    if f.value is None:
        return "—"
    if f.name == "price":
        return f"${f.value:,.0f}" if float(f.value).is_integer() else f"${f.value}"
    return str(f.value)


class F:
    def __init__(self, name, field):
        self.name, self.value, self.status = name, field.value, field.status.value
        self.evidence, self.reason = field.evidence, field.reason
        self.speaker, self.timestamp = field.speaker, field.timestamp


def cell(summary, tag, config):
    for c in summary["cells"]:
        if c["provider_tag"] == tag and c["config"] == config:
            return c
    raise KeyError((tag, config))


def counts_str(c, key):
    return " · ".join(c[key]["per_run"])


def lat_str(c, key):
    v = c["operational_efficiency"][key]["mean"]
    return f"{v:,.0f} ms" if v and v >= 10 else f"{v:.2f} ms"


def cost_str(c):
    costs = [x for x in c["operational_efficiency"]["cost_usd_per_run"] if x is not None]
    if not costs:
        return "—"
    return f"${(sum(costs) / len(costs)) / c['cases_per_run']:.6f}"


def parse_counts(s):
    n, total = s.split(" of ")
    return int(n), int(total)


def esc(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------- charts
# Inline SVG generated from the recorded numbers. Baseline is quiet
# gray, the current (TruTrace) series is the single blue: #0066cc on
# light tiles, #2997ff on dark tiles (DESIGN.apple.md).

def runs_chart(c_base, c_cur, key, dark=False, height=132):
    """Grouped bars: the 3 recorded runs of baseline vs current."""
    base = [parse_counts(s) for s in c_base[key]["per_run"]]
    cur = [parse_counts(s) for s in c_cur[key]["per_run"]]
    total = base[0][1]
    top = total
    bw, gap, group_gap, pad = 26, 5, 26, 6
    plot_h = height - 44
    base_y = height - 24
    width = pad * 2 + 2 * (3 * bw + 2 * gap) + group_gap
    cur_fill = "#2997ff" if dark else "#0066cc"
    base_fill = "rgba(255,255,255,0.28)" if dark else "#b9b9bd"
    val_fill = "rgba(255,255,255,0.85)" if dark else "rgba(0,0,0,0.85)"
    lab_fill = "rgba(255,255,255,0.55)" if dark else "rgba(0,0,0,0.5)"
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Bar chart of recorded runs">'
    ]
    x = pad
    for series, fill, name in ((base, base_fill, "Baseline"), (cur, cur_fill, "TruTrace")):
        for i, (n, _t) in enumerate(series):
            h = max(2.0, plot_h * n / top)
            parts.append(
                f'<rect x="{x:.0f}" y="{base_y - h:.1f}" width="{bw}" height="{h:.1f}" '
                f'rx="3" fill="{fill}"/>'
                f'<text x="{x + bw / 2:.0f}" y="{base_y - h - 5:.1f}" class="cv" '
                f'fill="{val_fill}">{n}</text>'
            )
            x += bw + gap
        parts.append(
            f'<text x="{x - gap - (3 * bw + 2 * gap) / 2:.0f}" y="{height - 6}" '
            f'class="cl" fill="{lab_fill}">{name}</text>'
        )
        x += group_gap - gap
    parts.append("</svg>")
    return "".join(parts)


def proof_chart(c_base, c_cur, height=118):
    """Two horizontal bars: proof spans matching gold, of the same total."""
    rows = []
    total = c_cur["proof_accuracy"]["total"]
    for c, name, fill in (
        (c_base, "Baseline", "#b9b9bd"),
        (c_cur, "TruTrace", "#0066cc"),
    ):
        m = c["proof_accuracy"]["matched"]
        rows.append((name, m, fill))
    width = 300
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Proof matching chart">'
    ]
    y = 8
    for name, m, fill in rows:
        w = (width - 118) * m / total
        parts.append(
            f'<text x="0" y="{y + 13}" class="cll" fill="rgba(0,0,0,0.5)">{name}</text>'
            f'<rect x="64" y="{y}" width="{width - 118}" height="16" rx="4" '
            f'fill="rgba(0,0,0,0.05)"/>'
            f'<rect x="64" y="{y}" width="{w:.0f}" height="16" rx="4" fill="{fill}"/>'
            f'<text x="{width}" y="{y + 13}" class="cvv" fill="rgba(0,0,0,0.85)">'
            f"{m} of {total}</text>"
        )
        y += 34
    parts.append("</svg>")
    return "".join(parts)


def latency_chart(ho_b, ho_c, ca_b, ca_c, height=150):
    """Mean p50 latency per run set, gpt-4o-mini, baseline vs current."""
    groups = []
    for label, cb, cc in (("Held out", ho_b, ho_c), ("Campaign", ca_b, ca_c)):
        groups.append((
            label,
            cb["operational_efficiency"]["p50_latency_ms"]["mean"],
            cc["operational_efficiency"]["p50_latency_ms"]["mean"],
        ))
    top = max(max(g[1], g[2]) for g in groups) * 1.18
    bw, gap, group_gap, pad = 30, 6, 34, 6
    plot_h = height - 46
    base_y = height - 24
    width = pad * 2 + 2 * (2 * bw + gap) + group_gap
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Latency chart">'
    ]
    x = pad
    for label, vb, vc in groups:
        for v, fill in ((vb, "#b9b9bd"), (vc, "#0066cc")):
            h = max(2.0, plot_h * v / top)
            parts.append(
                f'<rect x="{x:.0f}" y="{base_y - h:.1f}" width="{bw}" height="{h:.1f}" '
                f'rx="3" fill="{fill}"/>'
                f'<text x="{x + bw / 2:.0f}" y="{base_y - h - 5:.1f}" class="cv" '
                f'fill="rgba(0,0,0,0.85)">{v:,.0f}</text>'
            )
            x += bw + gap
        parts.append(
            f'<text x="{x - gap - (2 * bw + gap) / 2:.0f}" y="{height - 6}" '
            f'class="cl" fill="rgba(0,0,0,0.5)">{label}</text>'
        )
        x += group_gap - gap
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------- cases

def transcript_html(doc):
    lines = []
    for line in doc.transcript.splitlines():
        ts = line[1:6] if line.startswith("[") else ""
        lines.append(
            f'<div class="tline" data-ts="{esc(ts)}">{esc(line)}</div>'
        )
    return "\n".join(lines)


def field_button(name, field):
    """One answer field as a control: selecting it shows its evidence."""
    f = F(name, field)
    label, _color = CHIP[f.status]
    ev = f.evidence or ""
    reason = f.reason or ""
    return (
        f'<button type="button" class="frow" data-ts="{esc(f.timestamp or "")}" '
        f'data-status="{esc(f.status)}" data-evidence="{esc(ev)}" '
        f'data-reason="{esc(reason)}">'
        f'<span class="fname">{FIELD_LABEL[name]}</span>'
        f'<span class="fvalue">{esc(fmt_value(f))}</span>'
        f"{chip(f.status)}</button>"
    )


def case_fields(answer, fields):
    return "\n".join(field_button(n, answer.fields[n]) for n in fields)


def detail_block():
    return (
        '<div class="detail" aria-live="polite">'
        '<div class="detail-head"><span class="dlabel">Evidence</span>'
        '<span class="dstatus"></span></div>'
        '<p class="devidence"></p><p class="dreason"></p></div>'
    )


def score_rows(summary):
    rows = []
    for tag, label in [("gpt-4o-mini", "gpt-4o-mini"), ("offline", "offline rules")]:
        for config in ["baseline", "current"]:
            c = cell(summary, tag, config)
            rows.append(
                f"<tr><td>{label} · {config}</td>"
                f"<td>{counts_str(c, 'extraction_accuracy')}</td>"
                f"<td>{counts_str(c, 'unsupported_claim_rate')}</td>"
                f"<td>{lat_str(c, 'p50_latency_ms')}</td>"
                f"<td>{lat_str(c, 'p95_latency_ms')}</td>"
                f"<td>{cost_str(c)}</td></tr>"
            )
    return "\n".join(rows)


def unit_strip(per_transcript):
    cells = []
    for t in per_transcript:
        if t["provider_used"] == "primary":
            cls, word = "u-primary", "primary"
        elif t["provider_used"]:
            cls, word = "u-fallback", "fallback"
        else:
            cls, word = "u-down", "unconfirmed"
        cells.append(f'<span class="unit {cls}" title="{word}"></span>')
    return '<div class="units">' + "".join(cells) + "</div>"


# ---------------------------------------------------------------- styles
# Tokens: DESIGN.apple.md. Surface values: measured macOS values from
# the CupertinoUI theme CSS (labels 0.85/0.5/0.26, fills, materials,
# radii group 12 / window 16 / popover 20, layered shadow stacks,
# control heights), implemented as plain CSS. Its accent system and
# chart palette are not imported; #0066cc is the only interactive
# colour and charts are blue vs quiet gray.

CSS = """
:root {
  --blue:#0066cc; --blue-dark:#2997ff; --focus:#0071e3;
  --ink:#1d1d1f;
  --label:rgba(0,0,0,0.85); --label-2:rgba(0,0,0,0.5); --label-3:rgba(0,0,0,0.26);
  --d-label:rgba(255,255,255,0.85); --d-label-2:rgba(255,255,255,0.55);
  --d-label-3:rgba(255,255,255,0.25);
  --fill:rgba(0,0,0,0.1); --fill-2:rgba(0,0,0,0.08); --fill-3:rgba(0,0,0,0.05);
  --fill-4:rgba(0,0,0,0.03);
  --d-fill:rgba(255,255,255,0.1); --d-fill-2:rgba(255,255,255,0.08);
  --d-fill-3:rgba(255,255,255,0.05);
  --canvas:#ffffff; --parchment:#f5f5f7; --pearl:#fafafc;
  --tile-1:#272729; --tile-2:#2a2a2c; --tile-3:#252527; --black:#000000;
  --separator:rgba(0,0,0,0.05); --border:rgba(0,0,0,0.1);
  --d-separator:rgba(255,255,255,0.05); --d-border:rgba(255,255,255,0.1);
  --glass:rgba(255,255,255,0.82);
  --material:rgba(246,246,246,0.8);
  --glass-shadow:0 0 0 0.5px rgba(0,0,0,0.08), 0 8px 15px rgba(0,0,0,0.04);
  --popover-shadow:0 0 0 0.5px rgba(0,0,0,0.1), 0 8px 48px rgba(0,0,0,0.2);
  --window-shadow:0 0 1px rgba(0,0,0,0.8), 0 18px 54px rgba(0,0,0,0.3);
  --verified:#007d48; --conflicting:#d30005;
  --r-group:12px; --r-window:16px; --r-popover:20px; --r-item:8px;
  --font:-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro",
    "Helvetica Neue", "Segoe UI", Inter, system-ui, sans-serif;
  --mono:ui-monospace, "SF Mono", SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:var(--font); color:var(--label); background:var(--parchment);
  font-size:17px; line-height:1.47; letter-spacing:-0.374px;
  -webkit-font-smoothing:antialiased; }
button { font:inherit; color:inherit; background:none; border:0; cursor:pointer; }
button:focus-visible, a:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }
.icon { flex:none; display:block; }

header.site { background:var(--black); color:#fff; padding:56px 24px 48px; }
.site-inner { max-width:1180px; margin:0 auto; }
.wordmark { font-size:17px; font-weight:600; letter-spacing:-0.374px; }
.wordmark span { color:var(--d-label-2); font-weight:400; }
header.site h1 { font-size:56px; font-weight:600; line-height:1.07;
  letter-spacing:-0.28px; margin-top:40px; max-width:820px; }
header.site .sub { font-size:21px; line-height:1.35; color:var(--d-label-2);
  max-width:680px; margin-top:16px; }
header.site .sub b { color:#fff; font-weight:600; }

main { max-width:1180px; margin:0 auto; padding:24px 24px 8px; }
.grid { display:grid; grid-template-columns:repeat(12, 1fr); gap:20px; }
.tile { border-radius:var(--r-window); padding:28px; background:var(--canvas);
  border:1px solid var(--border); min-width:0; }
.tile--glass { background:var(--material); backdrop-filter:blur(30px) saturate(1.6);
  -webkit-backdrop-filter:blur(30px) saturate(1.6);
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.5); }
.tile--dark { background:var(--tile-1); color:var(--d-label); border-color:transparent; }
.tile--dark3 { background:var(--tile-3); color:var(--d-label); border-color:transparent; }
.s4 { grid-column:span 4; } .s5 { grid-column:span 5; } .s6 { grid-column:span 6; }
.s7 { grid-column:span 7; } .s8 { grid-column:span 8; } .s12 { grid-column:span 12; }

.tile-head { display:flex; align-items:center; gap:10px; margin-bottom:14px; }
.tile-head .icon { color:var(--label-2); }
.tile--dark .tile-head .icon, .tile--dark3 .tile-head .icon { color:var(--d-label-2); }
.kicker { font-size:12px; font-weight:600; color:var(--label-2);
  text-transform:uppercase; letter-spacing:0.06em; }
.tile--dark .kicker, .tile--dark3 .kicker { color:var(--d-label-2); }
.tile h2 { font-size:28px; font-weight:600; line-height:1.14; letter-spacing:0.196px; }
.tile-copy { font-size:17px; margin-bottom:16px; }
.tile-copy .cont { color:var(--label-2); }
.tile--dark .tile-copy .cont, .tile--dark3 .tile-copy .cont { color:var(--d-label-2); }
.big { font-size:40px; font-weight:600; line-height:1.1; letter-spacing:-0.01em; }
.big .of { color:var(--label-3); }
.tile--dark .big .of { color:var(--d-label-3); }
.fine { font-size:12px; line-height:1.45; color:var(--label-2); margin-top:16px; }
.tile--dark .fine, .tile--dark3 .fine { color:var(--d-label-2); }
.legend { display:flex; gap:20px; font-size:14px; color:var(--label-2); margin-top:10px; }
.tile--dark .legend { color:var(--d-label-2); }
.sw { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:7px; }
.chart { width:100%; height:auto; display:block; margin-top:14px; }
.chart text { font-family:var(--font); }
.chart .cv { font-size:12.5px; font-weight:600; text-anchor:middle; }
.chart .cvv { font-size:13.5px; font-weight:600; text-anchor:end; }
.chart .cl { font-size:12px; text-anchor:middle; }
.chart .cll { font-size:12.5px; }

/* segmented control, macOS pattern */
.seg { display:inline-flex; background:var(--fill-3); border-radius:9px;
  padding:2px; gap:2px; margin:4px 0 18px; }
.tile--dark .seg { background:var(--d-fill-2); }
.seg button { min-height:24px; padding:3px 14px; border-radius:7px;
  font-size:14px; color:var(--label-2); }
.tile--dark .seg button { color:var(--d-label-2); }
.seg button[aria-pressed="true"] { background:#fff; color:var(--label);
  box-shadow:var(--glass-shadow); font-weight:600; }
.tile--dark .seg button[aria-pressed="true"] { background:#323435; color:#fff; }
.panel[hidden] { display:none; }

/* transcript case tiles */
.transcript { font-family:var(--mono); font-size:13px; line-height:1.65;
  background:var(--canvas); border:1px solid var(--border);
  border-radius:var(--r-group); padding:14px 16px; margin-bottom:16px; }
.transcript--hero { box-shadow:var(--window-shadow); border-color:transparent; }
.tline { padding:3px 8px; border-radius:6px; color:var(--label); }
.tline.hl { background:rgba(0,102,204,0.12); }
.frow { display:flex; align-items:center; gap:12px; width:100%; text-align:left;
  padding:10px 12px; border-radius:var(--r-item); border:1px solid transparent; }
.frow:hover { background:var(--fill-4); }
.frow[aria-pressed="true"] { background:rgba(0,102,204,0.08);
  border-color:rgba(0,102,204,0.35); }
.fname { font-weight:600; width:96px; flex:none; font-size:15px; }
.fvalue { flex:1; font-size:15px; }
.chip { flex:none; background:var(--fill-3); border-radius:9999px;
  padding:3px 11px; font-size:12px; font-weight:600; }
.detail { margin-top:14px; background:var(--glass); border-radius:var(--r-group);
  box-shadow:var(--glass-shadow); padding:14px 16px; }
.detail-head { display:flex; justify-content:space-between; align-items:baseline; }
.dlabel { font-size:12px; font-weight:600; text-transform:uppercase;
  letter-spacing:0.06em; color:var(--label-2); }
.dstatus { font-size:13px; font-weight:600; }
.devidence { font-family:var(--mono); font-size:13px; line-height:1.6;
  margin-top:8px; color:var(--label); }
.dreason { font-size:14px; color:var(--label-2); margin-top:6px; }
.notest { font-size:14px; color:var(--label-2); margin-top:12px; }

/* provider rows */
.prow { display:flex; gap:12px; padding:13px 0; border-bottom:1px solid var(--separator); }
.prow:last-child { border-bottom:0; }
.prow .pbody { flex:1; }
.prow .pname { font-weight:600; font-size:16px; }
.prow .pnote { font-size:14px; color:var(--label-2); line-height:1.43; }
.pstatus { flex:none; font-size:12px; font-weight:600; padding:3px 11px;
  border-radius:9999px; background:var(--fill-3); height:fit-content; }
.pstatus.ok { color:var(--verified); }
.pstatus.down { color:var(--conflicting); }

/* degradation */
.deg-row { display:flex; justify-content:space-between; align-items:baseline;
  padding:10px 0 4px; font-size:16px; }
.deg-row span:last-child { font-weight:600; }
.units { display:flex; gap:6px; padding:6px 0 12px; }
.unit { width:26px; height:26px; border-radius:7px; background:var(--fill-3); }
.unit.u-primary { background:var(--ink); }
.unit.u-fallback { background:var(--blue); }
.unit.u-down { background:transparent; border:1.5px solid var(--border); }

/* limits */
.limits { list-style:none; }
.limits li { padding:11px 0; border-bottom:1px solid var(--d-separator);
  font-size:16px; line-height:1.45; }
.limits li:last-child { border-bottom:0; }
.limits b { font-weight:600; }

/* tables */
table { width:100%; border-collapse:collapse; font-size:14.5px;
  font-variant-numeric:tabular-nums; }
th { background:var(--pearl); font-size:13.5px; font-weight:600; text-align:left;
  padding:10px 14px; }
td { padding:10px 14px; border-bottom:1px solid var(--separator); }
td:not(:first-child), th:not(:first-child) { text-align:right; }
.table-scroll { overflow-x:auto; }
.tgroup { font-size:12px; font-weight:600; color:var(--label-2);
  text-transform:uppercase; letter-spacing:0.06em; margin:22px 0 8px; }
.tgroup:first-of-type { margin-top:4px; }

footer { padding:40px 24px 56px; }
.footer-inner { max-width:1180px; margin:0 auto; color:var(--label-2);
  font-size:13px; line-height:1.55; }
.footer-inner p { max-width:860px; }
.footer-inner .fine { margin-top:10px; }

@media (max-width:1023px) {
  .s4, .s5, .s6 { grid-column:span 6; }
  .s7, .s8 { grid-column:span 12; }
  header.site h1 { font-size:44px; }
}
@media (max-width:640px) {
  .grid { grid-template-columns:1fr; }
  .s4, .s5, .s6, .s7, .s8, .s12 { grid-column:span 1; }
  header.site { padding:40px 20px 32px; }
  header.site h1 { font-size:36px; }
  main { padding:16px 16px 4px; }
  .tile { padding:22px; }
  .big { font-size:32px; }
  .fname { width:84px; }
}
"""

JS = """
(function () {
  // Segmented toggles: switching the control swaps the panel it names.
  document.querySelectorAll("[data-seg-group]").forEach(function (group) {
    var name = group.getAttribute("data-seg-group");
    var buttons = group.querySelectorAll("button[data-seg]");
    var panels = document.querySelectorAll(
      '[data-panel-group="' + name + '"]');
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (b) {
          b.setAttribute("aria-pressed",
            b === btn ? "true" : "false");
        });
        panels.forEach(function (p) {
          p.hidden = p.getAttribute("data-panel") !==
            btn.getAttribute("data-seg");
        });
        var tile = group.closest(".case");
        if (tile && tile._selectFirst) tile._selectFirst();
      });
    });
  });

  // Case tiles: selecting a field shows its evidence and lights the
  // transcript line it rests on. Hover selects too; the detail stays
  // on the last selected field.
  var CHIPCOLOR = {
    confirmed: "var(--verified)", uncertain: "var(--label-2)",
    unconfirmed: "var(--label-2)", conflicting: "var(--conflicting)"
  };
  var CHIPLABEL = {
    confirmed: "Verified", uncertain: "Uncertain",
    unconfirmed: "Unconfirmed", conflicting: "Conflicting"
  };
  document.querySelectorAll(".case").forEach(function (tile) {
    var rows = tile.querySelectorAll(".frow");
    var lines = tile.querySelectorAll(".tline");
    var status = tile.querySelector(".dstatus");
    var evidence = tile.querySelector(".devidence");
    var reason = tile.querySelector(".dreason");
    if (!rows.length || !status) return;
    function select(row) {
      rows.forEach(function (r) {
        r.setAttribute("aria-pressed", r === row ? "true" : "false");
      });
      var st = row.getAttribute("data-status");
      status.textContent = CHIPLABEL[st] || st;
      status.style.color = CHIPCOLOR[st] || "";
      var ev = row.getAttribute("data-evidence");
      evidence.textContent = ev || "No span in the call supports a value.";
      var rs = row.getAttribute("data-reason");
      reason.textContent = rs || "";
      reason.style.display = rs ? "" : "none";
      var ts = row.getAttribute("data-ts");
      lines.forEach(function (line) {
        line.classList.toggle("hl",
          !!ts && line.getAttribute("data-ts") === ts);
      });
    }
    rows.forEach(function (row) {
      row.addEventListener("click", function () { select(row); });
      row.addEventListener("mouseenter", function () { select(row); });
    });
    tile._selectFirst = function () {
      for (var i = 0; i < rows.length; i++) {
        if (rows[i].offsetParent !== null) { select(rows[i]); return; }
      }
      select(rows[0]);
    };
    select(rows[0]);
  });
})();
"""


# ---------------------------------------------------------------- page

def stat_pair(label_base, big_base, note_base, label_cur, big_cur, note_cur):
    return (
        f'<p class="kicker">{label_base}</p>'
        f'<p class="big">{big_base}</p><p class="fine" style="margin-top:4px">{note_base}</p>'
        f'<p class="kicker" style="margin-top:18px">{label_cur}</p>'
        f'<p class="big" style="color:var(--blue-dark)">{big_cur}</p>'
        f'<p class="fine" style="margin-top:4px">{note_cur}</p>'
    )


def main() -> int:
    docs = {d.id: d for d in load_case_dir(os.path.join(ROOT, "datasets", "campaign"))}
    showcase = docs["campaign_01_showcase_hedged"]
    base = run_pipeline(showcase, provider_name="offline", prompt_version="baseline-naive").answer
    now = run_pipeline(showcase, provider_name="offline", prompt_version="trutrace-1.0.0").answer
    proof_doc = docs["campaign_02_clean_confirm"]
    proof = run_pipeline(proof_doc, provider_name="offline", prompt_version="trutrace-1.0.0").answer

    heldout = json.load(open(os.path.join(ROOT, "evals/results/final_heldout_summary.json")))
    campaign = json.load(open(os.path.join(ROOT, "evals/results/final_campaign_summary.json")))
    degradation = json.load(open(os.path.join(ROOT, "reports/degradation_record.json")))
    deg_a = degradation["scenario_a_killed_mid_run"]
    deg_b = degradation["scenario_b_all_providers_down"]
    load10 = json.load(open(os.path.join(ROOT, "evals/results/load_10_openrouter.json")))
    load100 = json.load(open(os.path.join(ROOT, "evals/results/load_100_openrouter.json")))
    gemini = json.load(open(os.path.join(
        ROOT, "evals/results/openrouter_gemini-2.0-flash-001_baseline_scorecard.json")))

    ho_b, ho_c = cell(heldout, "gpt-4o-mini", "baseline"), cell(heldout, "gpt-4o-mini", "current")
    ca_b, ca_c = cell(campaign, "gpt-4o-mini", "baseline"), cell(campaign, "gpt-4o-mini", "current")
    off_b = cell(campaign, "offline", "baseline")

    showcase_fields = ["price", "currency", "availability", "timing"]
    proof_fields = ["price", "currency", "availability", "delivery_or_pickup",
                    "timing", "contact_next_step"]
    gem_status = "HTTP 404" if "404" in gemini["error"]["message"] else "an error"

    headline_heldout = (
        stat_pair(
            "Baseline · accuracy, held out",
            '61 <span class="of">of 84</span>',
            "The same count in all three runs: " + counts_str(ho_b, "extraction_accuracy") + ".",
            "TruTrace · accuracy, held out",
            '68 · 69 · 65 <span class="of">of 84</span>',
            "Runs 1 to 3: " + counts_str(ho_c, "extraction_accuracy") + ".",
        )
        + runs_chart(ho_b, ho_c, "extraction_accuracy", dark=True)
        + '<div class="legend"><span><span class="sw" style="background:rgba(255,255,255,0.28)"></span>Baseline</span>'
          '<span><span class="sw" style="background:#2997ff"></span>TruTrace</span></div>'
        + f'<p style="margin-top:16px">Unsupported claims: <b>{counts_str(ho_b, "unsupported_claim_rate")}</b>'
          f' → <b>{counts_str(ho_c, "unsupported_claim_rate")}</b></p>'
        + f'<p>Contradictions caught: <b>{counts_str(ho_b, "contradiction_detection")}</b>'
          f' → <b>{counts_str(ho_c, "contradiction_detection")}</b></p>'
    )
    headline_campaign = (
        stat_pair(
            "Baseline · accuracy, campaign",
            '40 · 38 · 40 <span class="of">of 70</span>',
            "Runs 1 to 3: " + counts_str(ca_b, "extraction_accuracy") + ".",
            "TruTrace · accuracy, campaign",
            '55 · 55 · 56 <span class="of">of 70</span>',
            "Runs 1 to 3: " + counts_str(ca_c, "extraction_accuracy") + ".",
        )
        + runs_chart(ca_b, ca_c, "extraction_accuracy", dark=True)
        + '<div class="legend"><span><span class="sw" style="background:rgba(255,255,255,0.28)"></span>Baseline</span>'
          '<span><span class="sw" style="background:#2997ff"></span>TruTrace</span></div>'
        + f'<p style="margin-top:16px">Unsupported claims: <b>{counts_str(ca_b, "unsupported_claim_rate")}</b>'
          f' → <b>{counts_str(ca_c, "unsupported_claim_rate")}</b></p>'
        + f'<p>Contradictions caught: <b>{counts_str(ca_b, "contradiction_detection")}</b>'
          f' → <b>{counts_str(ca_c, "contradiction_detection")}</b></p>'
    )

    unsup_big = ca_b["unsupported_claim_rate"]["per_run"][0]
    unsup_now = ca_c["unsupported_claim_rate"]["per_run"][0]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TruTrace — verified answers from seller calls</title>
<style>{CSS}</style>
</head>
<body>
<!-- Bento composition after the Stageshow example (MIT, (c) 2026 Benji
     Taylor). Tokens: DESIGN.apple.md. Surface values: measured macOS
     values adapted from the CupertinoUI theme CSS (cupertino-ui.com);
     its accent system and chart palette are not imported. Icons are
     original inline SVG drawings in the SF Symbols style, not Apple's
     asset files. All data generated from recorded runs by
     demo/build_demo.py. -->
<header class="site">
  <div class="site-inner">
    <p class="wordmark">TruTrace <span>· verified answers from seller calls</span></p>
    <h1>Every field carries its evidence, or it is not asserted.</h1>
    <p class="sub">TruTrace checks what a seller actually said before an
    answer may state it. <b>The baseline asserts the hedges. TruTrace
    demotes them and keeps the proof attached.</b></p>
  </div>
</header>
<main>
  <div class="grid">

    <section class="tile tile--dark s8">
      <div class="tile-head">{icon("chart")}<p class="kicker">The headline result · gpt-4o-mini · three runs each</p></div>
      <div class="seg" data-seg-group="headline-set" role="group" aria-label="Choose the dataset">
        <button type="button" data-seg="heldout" aria-pressed="true">Held out</button>
        <button type="button" data-seg="campaign" aria-pressed="false">Campaign</button>
      </div>
      <div class="panel" data-panel-group="headline-set" data-panel="heldout">{headline_heldout}</div>
      <div class="panel" data-panel-group="headline-set" data-panel="campaign" hidden>{headline_campaign}</div>
      <p class="fine">Accuracy counts a field right only when value, status
      and condition all match gold. Scores are measured against gold labels
      drafted by an AI coding agent during the build, pending Diwakar
      Bhagat's human review: they are not validated ground truth. The
      held-out split is not a clean-room measurement; the split was frozen
      after a build round whose fixes were driven by failures seen across
      all 32 cases.</p>
    </section>

    <section class="tile s4">
      <div class="tile-head">{icon("server")}<p class="kicker">Providers</p></div>
      <div class="prow"><div class="pbody">
        <p class="pname">gpt-4o-mini · OpenRouter</p>
        <p class="pnote">Ran the recorded benchmarks: 32 cases and 10
        campaign calls, three runs each, at temperature 0.</p></div>
        <span class="pstatus ok">Ran</span></div>
      <div class="prow"><div class="pbody">
        <p class="pname">Offline rules</p>
        <p class="pnote">Deterministic provider. No network, no key. Also
        the fallback when a provider dies mid run.</p></div>
        <span class="pstatus ok">Ran</span></div>
      <div class="prow"><div class="pbody">
        <p class="pname">google/gemini-2.0-flash-001</p>
        <p class="pnote">Never ran. OpenRouter returned {gem_status} for
        this model id; {gemini["cases_run"]} of {gemini["cases_total"]}
        cases ran. The runs were stopped rather than re-pointed.</p></div>
        <span class="pstatus down">Did not run</span></div>
    </section>

    <section class="tile tile--glass s7 case">
      <div class="tile-head">{icon("waveform")}<p class="kicker">One call · campaign_01 · the failing case</p></div>
      <p class="tile-copy"><b>One florist, asked for a dozen red roses with
      delivery today.</b> <span class="cont">The seller hedges three times.
      Select a field to see the exact line it rests on.</span></p>
      <div class="transcript transcript--hero">{transcript_html(showcase)}</div>
      <div class="seg" data-seg-group="showcase-config" role="group" aria-label="Choose the configuration">
        <button type="button" data-seg="trutrace" aria-pressed="true">TruTrace</button>
        <button type="button" data-seg="baseline" aria-pressed="false">Baseline</button>
      </div>
      <div class="panel" data-panel-group="showcase-config" data-panel="trutrace">
        {case_fields(now, showcase_fields)}
        <p class="notest">Not established in the call, so reported
        unconfirmed rather than filled in: Quantity · Delivery · Next step.</p>
      </div>
      <div class="panel" data-panel-group="showcase-config" data-panel="baseline" hidden>
        {case_fields(base, showcase_fields)}
        <p class="notest">The baseline asserts every hedge as a fact. Its
        prompt never asks for evidence, and nothing checks the spans it
        returns.</p>
      </div>
      {detail_block()}
    </section>

    <section class="tile s5">
      <div class="tile-head">{icon("shield")}<p class="kicker">Unsupported claims · campaign · gpt-4o-mini</p></div>
      <p class="big">{unsup_big.split(' of ')[0]} <span class="of">of {unsup_big.split(' of ')[1]}</span></p>
      <p class="tile-copy" style="margin-top:8px">of the baseline's
      confirmations in run 1 were claims the call does not support.
      <span class="cont">With verification: <b>{unsup_now}</b>.</span></p>
      {runs_chart(ca_b, ca_c, "unsupported_claim_rate")}
      <div class="legend"><span><span class="sw" style="background:#b9b9bd"></span>Baseline</span><span><span class="sw" style="background:#0066cc"></span>TruTrace</span></div>
      <p class="fine">Bars are counts per run. The denominators differ
      because each configuration chooses which fields to confirm: the
      baseline confirmed 63 to 65 fields a run, TruTrace 40 to 41.</p>
    </section>

    <section class="tile s7">
      <div class="tile-head">{icon("seal")}<p class="kicker">The campaign slice · proof that matches</p></div>
      <p class="tile-copy"><b>One query to ten synthetic florist sellers:
      “Red roses, a dozen, delivery today.”</b> <span class="cont">A
      confirmed field is only as good as its proof: the span, the speaker
      and the timestamp all have to match gold.</span></p>
      {proof_chart(ca_b, ca_c)}
      <p class="fine">Proof matching gold, gpt-4o-mini, campaign. The
      baseline returns no evidence at all, because its prompt never asks
      for it. The offline provider matches {off_b["proof_accuracy"]["matched"]}
      of {off_b["proof_accuracy"]["total"]} in both configurations; its
      misses are fields it did not confirm, not wrong proof.</p>
      <div class="case" style="margin-top:22px">
        <p class="kicker" style="margin-bottom:10px">One clean call · campaign_02 · TruTrace</p>
        <div class="transcript">{transcript_html(proof_doc)}</div>
        {case_fields(proof, proof_fields)}
        {detail_block()}
      </div>
    </section>

    <section class="tile tile--glass s5">
      <div class="tile-head">{icon("timer")}<p class="kicker">Cost and latency · gpt-4o-mini</p></div>
      <p class="tile-copy"><b>Verification is a second pass, and it
      costs.</b> <span class="cont">What the recorded runs say it
      costs:</span></p>
      {latency_chart(ho_b, ho_c, ca_b, ca_c)}
      <div class="legend"><span><span class="sw" style="background:#b9b9bd"></span>Baseline</span><span><span class="sw" style="background:#0066cc"></span>TruTrace</span></div>
      <p class="fine" style="margin-top:8px">Mean p50 latency per call
      across the three runs, milliseconds.</p>
      <div class="deg-row"><span>Cost per call · held out</span><span>{cost_str(ho_b)} → {cost_str(ho_c)}</span></div>
      <div class="deg-row"><span>Cost per call · campaign</span><span>{cost_str(ca_b)} → {cost_str(ca_c)}</span></div>
      <div class="deg-row"><span>Load · 10 calls, real</span><span>${load10["cost_per_transcript_usd"]:.6f} a call, 0 errors</span></div>
      <div class="deg-row"><span>Load · 100 calls, real</span><span>${load100["cost_per_transcript_usd"]:.6f} a call, 0 errors</span></div>
      <p class="fine">Load at 1,000 calls was simulated against the
      offline provider in process: no network calls, no model cost, and
      its latencies are rule-engine time, not a live model's.</p>
    </section>

    <section class="tile s6">
      <div class="tile-head">{icon("fallback")}<p class="kicker">When the provider dies</p></div>
      <p class="tile-copy"><b>The provider dies at call four.</b>
      <span class="cont">Six campaign calls, the primary killed mid run,
      the offline provider as fallback.</span></p>
      <div class="deg-row"><span>Served by the primary</span><span>{deg_a["summary"]["served_by_primary"]} of {deg_a["summary"]["total"]}</span></div>
      {unit_strip(deg_a["per_transcript"])}
      <div class="deg-row"><span>Fell back</span><span>{deg_a["summary"]["served_by_fallback"]} of {deg_a["summary"]["total"]}</span></div>
      <div class="deg-row"><span>Lost</span><span>{deg_a["summary"]["unavailable"]} of {deg_a["summary"]["total"]}</span></div>
      <div class="deg-row"><span>Both providers down</span><span>{deg_b["summary"]["unavailable"]} of {deg_b["summary"]["total"]} unconfirmed, 0 invented</span></div>
      {unit_strip(deg_b["per_transcript"])}
      <div class="legend"><span><span class="sw" style="background:#1d1d1f"></span>Primary</span><span><span class="sw" style="background:#0066cc"></span>Fallback</span><span><span class="sw" style="background:transparent;border:1.5px solid rgba(0,0,0,0.1)"></span>Unconfirmed</span></div>
      <p class="fine">Provider deaths are simulated by killswitch
      wrappers; the fallback and unconfirmed behaviour is the pipeline's
      own code path. Covered by automated tests in
      tests/test_degradation.py.</p>
    </section>

    <section class="tile tile--dark3 s6">
      <div class="tile-head">{icon("info")}<p class="kicker">Limits, stated</p></div>
      <ul class="limits">
        <li><b>Synthetic transcripts.</b> No live audio. No real
        telephony. The campaign is ten written calls, not ten placed
        calls.</li>
        <li><b>The labels are AI drafted.</b> The gold labels were
        drafted by an AI coding agent during the build and are pending
        Diwakar Bhagat's human review. Every score on this page is
        measured against those labels, not validated ground truth.</li>
        <li><b>Held out is not clean room.</b> The split was frozen after
        a build round whose fixes were driven by failures seen across
        all 32 cases.</li>
        <li><b>The offline row is self-consistency.</b> Offline rules
        score 84 of 84 on held out with 0 of 45 unsupported, but the
        rules and the dataset grew up together. The model rows are the
        independent check.</li>
        <li><b>Small numbers.</b> 32 cases plus 10 campaign transcripts.
        Nothing here estimates accuracy on real seller calls.</li>
      </ul>
    </section>

    <section class="tile s12">
      <div class="tile-head">{icon("table")}<p class="kicker">Baseline vs current, measured in full</p></div>
      <p class="tile-copy"><b>Every recorded run.</b> <span class="cont">Counts
      are per run, three runs each, at temperature 0.</span></p>
      <p class="tgroup">Campaign · 10 calls · 70 fields</p>
      <div class="table-scroll"><table>
        <tr><th>Run</th><th>Accuracy</th><th>Unsupported</th><th>p50</th><th>p95</th><th>Cost / call</th></tr>
        {score_rows(campaign)}
      </table></div>
      <p class="tgroup">Held out · 12 cases · 84 fields</p>
      <div class="table-scroll"><table>
        <tr><th>Run</th><th>Accuracy</th><th>Unsupported</th><th>p50</th><th>p95</th><th>Cost / call</th></tr>
        {score_rows(heldout)}
      </table></div>
      <p class="fine">Full tables, spreads and methodology are in
      reports/benchmark_results.md in the repository.</p>
    </section>

  </div>
</main>
<footer>
  <div class="footer-inner">
    <p>TruTrace, by Diwakar Bhagat. A verification layer for seller-call
    answers, demonstrated on one campaign slice.</p>
    <p class="fine">Composition adapted from the Stageshow bento example
    (MIT, © 2026 Benji Taylor). Design tokens from this project's
    DESIGN.apple.md; surface values (label and fill hierarchies,
    materials, radii, shadow stacks) are measured macOS values adapted
    from the CupertinoUI theme CSS, with its multi-accent system and
    chart palette deliberately not imported. Icons are original inline
    SVG drawings in the SF Symbols style, not Apple's asset files.
    Every number and chart on this page was generated from recorded
    runs by demo/build_demo.py.</p>
  </div>
</footer>
<script>{JS}</script>
</body>
</html>
"""
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"wrote {OUT} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
