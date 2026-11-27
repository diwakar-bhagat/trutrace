"""Generate tools/gold_review.html, the gold-label review tool.

The tool embeds the frozen annotated dataset (datasets/
golden_dataset.jsonl, 32 calls, 224 fields, split per
datasets/split.json) so the page is a single self contained file.
It changes nothing in the dataset: the reviewer's decisions live
in the page (localStorage) as a working draft, and the primary way
they land is submission to the workbench backend
(POST /api/gold/review), which stores them as
gold-v2-human-reviewed. Exporting gold_labels_v2.json remains as a
fallback. The page is served on Cloudflare Pages at /review and
also opens as a local file. See GOLD_REVIEW.md for the protocol.

Usage:
    python tools/build_gold_review.py
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PROTOCOL = {
    "confirmed": "supported",
    "uncertain": "uncertain",
    "unconfirmed": "unsupported",
    "conflicting": "contradictory",
}


def build_data():
    with open(os.path.join(ROOT, "datasets", "split.json")) as fh:
        split = json.load(fh)
    split_of = {}
    for name, ids in split.items():
        for case_id in ids:
            split_of[case_id] = "heldout" if name == "heldout" else "dev"
    cases = []
    fields_total = 0
    with open(os.path.join(ROOT, "datasets", "golden_dataset.jsonl")) as fh:
        for line in fh:
            if not line.strip():
                continue
            doc = json.loads(line)
            fields = []
            for name, gold in doc["gold"].items():
                evidence = gold.get("evidence")
                start = end = None
                if evidence:
                    idx = doc["transcript"].find(evidence)
                    if idx >= 0:
                        start, end = idx, idx + len(evidence)
                fields.append({
                    "name": name,
                    "value": gold.get("value"),
                    "ai_status_engine": gold["status"],
                    "ai_status": PROTOCOL[gold["status"]],
                    "condition": gold.get("condition"),
                    "evidence": evidence,
                    "ev_start": start,
                    "ev_end": end,
                })
                fields_total += 1
            cases.append({
                "id": doc["id"],
                "split": split_of.get(doc["id"], "dev"),
                "business": doc.get("business_name"),
                "product": doc.get("product"),
                "question": doc.get("question"),
                "taxonomy": doc.get("taxonomy"),
                "transcript": doc["transcript"],
                "fields": fields,
            })
    return {"cases": cases, "fields_total": fields_total}


HTML = r"""<!DOCTYPE html>
<!--
  TruTrace gold-label review tool. Served on Cloudflare Pages at
  /review; also opens as a local file.

  Storage note: this page keeps the in-progress review in
  localStorage as a working draft, on the reviewer's own machine.
  On load it fetches the review currently stored on the backend
  (GET /api/gold/review) and seeds itself from it, so the fields
  already reviewed there open filled in and the progress counter
  reflects the server's coverage; local edits made after the last
  sync are kept and marked as unsubmitted changes, never silently
  discarded. The durable record is the submission to the workbench
  backend (POST /api/gold/review), which stores the review as
  gold-v2-human-reviewed; exporting gold_labels_v2.json remains as
  a fallback. Nothing on this page writes to the dataset: the
  frozen AI drafted labels (gold-v1-ai-drafted) are embedded read
  only, and human decisions land as a new version, never over the
  originals. Protocol: GOLD_REVIEW.md in the project root.
-->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TruTrace — Gold Label Review</title>
<style>
  :root{
    --blue:#0066cc; --blue-dark:#2997ff;
    --ink:#1d1d1f; --gray:#6e6e73; --faint:#86868b;
    --bg:#f5f5f7; --panel:#ffffff; --line:rgba(0,0,0,.09);
    --mark:#fff3bf; --mark-line:#e6c619;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:400 17px/1.5 "SF Pro Text",system-ui,-apple-system,"Inter","Segoe UI",sans-serif;}
  header{background:var(--panel);border-bottom:1px solid var(--line);
    padding:18px 28px 14px;}
  header h1{font-size:28px;font-weight:600;letter-spacing:-.02em;margin:0 0 4px;}
  header p{margin:0;color:var(--gray);font-size:15px;max-width:880px;}
  .bar{display:flex;flex-wrap:wrap;gap:14px;align-items:center;
    padding:12px 28px;background:var(--panel);border-bottom:1px solid var(--line);}
  .bar label{font-size:14px;color:var(--gray);}
  input[type=text],select,textarea{font:inherit;font-size:15px;color:var(--ink);
    border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:#fff;}
  button{font:inherit;font-size:15px;border:1px solid var(--line);background:#fff;
    color:var(--ink);border-radius:980px;padding:6px 16px;cursor:pointer;}
  button:hover{border-color:rgba(0,0,0,.25)}
  button.primary{background:var(--blue);border-color:var(--blue);color:#fff;}
  button:disabled{opacity:.4;cursor:default}
  .progress{flex:1;min-width:220px;}
  .progress .track{height:8px;border-radius:4px;background:rgba(0,0,0,.08);overflow:hidden;}
  .progress .fill{height:100%;background:var(--blue);width:0%;}
  .progress .nums{font-size:13px;color:var(--gray);margin-top:4px;}
  #submitStatus{padding:10px 28px;font-size:15px;background:var(--panel);
    border-bottom:1px solid var(--line);display:none;}
  #submitStatus.show{display:block;}
  #submitStatus.ok{border-left:4px solid var(--blue);font-weight:600;}
  #submitStatus.err{border-left:4px solid #d30005;}
  main{display:grid;grid-template-columns:1fr 1fr;gap:20px;padding:20px 28px;max-width:1440px;margin:0 auto;}
  @media (max-width:900px){main{grid-template-columns:1fr}}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px;}
  .panel h2{font-size:19px;font-weight:600;margin:0 0 4px;letter-spacing:-.01em;}
  .panel .sub{color:var(--gray);font-size:14px;margin:0 0 12px;}
  #transcript{white-space:pre-wrap;font-size:16px;line-height:1.65;
    border:1px solid var(--line);border-radius:8px;padding:14px;background:#fbfbfd;
    max-height:520px;overflow:auto;}
  #transcript mark{background:var(--mark);border-bottom:2px solid var(--mark-line);
    padding:0 1px;border-radius:2px;}
  .hint{font-size:13px;color:var(--faint);margin-top:10px;}
  .fieldname{font-size:22px;font-weight:600;letter-spacing:-.01em;}
  .kv{font-size:15px;margin:8px 0;}
  .kv .k{color:var(--gray);}
  .chip{display:inline-block;font-size:13px;border:1px solid var(--line);
    border-radius:980px;padding:2px 10px;color:var(--gray);}
  .statuses{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 6px;}
  .statuses button.active{background:var(--blue);border-color:var(--blue);color:#fff;}
  #evidenceBox{border:1px solid var(--line);border-radius:8px;background:#fbfbfd;
    padding:12px 14px;font-size:15px;min-height:56px;white-space:pre-wrap;}
  .evmeta{font-size:13px;color:var(--faint);margin-top:6px;}
  textarea{width:100%;min-height:74px;resize:vertical;}
  .rowbtns{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;}
  #fieldList{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;}
  #fieldList button{font-size:14px;padding:4px 12px;}
  #fieldList button.done{border-color:var(--blue);color:var(--blue);}
  #fieldList button.unsynced{border-color:var(--mark-line);background:#fffbe6;}
  #fieldList button.current{background:var(--ink);color:#fff;border-color:var(--ink);}
  @media (max-width:900px){
    header{padding:16px 20px 12px;}
    .bar{padding:12px 20px;}
    main{padding:16px 20px;}
    button{min-height:44px;}
    #fieldList button{min-height:40px;}
    .statuses button{flex:1 1 42%;}
    input[type=text],select,textarea{font-size:16px;}
  }
  footer{padding:0 28px 28px;max-width:1440px;margin:0 auto;color:var(--gray);font-size:13px;}
  a{color:var(--blue);text-decoration:none;}
</style>
</head>
<body>
<header>
  <h1>Gold label review</h1>
  <p>Reviewing the frozen AI drafted labels (<strong>gold-v1-ai-drafted</strong>) field by field.
     Submit your decisions to the backend and they are stored as
     <strong>gold-v2-human-reviewed</strong>; the originals are never overwritten.
     Exporting the file remains as a fallback. Uncertain is its own verdict: never collapse
     it into supported or unsupported. Full protocol: GOLD_REVIEW.md.</p>
</header>
<div class="bar">
  <label>Reviewer <input type="text" id="reviewer" placeholder="Your name" size="18"></label>
  <label>Show
    <select id="filter">
      <option value="all">All fields</option>
      <option value="unreviewed">Unreviewed only</option>
      <option value="dev">Dev split</option>
      <option value="heldout">Held out split</option>
    </select>
  </label>
  <div class="progress">
    <div class="track"><div class="fill" id="pfill"></div></div>
    <div class="nums" id="pnums"></div>
  </div>
  <button id="importBtn">Import export</button>
  <input type="file" id="importFile" accept=".json" hidden>
  <button id="submitBtn" class="primary">Submit review to backend</button>
  <button id="exportBtn">Export file (fallback)</button>
  <button id="resetBtn">Reset</button>
</div>
<div id="submitStatus" role="status"></div>
<main>
  <section class="panel">
    <h2 id="caseTitle">Transcript</h2>
    <p class="sub" id="caseSub"></p>
    <div id="transcript"></div>
    <p class="hint">The highlighted span is the evidence currently attached to this field.
      To change it, select text in the transcript, then choose “Use selection as evidence”.</p>
    <div class="rowbtns">
      <button id="useSel">Use selection as evidence</button>
      <button id="clearEv">Clear evidence</button>
    </div>
    <div id="fieldList"></div>
  </section>
  <section class="panel">
    <div class="fieldname" id="fName"></div>
    <div class="kv"><span class="k">Extracted value:</span> <span id="fValue"></span></div>
    <div class="kv"><span class="k">AI drafted status:</span> <span class="chip" id="fAi"></span>
      <span class="k" id="fCondWrap"> · condition: <span id="fCond"></span></span></div>
    <h2 style="margin-top:18px">Evidence span</h2>
    <div id="evidenceBox"></div>
    <div class="evmeta" id="evMeta"></div>
    <h2 style="margin-top:18px">Your verdict</h2>
    <div class="statuses" id="statusBtns">
      <button data-status="supported">Supported</button>
      <button data-status="uncertain">Uncertain</button>
      <button data-status="unsupported">Unsupported</button>
      <button data-status="contradictory">Contradictory</button>
    </div>
    <p class="hint" style="margin-top:0">Supported: the transcript establishes it. Uncertain: hedged or
      ambiguous, the evidence does not settle it. Unsupported: no adequate evidence in the transcript.
      Contradictory: the transcript contradicts it.</p>
    <div class="evmeta" id="syncNote" style="display:none"></div>
    <h2 style="margin-top:14px">Adjudication note</h2>
    <textarea id="note" placeholder="For ambiguous cases: what made this hard, and how you resolved it. Kept on record."></textarea>
    <div class="rowbtns">
      <button id="prevBtn">← Previous field</button>
      <button id="nextBtn" class="primary">Next field →</button>
    </div>
  </section>
</main>
<footer>
  On load, this page fetches the review stored on the backend and starts from it, so
  what is already reviewed there opens filled in. Your further work is kept in this
  browser as you go (localStorage working draft); fields you change after the last
  sync are marked • as unsubmitted changes until you submit. Submitting sends the
  review to the TruTrace backend, which stores it as gold-v2-human-reviewed and
  reports the coverage it recorded; the export file is the fallback if the backend
  cannot be reached. Scores against these labels are computed by
  evals/gold_metrics.py, which names the gold version on every report.
</footer>
<script>
"use strict";
const DATA = __DATA__;
const LS_KEY = "trutrace.gold_review.v1";
const TOTAL = DATA.fields_total;

let state = loadState();
let queue = [];
let pos = 0;

function loadState(){
  try{
    const raw = localStorage.getItem(LS_KEY);
    if(raw){
      const s = JSON.parse(raw);
      if(s && s.reviews){ s.base = s.base || {}; return s; }
    }
  }catch(e){}
  return {reviewer:"", reviews:{}, base:{}};
}
function save(){
  state.reviewer = document.getElementById("reviewer").value;
  try{ localStorage.setItem(LS_KEY, JSON.stringify(state)); }catch(e){}
}
function entry(caseId, fieldName){
  const byCase = state.reviews[caseId] || (state.reviews[caseId] = {});
  return byCase[fieldName] || (byCase[fieldName] = {status:null, note:"", spanState:"ai", span:null});
}
/* Sync bookkeeping. state.base is the entry map as last synced
   with the backend (fetched on load, replaced after each accepted
   submit). A field whose local entry differs from base carries
   unsubmitted changes: the local edit always wins on screen and is
   marked, never silently discarded by a reseed. */
function mapEntry(map, caseId, name){
  return ((map || {})[caseId] || {})[name] || null;
}
function isEmptyEnt(e){
  return !e || (!e.status && !(e.note || "").trim() &&
    (e.spanState || "ai") === "ai" && !e.span);
}
function cloneEnt(e){
  if(!e) return null;
  return {
    status: e.status || null, note: e.note || "",
    spanState: e.spanState || "ai",
    span: e.span ? {text:e.span.text, start:e.span.start, end:e.span.end} : null
  };
}
function cloneEntries(map){
  const out = {};
  Object.entries(map || {}).forEach(([cid, fields]) => {
    out[cid] = {};
    Object.entries(fields || {}).forEach(([name, e]) => {
      out[cid][name] = cloneEnt(e);
    });
  });
  return out;
}
function entEq(a, b){
  if(isEmptyEnt(a) && isEmptyEnt(b)) return true;
  if(isEmptyEnt(a) || isEmptyEnt(b)) return false;
  const sa = a.span, sb = b.span;
  const spanEq = (!sa && !sb) || (sa && sb && sa.text === sb.text &&
    sa.start === sb.start && sa.end === sb.end);
  return a.status === b.status && (a.note || "") === (b.note || "") &&
    (a.spanState || "ai") === (b.spanState || "ai") && spanEq;
}
function entriesFromExport(data){
  const reviews = {};
  Object.entries((data && data.cases) || {}).forEach(([caseId, c]) => {
    reviews[caseId] = {};
    Object.entries(c.fields || {}).forEach(([name, f]) => {
      reviews[caseId][name] = {
        status: f.reviewed ? f.human_status : null,
        note: f.note || "",
        spanState: f.evidence_source === "reviewer" ? "custom" :
                   f.evidence_cleared ? "cleared" : "ai",
        span: f.evidence_source === "reviewer" ? f.evidence : null
      };
    });
  });
  return reviews;
}
function isUnsynced(caseId, name){
  const local = mapEntry(state.reviews, caseId, name);
  if(isEmptyEnt(local)) return false;
  return !entEq(local, mapEntry(state.base, caseId, name));
}
function unsyncedCount(){
  let n = 0;
  DATA.cases.forEach(c => c.fields.forEach(fld => {
    if(isUnsynced(c.id, fld.name)) n++;
  }));
  return n;
}
function mergeServerEntries(serverEntries){
  DATA.cases.forEach(c => {
    c.fields.forEach(fld => {
      const local = mapEntry(state.reviews, c.id, fld.name);
      const base = mapEntry(state.base, c.id, fld.name);
      if(isEmptyEnt(local) || entEq(local, base)){
        /* No local divergence from the last synced state: the
           server's current word wins, including its absence (a
           newer submission elsewhere replaced the stored gold). */
        const srv = mapEntry(serverEntries, c.id, fld.name);
        if(srv){
          const byCase = state.reviews[c.id] || (state.reviews[c.id] = {});
          byCase[fld.name] = cloneEnt(srv);
        } else if(state.reviews[c.id]){
          delete state.reviews[c.id][fld.name];
        }
      }
      /* Otherwise the local edit is newer than the last sync: it
         stays untouched and isUnsynced() marks it until the next
         accepted submit. */
    });
  });
  state.base = cloneEntries(serverEntries);
}
function showStatus(text, cls){
  const box = document.getElementById("submitStatus");
  box.textContent = text;
  box.className = "show " + (cls || "");
}
function current(){
  const item = queue[pos];
  if(!item) return null;
  const c = DATA.cases[item.ci];
  return {case:c, field:c.fields[item.fi]};
}
function effectiveSpan(cur, ent){
  if(ent.spanState === "custom") return ent.span;
  if(ent.spanState === "cleared") return null;
  if(cur.field.evidence) return {text:cur.field.evidence, start:cur.field.ev_start, end:cur.field.ev_end};
  return null;
}
function buildQueue(){
  const f = document.getElementById("filter").value;
  queue = [];
  DATA.cases.forEach((c, ci) => {
    c.fields.forEach((fld, fi) => {
      const ent = (state.reviews[c.id] || {})[fld.name] || {};
      if(f === "unreviewed" && ent.status) return;
      if(f === "dev" && c.split !== "dev") return;
      if(f === "heldout" && c.split !== "heldout") return;
      queue.push({ci, fi});
    });
  });
  if(pos >= queue.length) pos = Math.max(0, queue.length - 1);
}
function esc(s){
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function render(){
  buildQueue();
  const cur = current();
  const done = countReviewed();
  document.getElementById("pfill").style.width = (100 * done / TOTAL) + "%";
  const bySplit = {dev:[0,0], heldout:[0,0]};
  DATA.cases.forEach(c => c.fields.forEach(fld => {
    bySplit[c.split][1]++;
    const ent = (state.reviews[c.id] || {})[fld.name] || {};
    if(ent.status) bySplit[c.split][0]++;
  }));
  const uns = unsyncedCount();
  document.getElementById("pnums").textContent =
    done + " of " + TOTAL + " fields reviewed · dev " + bySplit.dev[0] + "/" + bySplit.dev[1] +
    " · held out " + bySplit.heldout[0] + "/" + bySplit.heldout[1] +
    (queue.length ? " · field " + (pos + 1) + " of " + queue.length + " in view" : "") +
    (uns ? " · " + uns + " with unsubmitted changes (•)" : "");
  if(!cur){
    document.getElementById("caseTitle").textContent = "Nothing in this view";
    document.getElementById("transcript").textContent = "";
    return;
  }
  const ent = entry(cur.case.id, cur.field.name);
  document.getElementById("caseTitle").textContent =
    cur.case.business + " — " + cur.case.id;
  document.getElementById("caseSub").textContent =
    (cur.case.split === "heldout" ? "Held out split" : "Dev split") + " · " + cur.case.taxonomy +
    " · asked: “" + cur.case.question + "”";
  const span = effectiveSpan(cur, ent);
  const t = cur.case.transcript;
  const el = document.getElementById("transcript");
  if(span && span.start != null && t.substr(span.start, span.end - span.start) === span.text){
    el.innerHTML = esc(t.slice(0, span.start)) + "<mark>" + esc(span.text) + "</mark>" + esc(t.slice(span.end));
  } else if(span && span.text && t.indexOf(span.text) >= 0){
    const i = t.indexOf(span.text);
    el.innerHTML = esc(t.slice(0, i)) + "<mark>" + esc(span.text) + "</mark>" + esc(t.slice(i + span.text.length));
  } else {
    el.textContent = t;
  }
  document.getElementById("fName").textContent = cur.field.name;
  document.getElementById("fValue").textContent =
    cur.field.value === null ? "(not established)" : JSON.stringify(cur.field.value);
  document.getElementById("fAi").textContent = cur.field.ai_status + " (" + cur.field.ai_status_engine + ")";
  document.getElementById("fCondWrap").style.display = cur.field.condition ? "" : "none";
  document.getElementById("fCond").textContent = cur.field.condition || "";
  const eb = document.getElementById("evidenceBox");
  const em = document.getElementById("evMeta");
  if(span){
    eb.textContent = span.text;
    em.textContent = (ent.spanState === "custom" ? "Your selected span" :
      ent.spanState === "ai" ? "AI drafted span (accepted unless you change or clear it)" : "") +
      (span.start != null ? " · characters " + span.start + "–" + span.end : "");
  } else {
    eb.textContent = "No evidence span attached to this field.";
    em.textContent = ent.spanState === "cleared" ? "You cleared the AI drafted span." :
      "The AI drafted labels record no evidence for this field.";
  }
  document.querySelectorAll("#statusBtns button").forEach(b => {
    b.classList.toggle("active", ent.status === b.dataset.status);
  });
  const note = document.getElementById("note");
  if(note.value !== (ent.note || "")) note.value = ent.note || "";
  const sn = document.getElementById("syncNote");
  if(isUnsynced(cur.case.id, cur.field.name)){
    sn.style.display = "";
    sn.textContent = "This field has changes in this browser that are " +
      "not on the backend yet. They are kept; submit to store them.";
  } else {
    sn.style.display = "none";
  }
  const fl = document.getElementById("fieldList");
  fl.innerHTML = "";
  cur.case.fields.forEach((fld, fi) => {
    const e2 = (state.reviews[cur.case.id] || {})[fld.name] || {};
    const b = document.createElement("button");
    const uns = isUnsynced(cur.case.id, fld.name);
    b.textContent = fld.name + (e2.status ? " ✓" : "") + (uns ? " •" : "");
    if(e2.status) b.classList.add("done");
    if(uns) b.classList.add("unsynced");
    if(fld.name === cur.field.name) b.classList.add("current");
    b.addEventListener("click", () => {
      const idx = queue.findIndex(q => DATA.cases[q.ci].id === cur.case.id && q.fi === fi);
      if(idx >= 0){ pos = idx; render(); }
    });
    fl.appendChild(b);
  });
  document.getElementById("prevBtn").disabled = pos <= 0;
  document.getElementById("nextBtn").disabled = pos >= queue.length - 1;
}
function countReviewed(){
  let n = 0;
  DATA.cases.forEach(c => c.fields.forEach(fld => {
    const ent = (state.reviews[c.id] || {})[fld.name] || {};
    if(ent.status) n++;
  }));
  return n;
}
document.getElementById("statusBtns").addEventListener("click", e => {
  const b = e.target.closest("button[data-status]");
  if(!b) return;
  const cur = current(); if(!cur) return;
  entry(cur.case.id, cur.field.name).status = b.dataset.status;
  save(); render();
});
document.getElementById("note").addEventListener("input", e => {
  const cur = current(); if(!cur) return;
  entry(cur.case.id, cur.field.name).note = e.target.value;
  save();
  document.getElementById("pnums").textContent = document.getElementById("pnums").textContent;
});
document.getElementById("reviewer").addEventListener("input", save);
document.getElementById("filter").addEventListener("change", () => { pos = 0; render(); });
document.getElementById("prevBtn").addEventListener("click", () => { if(pos > 0){ pos--; render(); } });
document.getElementById("nextBtn").addEventListener("click", () => { if(pos < queue.length - 1){ pos++; render(); } });
document.getElementById("useSel").addEventListener("click", () => {
  const cur = current(); if(!cur) return;
  const container = document.getElementById("transcript");
  const sel = window.getSelection();
  if(!sel.rangeCount) return;
  const range = sel.getRangeAt(0);
  if(!container.contains(range.startContainer) || !container.contains(range.endContainer)) return;
  const pre = range.cloneRange();
  pre.selectNodeContents(container);
  pre.setEnd(range.startContainer, range.startOffset);
  const start = pre.toString().length;
  const text = range.toString();
  if(!text) return;
  const ent = entry(cur.case.id, cur.field.name);
  ent.span = {text:text, start:start, end:start + text.length};
  ent.spanState = "custom";
  save(); render();
});
document.getElementById("clearEv").addEventListener("click", () => {
  const cur = current(); if(!cur) return;
  const ent = entry(cur.case.id, cur.field.name);
  ent.span = null; ent.spanState = "cleared";
  save(); render();
});
document.getElementById("resetBtn").addEventListener("click", () => {
  if(!confirm("Discard all review decisions stored in this browser? The exported file, if you saved one, is unaffected.")) return;
  localStorage.removeItem(LS_KEY);
  state = {reviewer:"", reviews:{}, base:{}};
  document.getElementById("reviewer").value = "";
  pos = 0; render();
});
function exportData(){
  const cases = {};
  let reviewed = 0;
  DATA.cases.forEach(c => {
    const fields = {};
    c.fields.forEach(fld => {
      const ent = (state.reviews[c.id] || {})[fld.name] || {status:null, note:"", spanState:"ai", span:null};
      const isRev = !!ent.status;
      if(isRev) reviewed++;
      let evidence = null, source = "none";
      if(isRev){
        if(ent.spanState === "custom" && ent.span){ evidence = ent.span; source = "reviewer"; }
        else if(ent.spanState === "ai" && fld.evidence){
          evidence = {text:fld.evidence, start:fld.ev_start, end:fld.ev_end}; source = "ai_draft";
        }
      }
      fields[fld.name] = {
        value: fld.value,
        ai_status: fld.ai_status,
        human_status: isRev ? ent.status : null,
        reviewed: isRev,
        evidence: evidence,
        evidence_source: source,
        evidence_adjusted: ent.spanState === "custom",
        evidence_cleared: ent.spanState === "cleared",
        note: ent.note || ""
      };
    });
    cases[c.id] = {split: c.split, fields: fields};
  });
  return {
    dataset_version: "gold-v2-human-reviewed",
    source_version: "gold-v1-ai-drafted",
    reviewer: document.getElementById("reviewer").value || null,
    exported_at: new Date().toISOString(),
    fields_total: TOTAL,
    fields_reviewed: reviewed,
    cases: cases
  };
}
document.getElementById("exportBtn").addEventListener("click", () => {
  save();
  const blob = new Blob([JSON.stringify(exportData(), null, 2)], {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "gold_labels_v2.json";
  a.click();
  URL.revokeObjectURL(a.href);
});
const API_BASE = new URLSearchParams(window.location.search).get("api") ||
  "https://trutrace-production.up.railway.app";
document.getElementById("submitBtn").addEventListener("click", async () => {
  save();
  const show = showStatus;
  const payload = exportData();
  if(!payload.fields_reviewed){
    show("Nothing to submit yet: no field has a verdict. Your work is " +
      "saved in this browser as you go.", "err");
    return;
  }
  const btn = document.getElementById("submitBtn");
  btn.disabled = true;
  show("Submitting " + payload.fields_reviewed + " reviewed field(s) to " +
    "the backend…", "");
  try{
    const res = await fetch(API_BASE + "/api/gold/review", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const data = await res.json().catch(() => null);
    if(!res.ok){
      throw new Error((data && data.detail) || ("the backend answered HTTP " + res.status));
    }
    /* The backend now holds exactly this payload: it becomes the
       base the next load and every unsynced marker compare
       against. */
    state.base = entriesFromExport(payload);
    save(); render();
    show("Submitted and recorded by the backend: " + data.fields_reviewed +
      " of " + data.fields_total + " fields reviewed, stored as " +
      data.gold_version + " (recorded " +
      new Date(data.submitted_at).toLocaleString() + "). You can keep " +
      "reviewing and submit again; the newest submission is the " +
      "current human gold.", "ok");
  }catch(err){
    show("Submission failed: " + err.message + " Your decisions are " +
      "still saved in this browser; export the file as a fallback and " +
      "try submitting again later.", "err");
  }finally{
    btn.disabled = false;
  }
});
document.getElementById("importBtn").addEventListener("click", () =>
  document.getElementById("importFile").click());
document.getElementById("importFile").addEventListener("change", e => {
  const file = e.target.files[0];
  if(!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try{
      const data = JSON.parse(reader.result);
      state = {
        reviewer: data.reviewer || "",
        reviews: entriesFromExport(data),
        base: state.base || {}
      };
      document.getElementById("reviewer").value = state.reviewer;
      save(); pos = 0; render();
    }catch(err){ alert("Could not read that export: " + err.message); }
  };
  reader.readAsText(file);
});
document.addEventListener("keydown", e => {
  const tag = (e.target.tagName || "").toLowerCase();
  if(tag === "textarea" || tag === "input" || tag === "select") return;
  if(e.key === "ArrowRight") document.getElementById("nextBtn").click();
  if(e.key === "ArrowLeft") document.getElementById("prevBtn").click();
});
async function seedFromServer(){
  let data;
  try{
    const res = await fetch(API_BASE + "/api/gold/review");
    if(!res.ok) throw new Error("the backend answered HTTP " + res.status);
    data = await res.json();
  }catch(err){
    showStatus("Server state could not be loaded: " + err.message +
      ". Showing your local draft instead; your work is still saved " +
      "in this browser, and nothing was submitted.", "err");
    return;
  }
  if(!data.submission){
    showStatus("No review has been submitted to the backend yet; " +
      "you are starting from your local draft.", "");
    return;
  }
  const sub = data.submission;
  mergeServerEntries(entriesFromExport(sub.payload));
  if(!document.getElementById("reviewer").value && sub.reviewer){
    state.reviewer = sub.reviewer;
    document.getElementById("reviewer").value = sub.reviewer;
  }
  save(); render();
  const uns = unsyncedCount();
  showStatus("Loaded the review stored on the backend: " +
    sub.fields_reviewed + " of " + sub.fields_total + " fields " +
    "reviewed" + (sub.reviewer ? ", submitted by " + sub.reviewer : "") +
    " (" + new Date(sub.submitted_at).toLocaleString() + "). Those " +
    "fields open filled in." +
    (uns ? " " + uns + " field(s) in this browser carry newer " +
      "unsubmitted changes; they were kept and are marked •." : ""), "ok");
}
document.getElementById("reviewer").value = state.reviewer || "";
render();
seedFromServer();
</script>
</body>
</html>
"""


def main():
    data = build_data()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = HTML.replace("__DATA__", payload)
    path = os.path.join(HERE, "gold_review.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(out)
    print(
        f"wrote {path}: {len(data['cases'])} cases, "
        f"{data['fields_total']} fields"
    )


if __name__ == "__main__":
    main()
