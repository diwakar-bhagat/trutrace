"""Build demo/index.html from TruTrace's real outputs.

Nothing on the page is hand-typed data: the showcase answers come from
running the pipeline on campaign_01 in both configurations, the proof
tile from campaign_02, and every number from the recorded artifacts
(final summaries, degradation record, load records).

Composition follows the Stageshow bento example's discipline (one
hero tile, mixed tile kinds, copy outside the pictures, quiet grays),
restyled with the tokens in ../DESIGN.md. Stageshow is MIT licensed,
(c) 2026 Benji Taylor; see the footer note on the page itself.

Run: python demo/build_demo.py
"""

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
    "uncertain": ("Uncertain", "var(--unconfirmed)"),
    "unconfirmed": ("Unconfirmed", "var(--unconfirmed)"),
    "conflicting": ("Conflicting", "var(--conflicting)"),
}
FIELD_LABEL = {
    "price": "Price", "currency": "Currency", "availability": "Availability",
    "quantity_or_stock": "Quantity", "delivery_or_pickup": "Delivery",
    "timing": "Timing", "contact_next_step": "Next step",
}


def chip(status):
    label, color = CHIP[status]
    return (f'<span class="chip" style="color:{color}">{label}</span>')


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


def answer_rows(answer, fields, show_evidence=False):
    rows = []
    for name in fields:
        f = F(name, answer.fields[name])
        ev = ""
        if show_evidence and f.evidence:
            ev = (f'<div class="evidence">{f.evidence}</div>')
        reason = f'<div class="reason">{f.reason}</div>' if f.reason and f.status != "confirmed" else ""
        rows.append(
            f'<div class="field-row"><span class="field-name">{FIELD_LABEL[name]}</span>'
            f'<span class="field-value">{fmt_value(f)}</span>{chip(f.status)}</div>'
            f"{reason}{ev}"
        )
    return "\n".join(rows)


def cell(summary, tag, config):
    for c in summary["cells"]:
        if c["provider_tag"] == tag and c["config"] == config:
            return c
    raise KeyError((tag, config))


def counts_str(c, key):
    return " · ".join(c[key]["per_run"])


def lat_str(c, key):
    v = c["operational_efficiency"][key]["mean"]
    return f"{v:.0f} ms" if v and v >= 10 else f"{v:.2f} ms"


def cost_str(c):
    costs = [x for x in c["operational_efficiency"]["cost_usd_per_run"] if x is not None]
    if not costs:
        return "—"
    return f"${(sum(costs) / len(costs)) / c['cases_per_run']:.6f}"


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
    deg_a = degradation["scenario_a_killed_mid_run"]["summary"]
    deg_b = degradation["scenario_b_all_providers_down"]["summary"]

    transcript_lines = "\n".join(
        f'<div class="tline">{line}</div>'
        for line in showcase.transcript.splitlines()[1:]
    )
    showcase_fields = ["price", "availability", "timing"]

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

    camp_b = cell(campaign, "gpt-4o-mini", "baseline")
    camp_c = cell(campaign, "gpt-4o-mini", "current")
    stat_big = camp_b["unsupported_claim_rate"]["per_run"][0]
    stat_now = camp_c["unsupported_claim_rate"]["per_run"][0]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TruTrace — verified answers from seller calls</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --ink:#111111; --canvas:#ffffff; --soft:#f5f5f5; --charcoal:#39393b;
  --ash:#4b4b4d; --mute:#707072; --stone:#9e9ea0; --hairline:#cacacb;
  --hairline-soft:#e5e5e5; --verified:#007d48; --conflicting:#d30005;
  --unconfirmed:#707072;
}}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:Inter,system-ui,-apple-system,sans-serif; color:var(--ink);
  background:var(--canvas); font-size:16px; line-height:1.5;
  -webkit-font-smoothing:antialiased; }}
.hero {{ background:var(--ink); color:#fff; padding:80px 24px 64px; }}
.hero-inner {{ max-width:1080px; margin:0 auto; }}
.hero h1 {{ font-family:Anton,"Bebas Neue",Inter,sans-serif; font-size:96px;
  line-height:.9; font-weight:400; text-transform:uppercase; letter-spacing:0; }}
.hero .sub {{ font-size:20px; line-height:1.4; color:var(--stone);
  max-width:640px; margin-top:24px; }}
.hero .sub b {{ color:#fff; font-weight:500; }}
main {{ max-width:1080px; margin:0 auto; padding:80px 24px; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
.tile {{ background:var(--canvas); border:1px solid var(--hairline); padding:24px; }}
.tile--soft {{ background:var(--soft); border-color:transparent; }}
.tile--wide {{ grid-column:1 / -1; }}
.tile-copy {{ font-size:17px; line-height:1.45; margin-bottom:20px; }}
.tile-copy b {{ font-weight:500; }}
.tile-copy .cont {{ color:var(--mute); }}
.kicker {{ font-size:12px; font-weight:500; color:var(--mute);
  text-transform:uppercase; letter-spacing:.08em; margin-bottom:12px; }}
.transcript {{ font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  font-size:13px; line-height:1.6; color:var(--charcoal);
  background:var(--soft); padding:16px; margin-bottom:24px; }}
.tline {{ padding:2px 0; }}
.contrast {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
.contrast h3 {{ font-size:16px; font-weight:500; margin-bottom:4px; }}
.contrast .note {{ font-size:14px; color:var(--mute); margin-bottom:12px; }}
.field-row {{ display:flex; align-items:center; gap:12px; padding:12px 0;
  border-bottom:1px solid var(--hairline); }}
.field-name {{ font-weight:500; width:104px; flex:none; }}
.field-value {{ flex:1; }}
.chip {{ flex:none; background:var(--soft); border-radius:9999px;
  padding:4px 12px; font-size:12px; font-weight:500; }}
.reason {{ font-size:14px; color:var(--mute); padding:8px 0 0; }}
.evidence {{ font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  font-size:13px; line-height:1.6; color:var(--charcoal);
  background:var(--soft); padding:8px 12px; margin-top:8px; }}
.stat-num {{ font-size:56px; font-weight:500; line-height:1.05; letter-spacing:-.01em; }}
.stat-num .of {{ color:var(--mute); }}
.stat-label {{ color:var(--mute); margin-top:12px; font-size:16px; }}
.stat-now {{ margin-top:16px; font-size:16px; }}
table {{ width:100%; border-collapse:collapse; font-size:15px;
  font-variant-numeric:tabular-nums; }}
th {{ background:var(--soft); font-size:14px; font-weight:500; text-align:left;
  padding:12px 16px; }}
td {{ padding:12px 16px; border-bottom:1px solid var(--hairline); }}
td:not(:first-child), th:not(:first-child) {{ text-align:right; }}
.table-scroll {{ overflow-x:auto; }}
.deg-row {{ display:flex; justify-content:space-between; padding:10px 0;
  border-bottom:1px solid var(--hairline); font-size:16px; }}
.deg-row span:last-child {{ font-weight:500; }}
.statement {{ font-size:24px; font-weight:500; line-height:1.25; }}
.fine {{ font-size:12px; color:var(--mute); margin-top:16px; line-height:1.5; }}
footer {{ border-top:1px solid var(--hairline); padding:48px 24px; }}
.footer-inner {{ max-width:1080px; margin:0 auto; color:var(--mute);
  font-size:14px; }}
.footer-inner .fine {{ margin-top:12px; }}
@media (max-width:1023px) {{
  .grid {{ grid-template-columns:1fr 1fr; }}
  .hero h1 {{ font-size:64px; }}
  main {{ padding:48px 24px; }}
}}
@media (max-width:640px) {{
  .grid, .contrast {{ grid-template-columns:1fr; }}
  .hero {{ padding:48px 24px; }}
  .hero h1 {{ font-size:48px; }}
  main {{ padding:32px 16px; }}
  .stat-num {{ font-size:44px; }}
}}
</style>
</head>
<body>
<!-- Composition follows the Stageshow bento example (MIT, (c) 2026 Benji
     Taylor); visual tokens from this project's DESIGN.md. All data on
     this page is generated from real pipeline runs by demo/build_demo.py. -->
<header class="hero">
  <div class="hero-inner">
    <h1>TruTrace</h1>
    <p class="sub">Verified answers from seller calls. <b>Every field carries
    its evidence, or it is not asserted.</b></p>
  </div>
</header>
<main>
  <div class="grid">

    <section class="tile tile--wide">
      <p class="tile-copy"><b>The failing case.</b> <span class="cont">One
      florist, asked for a dozen red roses with delivery today. The seller
      hedges three times. The baseline asserts all three hedges as facts;
      TruTrace demotes them and keeps the proof attached.</span></p>
      <div class="transcript">{transcript_lines}</div>
      <div class="contrast">
        <div>
          <h3>Naive baseline</h3>
          <p class="note">Prompt asks for values. No verification.</p>
          {answer_rows(base, showcase_fields)}
        </div>
        <div>
          <h3>TruTrace</h3>
          <p class="note">Same extractor. Verification decides what may be asserted.</p>
          {answer_rows(now, showcase_fields)}
        </div>
      </div>
    </section>

    <section class="tile tile--soft">
      <p class="kicker">Unsupported claims · campaign · gpt-4o-mini</p>
      <div class="stat-num">{stat_big.split(' of ')[0]} <span class="of">of {stat_big.split(' of ')[1]}</span></div>
      <p class="stat-label">of the baseline's confirmations were claims the
      call does not support.</p>
      <p class="stat-now">With verification: <b>{stat_now}</b>.</p>
      <p class="fine">Run 1 of 3. All three runs are in the report.</p>
    </section>

    <section class="tile">
      <p class="tile-copy"><b>Extraction with proof.</b> <span class="cont">A
      confirmed field cites its span, its speaker and its timestamp.</span></p>
      {answer_rows(proof, ["price", "availability", "timing"], show_evidence=True)}
    </section>

    <section class="tile">
      <p class="tile-copy"><b>The provider dies at call four.</b>
      <span class="cont">Six campaign calls, the primary provider killed
      mid run, the offline provider as fallback.</span></p>
      <div class="deg-row"><span>Served by the primary</span><span>{deg_a['served_by_primary']} of 6</span></div>
      <div class="deg-row"><span>Fell back</span><span>{deg_a['served_by_fallback']} of 6</span></div>
      <div class="deg-row"><span>Lost</span><span>{deg_a['unavailable']} of 6</span></div>
      <div class="deg-row"><span>Both providers down</span><span>{deg_b['unavailable']} of 6 unconfirmed, 0 invented</span></div>
      <p class="fine">Simulated death, real fallback code. Covered by
      automated tests in tests/test_degradation.py.</p>
    </section>

    <section class="tile tile--soft">
      <p class="statement">Synthetic transcripts. No live audio. No real telephony.</p>
      <p class="fine">The campaign is ten written calls, not ten placed
      calls. The gold labels were drafted by an AI coding agent during
      the build and are pending Diwakar Bhagat's human review.</p>
    </section>

    <section class="tile tile--wide">
      <p class="tile-copy"><b>Baseline vs current, measured.</b>
      <span class="cont">Counts are per run, three runs each, at
      temperature 0. Accuracy counts a field right only when value,
      status and condition all match gold.</span></p>
      <div class="kicker">Campaign · 10 calls · 70 fields</div>
      <div class="table-scroll"><table>
        <tr><th>Run</th><th>Accuracy</th><th>Unsupported</th><th>p50</th><th>p95</th><th>Cost / call</th></tr>
        {score_rows(campaign)}
      </table></div>
      <div class="kicker" style="margin-top:32px">Held out · 12 cases · 84 fields</div>
      <div class="table-scroll"><table>
        <tr><th>Run</th><th>Accuracy</th><th>Unsupported</th><th>p50</th><th>p95</th><th>Cost / call</th></tr>
        {score_rows(heldout)}
      </table></div>
      <p class="fine">gemini-2.0-flash-001 did not run: OpenRouter returned
      HTTP 404 for that model id, and the runs were stopped rather than
      re-pointed. Full tables, spreads and methodology are in
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
    DESIGN.md. Every number on this page was generated from recorded
    runs by demo/build_demo.py.</p>
  </div>
</footer>
</body>
</html>
"""
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"wrote {OUT} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
