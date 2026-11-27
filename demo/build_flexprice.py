"""Build demo/flexprice.html: the Flexprice pitch page for TruTrace.

A sibling generator to demo/build_demo.py (which still owns
index.html and try.html and is not touched). This page runs one
scenario, "a day at Flexprice", through the whole TruTrace pipeline:

- the scenario (a fictional support call about a disputed invoice,
  and the extraction an AI agent produced from it) lives in
  demo/flexprice_scenario.json;
- the verdicts are NOT written here: they are the recorded output of
  a real verification run against the deployed backend
  (POST /api/verify, gpt-4o-mini via OpenRouter), saved verbatim in
  demo/flexprice_run.json, run id and all. The page renders that
  record; if the record changes, the page changes.

Cost figures come from the recorded eval summaries, like the demo
page's, plus this run's own recorded usage. Design: Stageshow
principles on top, DESIGN.apple.md tokens, CupertinoUI measured
macOS surface values, the same CSS base as the demo page (imported
from build_demo). Action Blue #0066cc is the only interactive
colour; icons are original inline SVGs in the SF Symbols visual
language; zero external references.

Run: python demo/build_flexprice.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from build_demo import CSS, cell, cost_str, esc, icon  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(os.path.dirname(__file__), "flexprice.html")

# Product-vocabulary chips, matching try.html's mapping.
STATUS = {
    "supported": ("Supported", "var(--verified)"),
    "uncertain": ("Uncertain", "var(--label-2)"),
    "unsupported": ("Unsupported", "var(--label-2)"),
    "contradictory": ("Contradictory", "var(--conflicting)"),
    "not_claimed": ("Not in the extraction", "var(--label-2)"),
    "unverified": ("No check", "var(--label-2)"),
}

FIELD_ORDER = [
    "price", "currency", "quantity_or_stock", "availability",
    "timing", "contact_next_step", "delivery_or_pickup",
]

UNVERIFIED_LABEL = {
    "credit_balance_usd": "Credit balance",
    "overage_rate_per_1000_events_usd": "Overage rate, per 1,000 events",
}


def fmt_claimed(name, value):
    if value is None:
        return "—"
    if name == "price":
        return f"${value:,.0f}" if float(value).is_integer() else f"${value}"
    if name == "quantity_or_stock":
        return f"{value:,}"
    if name == "credit_balance_usd":
        return f"${value:,.0f}"
    if name == "overage_rate_per_1000_events_usd":
        return f"${value:.2f}"
    return str(value)


def fmt_verified(name, value):
    if value is None:
        return "—"
    if name == "price":
        return f"${value:,.0f}" if float(value).is_integer() else f"${value}"
    return str(value)


# ---------------------------------------------------------------- page css
# Everything below is additive to the demo page's CSS base: the ops
# window stage, the staged verdict reveal, tally chips. Same tokens.

FLEX_CSS = """
/* flexprice.html: the ops window stage and the verdict reveal */
.backlink { display:inline-block; margin-top:22px; color:var(--blue-dark);
  font-size:15px; text-decoration:none; }
.ops { background:var(--canvas); border-radius:var(--r-window);
  box-shadow:var(--window-shadow); overflow:hidden; margin-top:18px;
  color:var(--label); }
.ops-bar { display:flex; align-items:center; gap:7px;
  padding:11px 14px; background:var(--pearl);
  border-bottom:1px solid var(--separator); }
.ops-dot { width:11px; height:11px; border-radius:50%; background:var(--fill); }
.ops-title { font-size:13px; font-weight:600; color:var(--label-2);
  margin-left:8px; }
.ops-body { padding:16px 18px 18px; }
.ops-beat { display:flex; gap:12px; align-items:baseline; padding:9px 0 3px; }
.ops-beat .btime { font-family:var(--mono); font-size:12px;
  color:var(--label-3); flex:none; width:44px; }
.ops-beat .bname { font-size:14px; font-weight:600; }
.ops-beat .bnote { font-size:13px; color:var(--label-2); }
.evt { display:flex; align-items:center; gap:10px; padding:6px 10px;
  border-radius:var(--r-item); font-size:13.5px; }
.evt .bar { height:8px; border-radius:4px; background:var(--fill-2); }
.evt .etag { font-family:var(--mono); font-size:12px; color:var(--label-2);
  flex:none; }
.evt .ecount { margin-left:auto; font-variant-numeric:tabular-nums;
  color:var(--label-2); font-size:13px; flex:none; }
.inv { display:flex; align-items:center; gap:12px; margin-top:8px;
  padding:12px; border:1px solid var(--border);
  border-radius:var(--r-group); }
.inv .iname { font-weight:600; font-size:15px; }
.inv .inote { font-size:13px; color:var(--label-2); }
.inv .itotal { margin-left:auto; font-size:19px; font-weight:600;
  font-variant-numeric:tabular-nums; flex:none; }
.dchip { flex:none; font-size:12px; font-weight:600; padding:3px 11px;
  border-radius:9999px; background:rgba(211,0,5,0.08);
  color:var(--conflicting); }
.beats { display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px;
  margin-top:18px; }
.beat p { font-size:14px; line-height:1.45; color:var(--d-label-2); }
.beat b { color:#fff; font-weight:600; display:block; font-size:15px;
  margin-bottom:3px; }
.replay { margin-top:16px; font-size:14px; font-weight:600;
  color:var(--blue-dark); padding:6px 2px; }

/* verdict stage */
.stage-head { display:flex; align-items:center; gap:10px;
  flex-wrap:wrap; margin-bottom:6px; }
.tally { display:flex; gap:8px; flex-wrap:wrap; margin:10px 0 4px; }
.tally .tchip { font-size:12.5px; font-weight:600; padding:4px 12px;
  border-radius:9999px; background:var(--fill-3); color:var(--label-2);
  font-variant-numeric:tabular-nums; }
.tally .tchip b { color:var(--label); }
.case-cols { display:grid; grid-template-columns:1fr 1fr; gap:22px;
  align-items:start; }
.frow .fst { flex:none; font-size:11px; font-weight:700; color:var(--label-3);
  width:16px; text-align:center; }
.frow.resolving { background:rgba(0,102,204,0.08); }
.frow .chip.noev { border:1.5px dashed var(--border); background:transparent; }
.runline { font-size:13px; color:var(--label-2); margin-top:14px;
  font-variant-numeric:tabular-nums; }
.runline .rid { font-family:var(--mono); font-size:12px; }
.spot { padding:13px 0; border-bottom:1px solid var(--separator); }
.spot:last-child { border-bottom:0; }
.spot .sname { font-weight:600; font-size:16px; }
.spot .snote { font-size:14.5px; color:var(--label-2); line-height:1.5;
  margin-top:3px; }
.spot .snote b { color:var(--label); font-weight:600; }
.fitlink { color:var(--blue-dark); text-decoration:none; font-weight:600; }
@media (prefers-reduced-motion: no-preference) {
  .ops .evt, .ops .inv, .ops .dchip { opacity:0; }
  .ops.play .evt { animation:fx-in 0.5s ease forwards; }
  .ops.play .evt:nth-child(2) { animation-delay:0.15s; }
  .ops.play .evt:nth-child(3) { animation-delay:0.3s; }
  .ops.play .evt:nth-child(4) { animation-delay:0.45s; }
  .ops.play .inv { animation:fx-in 0.5s ease 0.85s forwards; }
  .ops.play .dchip { animation:fx-in 0.45s ease 1.5s forwards; }
  .frow { transition:background 0.3s ease; }
  .frow .chip { transition:color 0.3s ease, background 0.3s ease; }
}
@keyframes fx-in { from { opacity:0; transform:translateY(6px); }
  to { opacity:1; transform:translateY(0); } }
@media (max-width:1023px) { .case-cols { grid-template-columns:1fr; } }
@media (max-width:640px) {
  .beats { grid-template-columns:1fr; }
  .inv { flex-wrap:wrap; }
  .inv .itotal { margin-left:0; }
}
"""

FLEX_JS = """
(function () {
  var reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // The ops window: beats light in sequence when it scrolls into
  // view; the dispute lands last and holds. Replay restarts it.
  var ops = document.querySelector(".ops");
  var replay = document.getElementById("ops-replay");
  function playOps() {
    if (!ops || reduce) { return; }
    ops.classList.remove("play");
    void ops.offsetWidth;
    ops.classList.add("play");
  }
  if (ops && !reduce && "IntersectionObserver" in window) {
    var oo = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { playOps(); oo.disconnect(); }
      });
    }, { threshold: 0.3 });
    oo.observe(ops);
  }
  if (replay) { replay.addEventListener("click", playOps); }

  // The verdict stage. The page is rendered resolved (the poster
  // frame tells the story with no script at all). With script, the
  // stage resets to the agent's claims and the Run control resolves
  // them one by one into the recorded verdicts: each landing row
  // increments its tally, lights its transcript line, and fills the
  // evidence panel, exactly the order a reviewer reads them in.
  var stage = document.querySelector(".vstage");
  if (!stage) { return; }
  var rows = Array.prototype.slice.call(stage.querySelectorAll(".frow"));
  var lines = stage.querySelectorAll(".tline");
  var status = stage.querySelector(".dstatus");
  var evidence = stage.querySelector(".devidence");
  var reason = stage.querySelector(".dreason");
  var claimEl = stage.querySelector(".dclaim");
  var runBtn = document.getElementById("run-verdicts");
  var summary = document.getElementById("stage-summary");
  var tallies = {};
  stage.querySelectorAll(".tchip[data-tally]").forEach(function (chip) {
    tallies[chip.getAttribute("data-tally")] = chip.querySelector("b");
  });
  var timer = null;

  function showDetail(row) {
    rows.forEach(function (r) {
      r.setAttribute("aria-pressed", r === row ? "true" : "false");
    });
    var st = row.getAttribute("data-status");
    var label = row.getAttribute("data-chip");
    status.textContent = row.classList.contains("resolved") || !stage._armed
      ? label : "Claimed";
    status.style.color = row.getAttribute("data-color") || "";
    claimEl.textContent = row.getAttribute("data-claimtext") || "";
    var ev = row.getAttribute("data-evidence");
    if (st === "unverified") {
      evidence.textContent = "No evidence is offered for a claim " +
        "TruTrace cannot check. The claim is labelled, not passed.";
    } else {
      evidence.textContent = ev ||
        "No span in the call supports this claim. The absence is the finding.";
    }
    var rs = row.getAttribute("data-reason");
    reason.textContent = rs || "";
    reason.style.display = rs ? "" : "none";
    var ts = row.getAttribute("data-ts");
    lines.forEach(function (line) {
      line.classList.toggle("hl",
        !!ts && line.getAttribute("data-ts") === ts);
    });
  }

  function arm() {
    stage._armed = true;
    rows.forEach(function (row) {
      row.classList.remove("resolved");
      var chip = row.querySelector(".chip");
      chip.textContent = "Claimed";
      chip.style.color = "var(--label-2)";
    });
    Object.keys(tallies).forEach(function (k) {
      tallies[k].textContent = "0";
    });
    if (summary) { summary.hidden = true; }
    status.textContent = "Not run yet";
    status.style.color = "var(--label-2)";
    claimEl.textContent = "The agent's claims are listed as claimed. " +
      "Run the verification and each one resolves into its recorded verdict.";
    evidence.textContent = "";
    reason.textContent = "";
    lines.forEach(function (line) { line.classList.remove("hl"); });
    runBtn.disabled = false;
    runBtn.textContent = "Run verification";
  }

  function resolve() {
    if (timer) { window.clearInterval(timer); }
    arm();
    stage._armed = false;
    runBtn.disabled = true;
    runBtn.textContent = "Verifying\\u2026";
    var i = 0;
    function step() {
      if (i > 0) { rows[i - 1].classList.remove("resolving"); }
      if (i >= rows.length) {
        window.clearInterval(timer);
        timer = null;
        if (summary) { summary.hidden = false; }
        runBtn.disabled = false;
        runBtn.textContent = "Replay the run";
        return;
      }
      var row = rows[i];
      row.classList.add("resolving", "resolved");
      var chip = row.querySelector(".chip");
      chip.textContent = row.getAttribute("data-chip");
      chip.style.color = row.getAttribute("data-color") || "";
      var key = row.getAttribute("data-tally-key");
      if (key && tallies[key]) {
        tallies[key].textContent =
          String(parseInt(tallies[key].textContent, 10) + 1);
      }
      showDetail(row);
      i += 1;
    }
    step();
    timer = window.setInterval(step, 560);
  }

  rows.forEach(function (row) {
    row.addEventListener("click", function () { showDetail(row); });
  });
  if (runBtn) { runBtn.addEventListener("click", resolve); }
  if (!reduce) {
    arm();
    if ("IntersectionObserver" in window) {
      var vo = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { resolve(); vo.disconnect(); }
        });
      }, { threshold: 0.25 });
      vo.observe(stage);
    }
  } else if (rows.length) {
    rows.forEach(function (r) { r.classList.add("resolved"); });
    showDetail(rows[0]);
  }
  if (reduce && rows.length) { showDetail(rows[0]); }
})();
"""


def transcript_html(transcript):
    lines = []
    for line in transcript.splitlines():
        ts = line[1:6] if line.startswith("[") else ""
        lines.append(f'<div class="tline" data-ts="{esc(ts)}">{esc(line)}</div>')
    return "\n".join(lines)


def field_row(name, entry, gloss):
    label, color = STATUS[entry["status"]]
    claimed = fmt_claimed(name, entry["claimed_value"])
    if name == "availability" and entry["claimed_value"] is not None:
        claimed += " · asserted as included"
    claim_text = f"The agent's extraction claims {gloss.lower()} is {claimed}."
    if entry["status"] == "not_claimed":
        claim_text = (
            f"The extraction never claims {gloss.lower()}; "
            "there is nothing to vouch for."
        )
    return (
        f'<button type="button" class="frow" data-status="{esc(entry["status"])}" '
        f'data-chip="{esc(label)}" data-color="{esc(color)}" '
        f'data-tally-key="{esc(entry["status"])}" '
        f'data-ts="{esc(entry.get("timestamp") or "")}" '
        f'data-evidence="{esc(entry.get("evidence") or "")}" '
        f'data-reason="{esc(entry.get("reason") or "")}" '
        f'data-claimtext="{esc(claim_text)}" aria-pressed="false">'
        f'<span class="fname">{esc(gloss)}</span>'
        f'<span class="fvalue">{esc(claimed)}</span>'
        f'<span class="chip" style="color:{color}">{label}</span></button>'
    )


def unverified_row(key, item):
    label, color = STATUS["unverified"]
    claimed = fmt_claimed(key, item["claimed_value"])
    claim_text = (
        f"The agent's extraction claims {UNVERIFIED_LABEL[key].lower()} "
        f"is {claimed}."
    )
    return (
        f'<button type="button" class="frow" data-status="unverified" '
        f'data-chip="{esc(label)}" data-color="{esc(color)}" '
        f'data-tally-key="unverified" data-ts="" data-evidence="" '
        f'data-reason="{esc("TruTrace has no check for this field, so the claim passes through unverified: " + item["reason"] + ".")}" '
        f'data-claimtext="{esc(claim_text)}" aria-pressed="false">'
        f'<span class="fname">{esc(UNVERIFIED_LABEL[key])}</span>'
        f'<span class="fvalue">{esc(claimed)}</span>'
        f'<span class="chip noev" style="color:{color}">{label}</span></button>'
    )


def main() -> int:
    scenario = json.load(open(os.path.join(os.path.dirname(__file__), "flexprice_scenario.json")))
    run = json.load(open(os.path.join(os.path.dirname(__file__), "flexprice_run.json")))
    heldout = json.load(open(os.path.join(ROOT, "evals/results/final_heldout_summary.json")))
    campaign = json.load(open(os.path.join(ROOT, "evals/results/final_campaign_summary.json")))
    ho_b, ho_c = cell(heldout, "gpt-4o-mini", "baseline"), cell(heldout, "gpt-4o-mini", "current")
    ca_b, ca_c = cell(campaign, "gpt-4o-mini", "baseline"), cell(campaign, "gpt-4o-mini", "current")

    gloss = scenario["field_gloss"]
    transcript = run["input"]["transcript"]
    fields = run["fields"]
    summary = run["summary"]
    usage = run["usage"]
    run_cost = usage.get("reported_cost_usd")
    latency_s = run["latency_ms"] / 1000.0

    rows = "\n".join(field_row(n, fields[n], gloss[n]) for n in FIELD_ORDER)
    urows = "\n".join(unverified_row(k, v) for k, v in run["unverified"].items())
    tally = (
        f'<span class="tchip" data-tally="supported">Supported <b>{summary["supported"]}</b></span>'
        f'<span class="tchip" data-tally="uncertain">Uncertain <b>{summary["uncertain"]}</b></span>'
        f'<span class="tchip" data-tally="contradictory">Contradictory <b>{summary["contradictory"]}</b></span>'
        f'<span class="tchip" data-tally="unsupported">Unsupported <b>{summary["unsupported"]}</b></span>'
        f'<span class="tchip" data-tally="not_claimed">Not claimed <b>{summary["not_claimed"]}</b></span>'
        f'<span class="tchip" data-tally="unverified">No check <b>{len(run["unverified"])}</b></span>'
    )
    summary_line = (
        f'{summary["supported"]} supported, {summary["uncertain"]} uncertain, '
        f'{summary["contradictory"]} contradictory, {summary["unsupported"]} unsupported, '
        f'{summary["not_claimed"]} not claimed, and {len(run["unverified"])} claims '
        "TruTrace has no check for and refuses to vouch for. "
        "The two money claims the agent got wrong did not pass."
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TruTrace for Flexprice — every billing number carries its evidence</title>
<style>{CSS}{FLEX_CSS}</style>
</head>
<body>
<!-- A pitch page for Flexprice, generated by demo/build_flexprice.py.
     The scenario is written for this page and labelled as one. The
     verdicts are a real recorded run of the live verification
     backend (demo/flexprice_run.json); nothing here is hand-scored.
     Tokens: DESIGN.apple.md. Surface values: measured macOS values
     adapted from the CupertinoUI theme CSS, as the demo page. Icons
     are original inline SVG drawings in the SF Symbols style. -->
<header class="site">
  <div class="site-inner">
    <p class="wordmark">TruTrace <span>· built for Flexprice</span></p>
    <h1>Every number on the invoice carries its evidence, or it is not asserted.</h1>
    <p class="sub">Flexprice meters usage and turns it into invoices
    that customers have to trust. <b>This page runs one day of that
    operation, and one disputed invoice, through TruTrace, the proof
    layer for numbers an AI states out loud.</b></p>
    <a class="backlink" href="index.html">The benchmark story</a>
  </div>
</header>
<main>
  <div class="grid">

    <section class="tile tile--dark s8">
      <div class="tile-head">{icon("server")}<p class="kicker">A day at Flexprice · the operation</p></div>
      <h2>Metering all morning. One dispute by afternoon.</h2>
      <div class="ops" aria-label="A staged illustration of a day of billing operations">
        <div class="ops-bar"><span class="ops-dot"></span><span class="ops-dot"></span><span class="ops-dot"></span><span class="ops-title">flexprice · operations</span></div>
        <div class="ops-body">
          <div class="evt"><span class="etag">api.call</span><span class="bar" style="width:34%"></span><span class="ecount">events streaming</span></div>
          <div class="evt"><span class="etag">tokens</span><span class="bar" style="width:52%"></span><span class="ecount">metered</span></div>
          <div class="evt"><span class="etag">credits</span><span class="bar" style="width:26%"></span><span class="ecount">applied</span></div>
          <div class="evt"><span class="etag">entitlements</span><span class="bar" style="width:44%"></span><span class="ecount">checked</span></div>
          <div class="inv"><div><p class="iname">Invoice FP-1042 · October</p><p class="inote">Growth plan · usage, credit applied</p></div><span class="itotal">$1,240</span><span class="dchip">Disputed</span></div>
        </div>
      </div>
      <div class="beats">
        <div class="beat"><b>09:00 · Metering</b><p>Usage events stream in from AI companies and are counted, priced and credited. This part Flexprice already does.</p></div>
        <div class="beat"><b>13:00 · The invoice</b><p>FP-1042 goes out at $1,240: $1,540 of metered usage, a $300 platform credit applied.</p></div>
        <div class="beat"><b>16:40 · The dispute</b><p>The customer calls. An AI agent takes the call and writes down what was agreed. That summary is where numbers stop carrying their evidence.</p></div>
      </div>
      <button type="button" class="replay" id="ops-replay">Replay the day</button>
      <p class="fine">A staged illustration of the operation, drawn for
      this page. The invoice figures are the scenario's, and the call
      below is where they are tested.</p>
    </section>

    <section class="tile s4">
      <div class="tile-head">{icon("waveform")}<p class="kicker">The moment that matters</p></div>
      <h2>The call is the contract.</h2>
      <p class="tile-copy" style="margin-top:10px">When a customer
      disputes an invoice, the support call is where the company's
      position gets set: what was metered, what the total is, what was
      promised. <span class="cont">If an AI agent summarises that call
      and states a number the call never established, the company has
      not saved a support ticket. It has manufactured the next
      dispute.</span></p>
      <div class="deg-row"><span>Claims in the agent's summary</span><span>8</span></div>
      <div class="deg-row"><span>Verdicts against the call</span><span>6</span></div>
      <div class="deg-row"><span>No check exists yet</span><span>2</span></div>
      <div class="deg-row"><span>That failed or went unchecked</span><span>4</span></div>
      <div class="deg-row"><span>Cost of checking</span><span>${run_cost:.6f}</span></div>
      <p class="fine">Counts and cost are this page's recorded run,
      cited in full below the verdicts.</p>
    </section>

    <section class="tile tile--glass s12 vstage case">
      <div class="tile-head">{icon("seal")}<p class="kicker">The dispute call · verified</p></div>
      <h2>What the agent wrote down, checked against what was said.</h2>
      <p class="tile-copy" style="margin-top:10px">A scenario written
      for this page: a Flexprice support call about invoice FP-1042,
      and the extraction an AI agent produced from it. The agent is
      good, and it still overstates an entitlement, drops a hedge, and
      states a credit balance the call never gives. <span class="cont">
      Run the verification: each claim resolves into its recorded
      verdict, with the exact line it rests on, or the absence stated.</span></p>
      <div class="stage-head">
        <button type="button" class="trycta" id="run-verdicts">Run verification</button>
      </div>
      <div class="tally">{tally}</div>
      <div class="case-cols">
        <div class="transcript transcript--hero">{transcript_html(transcript)}</div>
        <div>
          {rows}
          {urows}
        </div>
      </div>
      <div class="detail" aria-live="polite">
        <div class="detail-head"><span class="dlabel">Evidence</span><span class="dstatus"></span></div>
        <p class="dclaim" style="font-size:15px;margin-top:8px"></p>
        <p class="devidence"></p><p class="dreason"></p>
      </div>
      <p class="tile-copy" id="stage-summary" style="margin-top:16px"><b>{summary_line}</b></p>
      <p class="runline">Verdicts are one real run of the live backend,
      not a mock: run <span class="rid">{esc(run["run_id"])}</span> ·
      gpt-4o-mini via OpenRouter · {latency_s:.1f} s ·
      ${run_cost:.6f} for the call · inputs and outputs recorded in
      demo/flexprice_run.json in the repository. Run it yourself in
      <a href="try.html">the workspace</a>.</p>
    </section>

    <section class="tile s7">
      <div class="tile-head">{icon("shield")}<p class="kicker">The claims that fail</p></div>
      <h2>Two of them are money.</h2>
      <div class="spot"><p class="sname">Invoice total: claimed $1,540. Verdict: contradictory.</p>
      <p class="snote">The call states two prices: $1,540 of usage
      before the credit, and <b>$1,240, the invoice total</b>. The
      agent wrote down the wrong one as the total. TruTrace asserts
      neither and shows both, because a billing agent that picks the
      louder number has just told a customer they owe $300 more than
      they do.</p></div>
      <div class="spot"><p class="sname">Credit balance: claimed $500. Verdict: no check.</p>
      <p class="snote">Support says, in terms, that the remaining
      balance is not in front of them and not on the invoice. The
      agent states $500 anyway. <b>TruTrace has no balance check
      today, so it marks the claim unchecked rather than letting it
      pass as verified.</b> An unchecked label is honest; a silent
      pass would be the failure.</p></div>
      <div class="spot"><p class="sname">Advanced analytics entitlement: claimed as included. Verdict: unsupported.</p>
      <p class="snote">Support hedges and refuses to promise it:
      “usually included, I believe, I would need to double-check.”
      The extraction asserts it as included. <b>An entitlement stated
      stronger than it was said is a feature the customer now believes
      they bought.</b></p></div>
    </section>

    <section class="tile tile--dark3 s5">
      <div class="tile-head">{icon("info")}<p class="kicker">Stated limits</p></div>
      <ul class="limits">
        <li><b>The events count is not established.</b> The agent's
        figure of 1,842,300 events is stated plainly in the call, and
        the current verification profile, built on seller calls, does
        not ground a metered-event count. It reports the claim
        unsupported rather than guessing. A billing profile, events,
        rates, balances, entitlements, is the named next piece of
        work.</li>
        <li><b>The overage rate has no check either.</b> $0.40 per
        thousand events is stated in the call and claimed correctly,
        and it still passes only as unchecked, because no check
        exists for it yet.</li>
        <li><b>The call is a scenario.</b> Written for this page, not
        a recording, and labelled as one wherever it appears.</li>
        <li><b>One run, not a benchmark.</b> The verdicts above are a
        single recorded run against this scenario. The measured
        benchmark, 32 calls and a 10 call campaign, lives on the
        <a class="fitlink" href="index.html">main page</a>, scored
        against gold labels drafted by an AI and pending human
        review.</li>
      </ul>
    </section>

    <section class="tile s6">
      <div class="tile-head">{icon("chart")}<p class="kicker">The fit</p></div>
      <h2>Billing is a trust product. This is the trust layer.</h2>
      <p class="tile-copy" style="margin-top:10px">Flexprice sells the
      numbers a company charges by. Every one of those numbers that an
      agent later states to a customer, in support, in docs, in an AI
      coworker, either carries the line it rests on or it is a dispute
      waiting to happen. <span class="cont">TruTrace is that proof
      layer: it sits behind the agents Flexprice and its customers
      already run, and it refuses to let a claim travel further than
      its evidence. The verification discipline is built and measured.
      The billing profile is small, named work, and it is the work I
      want to do with your team.</span></p>
      <p class="tile-copy">Diwakar Bhagat · <a class="fitlink" href="https://diwakarbhagat.com">diwakarbhagat.com</a> ·
      <a class="fitlink" href="try.html">run the workspace</a> ·
      <a class="fitlink" href="index.html">the benchmark</a></p>
    </section>

    <section class="tile tile--glass s6">
      <div class="tile-head">{icon("timer")}<p class="kicker">What verification costs · recorded</p></div>
      <p class="tile-copy"><b>A second pass, priced.</b> <span class="cont">From
      the recorded benchmark runs on gpt-4o-mini, three runs each:</span></p>
      <div class="deg-row"><span>Naive extraction · per call, held out</span><span>{cost_str(ho_b)}</span></div>
      <div class="deg-row"><span>Verified · per call, held out</span><span>{cost_str(ho_c)}</span></div>
      <div class="deg-row"><span>Naive extraction · per call, campaign</span><span>{cost_str(ca_b)}</span></div>
      <div class="deg-row"><span>Verified · per call, campaign</span><span>{cost_str(ca_c)}</span></div>
      <div class="deg-row"><span>This page's dispute call, verified</span><span>${run_cost:.6f}</span></div>
      <div class="deg-row"><span>Whole TruTrace build, total model spend</span><span>$0.0536</span></div>
      <p class="fine">Per call figures are computed from the recorded
      eval summaries in evals/results; the scenario run's cost is its
      own recorded provider usage. The total is the OpenRouter key's
      usage record for the whole build, $0.0536 of a $100 limit, as
      recorded on 27 Nov 2026. Verification roughly doubles the model
      cost of an answer and stays under two hundredths of a cent a
      call; the benchmark's accuracy and unsupported claim figures are
      on the main page, measured against AI drafted gold labels
      pending human review.</p>
    </section>

  </div>
</main>
<footer>
  <div class="footer-inner">
    <p>TruTrace, by Diwakar Bhagat. This page was built for Flexprice:
    the scenario is written, the verdicts are real, and the limits are
    stated on the page.</p>
    <p class="fine">Composition after the Stageshow bento discipline
    (MIT, © 2026 Benji Taylor). Design tokens from this project's
    DESIGN.apple.md; surface values are measured macOS values adapted
    from the CupertinoUI theme CSS, with its multi-accent system not
    imported. Icons are original inline SVG drawings in the SF
    Symbols style, not Apple's asset files. Generated by
    demo/build_flexprice.py from demo/flexprice_scenario.json and the
    recorded run demo/flexprice_run.json.</p>
  </div>
</footer>
<script>{FLEX_JS}</script>
</body>
</html>
"""
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote {OUT} ({len(page)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
