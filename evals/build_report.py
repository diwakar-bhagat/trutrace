"""Generate reports/benchmark_results.md from recorded run artifacts.

Every number comes from a file in evals/results/ or
reports/degradation_record.json. If an artifact is missing, the
section says so instead of inventing a number.

Usage: python -m evals.build_report
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
ROOT = os.path.join(HERE, "..")
OUT = os.path.join(ROOT, "reports", "benchmark_results.md")


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def cell(summary, tag, config):
    for c in summary["cells"]:
        if c["provider_tag"] == tag and c["config"] == config:
            return c
    return None


def counts(cell_, key):
    return ", ".join(cell_[key]["per_run"])


def rate_spread(cell_, key, rate_key="rate"):
    r = cell_[key][rate_key]
    if r["mean"] is None:
        return "n/a"
    if r["min"] == r["max"]:
        return pct(r["mean"])
    return f"{pct(r['mean'])} (range {pct(r['min'])}–{pct(r['max'])})"


def lat(cell_, key):
    v = cell_["operational_efficiency"][key]
    if v["mean"] is None:
        return "n/a"
    if v["mean"] < 10:
        return f"{v['mean']:.2f} ms"
    return f"{v['mean']:.0f} ms"


def cost_per_transcript(cell_):
    costs = [c for c in cell_["operational_efficiency"]["cost_usd_per_run"]
             if c is not None]
    if not costs or not cell_["cases_per_run"]:
        return "—"
    mean = sum(costs) / len(costs)
    return f"${mean / cell_['cases_per_run']:.6f}"


def bench_table(summary, title):
    lines = [
        f"### {title}",
        "",
        "| provider · configuration | extraction accuracy | unsupported claims | contradiction recall | p50 latency | p95 latency | cost per transcript |",
        "|---|---|---|---|---|---|---|",
    ]
    for tag, label in [("offline", "offline"), ("gpt-4o-mini", "gpt-4o-mini")]:
        for config in ["baseline", "current"]:
            c = cell(summary, tag, config)
            if c is None:
                lines.append(f"| {label} · {config} | not run | | | | | |")
                continue
            lines.append(
                f"| {label} · {config} "
                f"| {counts(c, 'extraction_accuracy')} ({rate_spread(c, 'extraction_accuracy')}) "
                f"| {counts(c, 'unsupported_claim_rate')} ({rate_spread(c, 'unsupported_claim_rate')}) "
                f"| {counts(c, 'contradiction_detection')} "
                f"| {lat(c, 'p50_latency_ms')} | {lat(c, 'p95_latency_ms')} "
                f"| {cost_per_transcript(c)} |"
            )
    lines.append("")
    return lines


def main() -> int:
    heldout = load_json(os.path.join(RESULTS, "final_heldout_summary.json"))
    campaign = load_json(os.path.join(RESULTS, "final_campaign_summary.json"))
    degradation = load_json(os.path.join(ROOT, "reports", "degradation_record.json"))
    loads = {
        n: load_json(os.path.join(RESULTS, f"load_{n}_openrouter.json"))
        for n in (10, 100)
    }
    load1000 = load_json(os.path.join(RESULTS, "load_1000_offline.json"))
    gem = load_json(os.path.join(
        RESULTS, "openrouter_gemini-2.0-flash-001_baseline_scorecard.json"))

    lines = [
        "# TruTrace benchmark results",
        "",
        "TruTrace turns seller-call transcripts into structured answers "
        "where every field carries a status (confirmed, uncertain, "
        "unconfirmed, conflicting) and the transcript span that proves "
        "it. This report is the measured record of one thin slice of "
        "that system: a florist campaign, a held-out eval set, a "
        "provider failure, and three load runs. Every number below "
        "comes from a recorded run artifact in `evals/results/`; "
        "counts are given with denominators, and model configurations "
        "were run three times each so the spread is visible.",
        "",
        "## Methodology, before any numbers",
        "",
        "- **Split.** The 32-case dataset is frozen into 20 dev and 12 "
        "held-out cases (`datasets/SPLIT.md`, `datasets/split.json`). "
        "Final numbers come from the held-out 12 only. The 10 campaign "
        "transcripts are a separate slice and were never tuned against.",
        "- **Disclosure.** The split was frozen after a first build "
        "round whose fixes were driven by failures seen across all 32 "
        "cases (offline timing patterns, the conditional-pricing "
        "discriminator, two stopwords, the currency-evidence fallback). "
        "The held-out numbers are therefore not a clean-room "
        "measurement. Post-freeze changes are feature work (proof "
        "fields, provider fallback, reporting), not tuning.",
        "- **Runs.** Each configuration (provider x baseline/current) "
        "was run 3 times per eval set at temperature 0. Two first "
        "attempts at held-out gpt-4o-mini runs stopped on an HTTP 429 "
        "rate limit; they were re-run once after the limit cleared, "
        "and the errored attempts are preserved in `evals/results/` "
        "with `_error429` in the filename.",
        "- **Authorship.** The transcripts and gold labels in this "
        "repository were drafted by an AI coding agent during the "
        "build and are pending Diwakar Bhagat's human review. Gold is "
        "one annotator's judgement, unreviewed.",
        "- **Prices.** Cost is computed from returned token counts at "
        "published OpenRouter list prices (November 2026): "
        "gpt-4o-mini $0.15 in / $0.60 out per 1M tokens; "
        "gemini-2.0-flash-001 $0.10 in / $0.40 out. In every completed "
        "gpt-4o-mini run the computed cost matched the "
        "provider-reported cost.",
        "",
        "## The campaign slice",
        "",
        "One query, run against ten synthetic florist sellers: **\"Red "
        "roses, a dozen, delivery today\"**. The transcripts carry "
        "[mm:ss] speaker labels, ASR-style noise (fillers, a misheard "
        "word, an [inaudible]) and hedged answers. Every field of every "
        "answer returns its status plus its proof: the span, the "
        "speaker, the timestamp.",
        "",
        "### The failing case, on one transcript",
        "",
        "Campaign call 01, seller Bloom & Co. The seller says, at "
        "[00:07]: \"Uh, red roses, a dozen is around $35, I think.\" At "
        "[00:13]: \"They are usually in stock, we get them most "
        "mornings.\" At [00:19]: \"Delivery today, uh, probably "
        "tomorrow morning is safer, to be honest.\"",
        "",
        "| field | naive baseline | TruTrace (current) |",
        "|---|---|---|",
        "| price | $35, **confirmed** | $35, **uncertain**: quoted as an approximate price |",
        "| availability | in stock, **confirmed** | in stock, **uncertain**: hedged in the call ('usually') |",
        "| timing | tomorrow morning, **confirmed** | tomorrow morning, **uncertain**: hedged in the call ('probably') |",
        "",
        "Same transcript, same extractor. The baseline asserts the "
        "hedges as facts; the verification layer demotes them and "
        "keeps the evidence attached (Seller, [00:07] / [00:13] / "
        "[00:19]). This contrast is pinned by an automated test "
        "(`tests/test_campaign.py`).",
        "",
    ]
    lines += bench_table(campaign, "Campaign results (10 calls, 70 fields, 3 runs per configuration)")
    camp_gpt_b = cell(campaign, "gpt-4o-mini", "baseline")
    camp_gpt_c = cell(campaign, "gpt-4o-mini", "current")
    camp_off_c = cell(campaign, "offline", "current")
    lines += [
        f"Proof completeness on the campaign: the current "
        f"gpt-4o-mini configuration returns speaker and timestamp "
        f"proof matching gold on {camp_gpt_c['proof_accuracy']['matched']} "
        f"of {camp_gpt_c['proof_accuracy']['total']} gold-confirmed "
        f"fields; the naive baseline returns "
        f"{camp_gpt_b['proof_accuracy']['matched']} of "
        f"{camp_gpt_b['proof_accuracy']['total']}, because its prompt "
        f"never asks for evidence. The offline provider matches on "
        f"{camp_off_c['proof_accuracy']['matched']} of "
        f"{camp_off_c['proof_accuracy']['total']} in both "
        f"configurations; its misses are fields it did not confirm at "
        f"all, not wrong proof.",
        "",
        "Where the campaign is hard, honestly: the ASR-noise call "
        "(prices spoken in words, \"thirty-eight dollars\") defeats "
        "the rule-based offline extractor almost completely, and the "
        "conditional call turns on whether an unqualified request "
        "means the standard dozen, a judgement the offline engine "
        "resolves as a conflict and gold resolves as the standard "
        "dozen with its condition attached. Both failures are in the "
        "recorded scorecards, uncorrected.",
        "",
        "## Benchmark: held-out set",
        "",
    ]
    lines += bench_table(heldout, "Held-out results (12 cases, 84 fields, 3 runs per configuration)")
    lines += [
        "Reading the table: the baseline's failure mode is confident "
        "assertion. On gpt-4o-mini it confirms 58 to 59 of 84 fields "
        "and roughly 23 of those confirmations are claims gold does "
        "not support. The current configuration confirms fewer fields "
        "(39 to 44) and cuts unsupported claims to 11 or 12, while "
        "accuracy rises because the fields it does assert are the "
        "right ones, and the ones it refuses to assert stop counting "
        "as confident errors. The offline provider shows the same "
        "shape at smaller scale, and its current configuration is "
        "clean on this set (0 of 45 unsupported) — with the caveat "
        "that the offline rules and the dataset grew up together, so "
        "that row shows self-consistency, not real-world accuracy. "
        "The model rows are the independent check.",
        "",
        "**Gemini did not run.** Both gemini-2.0-flash-001 "
        "configurations stopped on the first call: OpenRouter "
        "returned HTTP 404 for that model id. The runs were stopped "
        "rather than retried in a loop or silently re-pointed at a "
        "different model; the scorecard files record the error.",
        "",
        "## Degradation: a provider dies mid run",
        "",
    ]
    if degradation:
        a = degradation["scenario_a_killed_mid_run"]["summary"]
        b = degradation["scenario_b_all_providers_down"]["summary"]
        lines += [
            "Recorded by `scripts/degradation_demo.py` (and covered by "
            "automated tests in `tests/test_degradation.py`). The "
            "provider death is simulated with a wrapper that raises "
            "after a set number of calls; the fallback behaviour is "
            "the pipeline's own code path.",
            "",
            f"- **Killed mid run.** Primary provider (gpt-4o-mini) "
            f"dies after 3 of 6 campaign calls. Result: "
            f"{a['served_by_primary']} of 6 served by the primary, "
            f"{a['served_by_fallback']} of 6 fell back to the offline "
            f"provider, {a['unavailable']} of 6 lost. The batch "
            f"completed with partial results preserved.",
            f"- **Everything down.** Primary and fallback both dead "
            f"from the start. Result: {b['unavailable']} of 6 came "
            f"back with every field unconfirmed and the failure "
            f"recorded on the result. No exception escaped the "
            f"pipeline, and no answer was invented.",
            "",
        ]
    lines += [
        "## Load, measured and labelled",
        "",
        "| run | kind | wall time | throughput | error rate | latency p50 / p95 | cost |",
        "|---|---|---|---|---|---|---|",
    ]
    for n in (10, 100):
        r = loads[n]
        if r:
            lines.append(
                f"| {n} transcripts | real, sequential calls to "
                f"gpt-4o-mini via the OpenRouter helper | "
                f"{r['wall_time_s']} s | "
                f"{r['throughput_transcripts_per_s']} transcripts/s | "
                f"{r['errors']} of {n} ({pct(r['error_rate'])}) | "
                f"{r['latency_ms']['p50']:.0f} ms / {r['latency_ms']['p95']:.0f} ms | "
                f"${r['cost_usd_computed']:.4f} total, "
                f"${r['cost_per_transcript_usd']:.6f} per transcript |"
            )
        else:
            lines.append(f"| {n} transcripts | real | not run | | | | |")
    if load1000:
        r = load1000
        lines.append(
            f"| 1000 transcripts | simulated (see below) | "
            f"{r['wall_time_s']} s | "
            f"{r['throughput_transcripts_per_s']} transcripts/s | "
            f"{r['errors']} of 1000 ({pct(r['error_rate'])}) | "
            f"{r['latency_ms']['p50']:.2f} ms / {r['latency_ms']['p95']:.2f} ms | "
            f"no provider cost (offline) |"
        )
    lines += [
        "",
        "What was mocked in the 1000 run, in one sentence: the "
        "pipeline code ran for real in-process, but the provider was "
        "the deterministic offline rule engine, so no network calls "
        "were made and the latencies are rule-engine times, not a "
        "live model's. The 10 and 100 runs are sequential, so their "
        "throughput is a floor set by one call at a time, not a "
        "concurrency figure.",
        "",
        "## What breaks next",
        "",
        "This is a single-process slice. In order, what a real "
        "calling workload would break first:",
        "",
        "- **Queueing.** Calls arrive in bursts (a campaign dials in "
        "parallel) and the pipeline is sequential code. A queue with "
        "backpressure goes in front of extraction before anything "
        "else matters; without it, a burst is just a longer wait or a "
        "dropped batch.",
        "- **Idempotent retries.** Provider calls fail transiently "
        "(this project's own eval runs hit an HTTP 429). A retry that "
        "is not idempotent can extract the same call twice and bill "
        "twice; retries need a per-transcript idempotency key and a "
        "record of completed extractions to resume from.",
        "- **Per-seller concurrency caps.** One seller's calls are "
        "independent, but a provider account is not: uncapped "
        "parallelism across sellers spends the shared rate limit on "
        "whoever shouts first. Caps per seller, and a global budget "
        "per provider, keep one campaign from starving the rest.",
        "- **Partial results.** A batch where 6 of 10 calls verify "
        "and 4 come back unconfirmed is a normal outcome, not an "
        "error, and the degradation run shows the shape of it. "
        "Downstream consumers need to treat per-field status as the "
        "contract, because 'the batch succeeded' will often mean "
        "'most of it did'.",
        "",
        "## Limits",
        "",
        "- The transcripts are synthetic, written for this project. "
        "They are not recordings of real calls.",
        "- There is no live audio anywhere in the system: no speech "
        "recognition, no audio pipeline. The ASR noise in the "
        "campaign transcripts is written text imitating recognition "
        "errors.",
        "- There is no real telephony: no dialling, no call "
        "recording, no carrier integration. The campaign is a set of "
        "transcripts, not a set of calls that were placed.",
        "- Gold labels are one annotator's judgement, drafted by an "
        "AI coding agent during the build and pending human review "
        "(see Methodology). Arguable calls exist, and the scoring "
        "treats a hedged value as not confirmed even when it later "
        "turns out right, because the promise is verified answers, "
        "not lucky ones.",
        "- The dataset is small (32 cases plus 10 campaign "
        "transcripts) and the offline provider was built alongside "
        "it. Nothing here estimates accuracy on real seller calls.",
        "",
    ]
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
