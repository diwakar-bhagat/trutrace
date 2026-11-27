# TruTrace benchmark results

TruTrace turns seller-call transcripts into structured answers where every field carries a status (confirmed, uncertain, unconfirmed, conflicting) and the transcript span that proves it. This report is the measured record of one thin slice of that system: a florist campaign, a held-out eval set, a provider failure, and three load runs. Every number below comes from a recorded run artifact in `evals/results/`; counts are given with denominators, and model configurations were run three times each so the spread is visible.

## Methodology, before any numbers

- **Split.** The 32-case dataset is frozen into 20 dev and 12 held-out cases (`datasets/SPLIT.md`, `datasets/split.json`). Final numbers come from the held-out 12 only. The 10 campaign transcripts are a separate slice and were never tuned against.
- **Disclosure.** The split was frozen after a first build round whose fixes were driven by failures seen across all 32 cases (offline timing patterns, the conditional-pricing discriminator, two stopwords, the currency-evidence fallback). The held-out numbers are therefore not a clean-room measurement. Post-freeze changes are feature work (proof fields, provider fallback, reporting), not tuning.
- **Runs.** Each configuration (provider x baseline/current) was run 3 times per eval set at temperature 0. Two first attempts at held-out gpt-4o-mini runs stopped on an HTTP 429 rate limit; they were re-run once after the limit cleared, and the errored attempts are preserved in `evals/results/` with `_error429` in the filename.
- **Authorship.** The transcripts and gold labels in this repository were drafted by an AI coding agent during the build and are pending Diwakar Bhagat's human review. Gold is one annotator's judgement, unreviewed.
- **Prices.** Cost is computed from returned token counts at published OpenRouter list prices (November 2026): gpt-4o-mini $0.15 in / $0.60 out per 1M tokens; gemini-2.0-flash-001 $0.10 in / $0.40 out. In every completed gpt-4o-mini run the computed cost matched the provider-reported cost.

## The campaign slice

One query, run against ten synthetic florist sellers: **"Red roses, a dozen, delivery today"**. The transcripts carry [mm:ss] speaker labels, ASR-style noise (fillers, a misheard word, an [inaudible]) and hedged answers. Every field of every answer returns its status plus its proof: the span, the speaker, the timestamp.

### The failing case, on one transcript

Campaign call 01, seller Bloom & Co. The seller says, at [00:07]: "Uh, red roses, a dozen is around $35, I think." At [00:13]: "They are usually in stock, we get them most mornings." At [00:19]: "Delivery today, uh, probably tomorrow morning is safer, to be honest."

| field | naive baseline | TruTrace (current) |
|---|---|---|
| price | $35, **confirmed** | $35, **uncertain**: quoted as an approximate price |
| availability | in stock, **confirmed** | in stock, **uncertain**: hedged in the call ('usually') |
| timing | tomorrow morning, **confirmed** | tomorrow morning, **uncertain**: hedged in the call ('probably') |

Same transcript, same extractor. The baseline asserts the hedges as facts; the verification layer demotes them and keeps the evidence attached (Seller, [00:07] / [00:13] / [00:19]). This contrast is pinned by an automated test (`tests/test_campaign.py`).

### Campaign results (10 calls, 70 fields, 3 runs per configuration)

| provider · configuration | extraction accuracy | unsupported claims | contradiction recall | p50 latency | p95 latency | cost per transcript |
|---|---|---|---|---|---|---|
| offline · baseline | 52 of 70, 52 of 70, 52 of 70 (74.3%) | 9 of 39, 9 of 39, 9 of 39 (23.1%) | 0 of 1, 0 of 1, 0 of 1 | 0.36 ms | 1.81 ms | — |
| offline · current | 56 of 70, 56 of 70, 56 of 70 (80.0%) | 4 of 34, 4 of 34, 4 of 34 (11.8%) | 1 of 1, 1 of 1, 1 of 1 | 0.46 ms | 0.87 ms | — |
| gpt-4o-mini · baseline | 40 of 70, 38 of 70, 40 of 70 (56.2% (range 54.3%–57.1%)) | 30 of 63, 32 of 65, 30 of 63 (48.2% (range 47.6%–49.2%)) | 0 of 1, 0 of 1, 0 of 1 | 2116 ms | 2422 ms | $0.000079 |
| gpt-4o-mini · current | 55 of 70, 55 of 70, 56 of 70 (79.0% (range 78.6%–80.0%)) | 12 of 41, 12 of 41, 11 of 40 (28.7% (range 27.5%–29.3%)) | 1 of 1, 1 of 1, 1 of 1 | 3699 ms | 4592 ms | $0.000184 |

Proof completeness on the campaign: the current gpt-4o-mini configuration returns speaker and timestamp proof matching gold on 37 of 41 gold-confirmed fields; the naive baseline returns 0 of 41, because its prompt never asks for evidence. The offline provider matches on 30 of 41 in both configurations; its misses are fields it did not confirm at all, not wrong proof.

Where the campaign is hard, honestly: the ASR-noise call (prices spoken in words, "thirty-eight dollars") defeats the rule-based offline extractor almost completely, and the conditional call turns on whether an unqualified request means the standard dozen, a judgement the offline engine resolves as a conflict and gold resolves as the standard dozen with its condition attached. Both failures are in the recorded scorecards, uncorrected.

## Benchmark: held-out set

### Held-out results (12 cases, 84 fields, 3 runs per configuration)

| provider · configuration | extraction accuracy | unsupported claims | contradiction recall | p50 latency | p95 latency | cost per transcript |
|---|---|---|---|---|---|---|
| offline · baseline | 74 of 84, 74 of 84, 74 of 84 (88.1%) | 10 of 50, 10 of 50, 10 of 50 (20.0%) | 0 of 2, 0 of 2, 0 of 2 | 0.27 ms | 1.16 ms | — |
| offline · current | 84 of 84, 84 of 84, 84 of 84 (100.0%) | 0 of 45, 0 of 45, 0 of 45 (0.0%) | 2 of 2, 2 of 2, 2 of 2 | 0.40 ms | 0.62 ms | — |
| gpt-4o-mini · baseline | 61 of 84, 61 of 84, 61 of 84 (72.6%) | 23 of 58, 23 of 59, 23 of 58 (39.4% (range 39.0%–39.7%)) | 0 of 2, 0 of 2, 0 of 2 | 1876 ms | 2691 ms | $0.000071 |
| gpt-4o-mini · current | 68 of 84, 69 of 84, 65 of 84 (80.2% (range 77.4%–82.1%)) | 11 of 43, 12 of 44, 11 of 39 (27.0% (range 25.6%–28.2%)) | 1 of 2, 1 of 2, 1 of 2 | 3330 ms | 4437 ms | $0.000164 |

Reading the table: the baseline's failure mode is confident assertion. On gpt-4o-mini it confirms 58 to 59 of 84 fields and roughly 23 of those confirmations are claims gold does not support. The current configuration confirms fewer fields (39 to 44) and cuts unsupported claims to 11 or 12, while accuracy rises because the fields it does assert are the right ones, and the ones it refuses to assert stop counting as confident errors. The offline provider shows the same shape at smaller scale, and its current configuration is clean on this set (0 of 45 unsupported) — with the caveat that the offline rules and the dataset grew up together, so that row shows self-consistency, not real-world accuracy. The model rows are the independent check.

**Gemini did not run.** Both gemini-2.0-flash-001 configurations stopped on the first call: OpenRouter returned HTTP 404 for that model id. The runs were stopped rather than retried in a loop or silently re-pointed at a different model; the scorecard files record the error.

## Degradation: a provider dies mid run

Recorded by `scripts/degradation_demo.py` (and covered by automated tests in `tests/test_degradation.py`). The provider death is simulated with a wrapper that raises after a set number of calls; the fallback behaviour is the pipeline's own code path.

- **Killed mid run.** Primary provider (gpt-4o-mini) dies after 3 of 6 campaign calls. Result: 3 of 6 served by the primary, 3 of 6 fell back to the offline provider, 0 of 6 lost. The batch completed with partial results preserved.
- **Everything down.** Primary and fallback both dead from the start. Result: 6 of 6 came back with every field unconfirmed and the failure recorded on the result. No exception escaped the pipeline, and no answer was invented.

## Load, measured and labelled

| run | kind | wall time | throughput | error rate | latency p50 / p95 | cost |
|---|---|---|---|---|---|---|
| 10 transcripts | real, sequential calls to gpt-4o-mini via the OpenRouter helper | 34.6 s | 0.289 transcripts/s | 0 of 10 (0.0%) | 3477 ms / 4423 ms | $0.0019 total, $0.000186 per transcript |
| 100 transcripts | real, sequential calls to gpt-4o-mini via the OpenRouter helper | 374.32 s | 0.267 transcripts/s | 0 of 100 (0.0%) | 3689 ms / 5100 ms | $0.0184 total, $0.000184 per transcript |
| 1000 transcripts | simulated (see below) | 0.39 s | 2535.153 transcripts/s | 0 of 1000 (0.0%) | 0.38 ms / 0.52 ms | no provider cost (offline) |

What was mocked in the 1000 run, in one sentence: the pipeline code ran for real in-process, but the provider was the deterministic offline rule engine, so no network calls were made and the latencies are rule-engine times, not a live model's. The 10 and 100 runs are sequential, so their throughput is a floor set by one call at a time, not a concurrency figure.

## What breaks next

This is a single-process slice. In order, what a real calling workload would break first:

- **Queueing.** Calls arrive in bursts (a campaign dials in parallel) and the pipeline is sequential code. A queue with backpressure goes in front of extraction before anything else matters; without it, a burst is just a longer wait or a dropped batch.
- **Idempotent retries.** Provider calls fail transiently (this project's own eval runs hit an HTTP 429). A retry that is not idempotent can extract the same call twice and bill twice; retries need a per-transcript idempotency key and a record of completed extractions to resume from.
- **Per-seller concurrency caps.** One seller's calls are independent, but a provider account is not: uncapped parallelism across sellers spends the shared rate limit on whoever shouts first. Caps per seller, and a global budget per provider, keep one campaign from starving the rest.
- **Partial results.** A batch where 6 of 10 calls verify and 4 come back unconfirmed is a normal outcome, not an error, and the degradation run shows the shape of it. Downstream consumers need to treat per-field status as the contract, because 'the batch succeeded' will often mean 'most of it did'.

## Limits

- The transcripts are synthetic, written for this project. They are not recordings of real calls.
- There is no live audio anywhere in the system: no speech recognition, no audio pipeline. The ASR noise in the campaign transcripts is written text imitating recognition errors.
- There is no real telephony: no dialling, no call recording, no carrier integration. The campaign is a set of transcripts, not a set of calls that were placed.
- Gold labels are one annotator's judgement, drafted by an AI coding agent during the build and pending human review (see Methodology). Arguable calls exist, and the scoring treats a hedged value as not confirmed even when it later turns out right, because the promise is verified answers, not lucky ones.
- The dataset is small (32 cases plus 10 campaign transcripts) and the offline provider was built alongside it. Nothing here estimates accuracy on real seller calls.
