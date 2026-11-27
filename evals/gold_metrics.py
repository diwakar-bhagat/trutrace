"""Verification-decision metrics against a named gold-label version.

The benchmark's five metrics (evals/run_evals.py) say how a run
scored. This harness answers a different question: when TruTrace
issues a verification decision, how often is that decision right,
measured against a specific, versioned set of gold labels?

    precision            of the fields a run asserts as confirmed,
                         the share gold confirms with the same value
                         and condition (a true verification)
    recall               of the fields gold confirms, the share the
                         run confirms correctly
    false positive rate  of the fields gold marks unconfirmed or
                         conflicting, the share the run asserts as
                         confirmed anyway
    false negative rate  of the fields gold confirms, the share the
                         run fails to confirm correctly (= 1 - recall)
    evidence accuracy    of the fields where both gold and the run
                         cite an evidence span, the share where the
                         cited span matches the gold span
    abstention quality   gold uncertain and gold unconfirmed fields,
                         reported as their own blocks: how the run
                         handled them (abstained, asserted, other).
                         These are NEVER folded into the positive or
                         negative classes above: a gold uncertain
                         field is not a negative, and asserting it is
                         reported both as an unsupported claim (it
                         lowers precision, because the run did assert
                         it) and as an abstention failure.

Status vocabulary: gold labels and predictions use the engine's four
statuses (confirmed / uncertain / unconfirmed / conflicting). The
review protocol's terms map onto them: supported = confirmed,
unsupported = unconfirmed, contradictory = conflicting, uncertain =
uncertain. A human-reviewed export (gold_labels_v2.json from
tools/gold_review.html) is translated through that mapping.

HONESTY RULE: every report names the gold version it scored against.
Against gold-v1-ai-drafted the numbers measure AGREEMENT WITH
AI-DRAFTED LABELS, not validated correctness: the labels were drafted
by an AI coding agent and are pending Diwakar Bhagat's human review
(see GOLD_REVIEW.md). Only a human-reviewed gold version turns these
into correctness measurements.

The harness scores RECORDED runs only; it never calls a model. It
reads the eval suite's result files (evals/results/final_*.json) and
workbench run directories (runs/<run_id>/ with run.json +
cases.jsonl).

Usage:
    python -m evals.gold_metrics
    python -m evals.gold_metrics --gold gold_labels_v2.json
    python -m evals.gold_metrics --results evals/results/final_heldout_offline_current_run1.json runs/20261127-050338_trutrace-1.0.0_offline_campaign
"""

import argparse
import glob
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evals.metrics import field_correct, is_unsupported_claim  # noqa: E402
from evals.run_evals import load_case_dir, load_cases  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

GOLD_VERSION_AI_DRAFTED = "gold-v1-ai-drafted"

PROTOCOL_TO_ENGINE = {
    "supported": "confirmed",
    "uncertain": "uncertain",
    "unsupported": "unconfirmed",
    "contradictory": "conflicting",
}
ENGINE_TO_PROTOCOL = {v: k for k, v in PROTOCOL_TO_ENGINE.items()}


# ---------------------------------------------------------------- gold book --

class GoldBook:
    """Gold labels from one versioned source.

    The base layer is the frozen dataset (gold-v1-ai-drafted). A
    human-reviewed export overlays the fields a reviewer actually
    decided; unreviewed fields keep the AI-drafted label and the
    coverage counts say how much of the set the overlay covers.
    """

    def __init__(self):
        self.version = GOLD_VERSION_AI_DRAFTED
        self.provenance = "ai-drafted"
        self.reviewer = None
        self.exported_at = None
        self.reviewed_fields = 0
        self.total_fields = 0
        self._fields = {}  # (case_id, field) -> dict

    @classmethod
    def from_dataset(cls):
        book = cls()
        for doc in load_cases():
            book._add_doc(doc)
        campaign_dir = os.path.join(ROOT, "datasets", "campaign")
        if os.path.isdir(campaign_dir):
            for doc in load_case_dir(campaign_dir):
                book._add_doc(doc)
        book.total_fields = len(book._fields)
        return book

    def _add_doc(self, doc):
        for name, gold in doc.gold.items():
            self._fields[(doc.id, name)] = {
                "value": gold.value,
                "status": gold.status.value,
                "evidence": gold.evidence,
                "condition": gold.condition,
                "reviewed": False,
            }

    def overlay_export(self, path):
        with open(path, encoding="utf-8") as fh:
            export = json.load(fh)
        return self.overlay_export_data(export)

    def overlay_export_data(self, export):
        """Overlay a human-reviewed export already parsed into a
        dict (the shape tools/gold_review.html exports and
        POST /api/gold/review stores). Same semantics as
        overlay_export: only fields the reviewer actually decided
        are replaced."""
        self.version = export.get("dataset_version", "gold-v2-human-reviewed")
        self.provenance = "human-reviewed"
        self.reviewer = export.get("reviewer")
        self.exported_at = export.get("exported_at")
        reviewed = 0
        for case_id, case in (export.get("cases") or {}).items():
            for name, entry in (case.get("fields") or {}).items():
                if not entry.get("reviewed") or not entry.get("human_status"):
                    continue
                key = (case_id, name)
                base = self._fields.get(key, {})
                evidence = entry.get("evidence") or {}
                self._fields[key] = {
                    "value": base.get("value"),
                    "status": PROTOCOL_TO_ENGINE[entry["human_status"]],
                    "evidence": evidence.get("text"),
                    "condition": base.get("condition"),
                    "reviewed": True,
                }
                reviewed += 1
        self.reviewed_fields = reviewed
        return self

    def get(self, case_id, field):
        return self._fields.get((case_id, field))

    def reviewed_keys(self):
        """The (case_id, field) pairs a human reviewer actually
        decided in the overlay. Empty for the AI drafted book."""
        return {
            key for key, entry in self._fields.items()
            if entry.get("reviewed")
        }


def load_gold(path=None):
    book = GoldBook.from_dataset()
    if path:
        book.overlay_export(path)
    return book


# ------------------------------------------------------------ result loaders --

def _row(config, case_id, field, gold, pred):
    return {
        "config": config,
        "case_id": case_id,
        "field": field,
        "gold_status": gold.get("status"),
        "gold_value": gold.get("value"),
        "gold_condition": gold.get("condition"),
        "gold_evidence": gold.get("evidence"),
        "pred_status": pred.get("status"),
        "pred_value": pred.get("value"),
        "pred_condition": pred.get("condition"),
        "pred_evidence": pred.get("evidence"),
    }


def rows_from_final_results(path, gold_book):
    """evals/results/final_*.json: per-case field rows with embedded
    gold status/value (no evidence spans in this format). Gold comes
    from the gold book when the case is in it, so a human-reviewed
    version re-scores the recorded predictions."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    label = " / ".join(
        str(x) for x in (data.get("provider"), data.get("model"),
                         data.get("config") or data.get("prompt_version"))
        if x
    )
    rows = []
    for case in data.get("cases", []):
        for field, f in case.get("fields", {}).items():
            gold = gold_book.get(case["id"], field) or {
                "value": f.get("gold_value"),
                "status": f.get("gold_status"),
                "evidence": None,
                "condition": None,
            }
            pred = {
                "value": f.get("pred_value"),
                "status": f.get("pred_status"),
                "condition": f.get("pred_condition"),
                "evidence": None,
            }
            rows.append(_row(label, case["id"], field, gold, pred))
    return rows


def rows_from_workbench_run(run_dir, gold_book):
    """runs/<run_id>/: run.json + cases.jsonl traces carry the full
    gold and predicted field objects, evidence spans included."""
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as fh:
        run = json.load(fh)
    label = " / ".join(
        str(x) for x in (run.get("provider"), run.get("model"),
                         (run.get("prompt") or {}).get("key"))
        if x
    )
    rows = []
    cases_path = os.path.join(run_dir, "cases.jsonl")
    with open(cases_path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            trace = json.loads(line)
            evaluations = trace.get("evaluations") or {}
            for field, f in (evaluations.get("fields") or {}).items():
                gold = gold_book.get(trace["case_id"], field) or f["gold"]
                rows.append(
                    _row(label, trace["case_id"], field, gold, f["predicted"])
                )
    return rows


def load_rows(paths, gold_book):
    rows = []
    for path in paths:
        if os.path.isdir(path):
            if os.path.exists(os.path.join(path, "run.json")):
                rows.extend(rows_from_workbench_run(path, gold_book))
            else:
                for sub in sorted(glob.glob(os.path.join(path, "*.json"))):
                    rows.extend(load_rows([sub], gold_book))
        elif path.endswith(".json"):
            rows.extend(rows_from_final_results(path, gold_book))
        else:
            raise ValueError(f"don't know how to read results from {path}")
    return rows


def default_result_paths():
    finals = [
        p for p in sorted(glob.glob(os.path.join(HERE, "results", "final_*.json")))
        if "_summary" not in p and "_error" not in p
    ]
    runs = sorted(
        d for d in glob.glob(os.path.join(ROOT, "runs", "*"))
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "run.json"))
    )
    return finals + runs


# ------------------------------------------------------------------ scoring --

def _field(value, status, condition):
    return SimpleNamespace(
        value=value,
        status=SimpleNamespace(value=status),
        condition=condition,
    )


def _rate(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def compute_metrics(rows):
    """Verification-decision metrics over unified rows (see _row).

    Gold uncertain fields are excluded from every positive/negative
    denominator and reported in the abstention block only.
    """
    tp = fp_all = fp_neg = 0
    gold_pos = gold_neg = 0
    ev_compared = ev_matched = 0
    unc = {"total": 0, "abstained": 0, "asserted": 0, "other": 0}
    unconf = {"total": 0, "correct": 0, "asserted": 0, "other": 0}

    for r in rows:
        gold = _field(r["gold_value"], r["gold_status"], r["gold_condition"])
        pred = _field(r["pred_value"], r["pred_status"], r["pred_condition"])
        gs, ps = r["gold_status"], r["pred_status"]

        if gs == "confirmed":
            gold_pos += 1
            if ps == "confirmed" and field_correct(gold, pred):
                tp += 1
        elif gs in ("unconfirmed", "conflicting"):
            gold_neg += 1
            if ps == "confirmed":
                fp_neg += 1

        if ps == "confirmed" and is_unsupported_claim(gold, pred):
            fp_all += 1

        if gs == "uncertain":
            unc["total"] += 1
            if ps in ("uncertain", "unconfirmed"):
                unc["abstained"] += 1
            elif ps == "confirmed":
                unc["asserted"] += 1
            else:
                unc["other"] += 1
        elif gs == "unconfirmed":
            unconf["total"] += 1
            if ps == "unconfirmed" and r["pred_value"] is None:
                unconf["correct"] += 1
            elif ps == "confirmed":
                unconf["asserted"] += 1
            else:
                unconf["other"] += 1

        if r["gold_evidence"] and r["pred_evidence"]:
            ev_compared += 1
            g = " ".join(str(r["gold_evidence"]).lower().split())
            p = " ".join(str(r["pred_evidence"]).lower().split())
            if g == p or g in p or p in g:
                ev_matched += 1

    fn = gold_pos - tp
    return {
        "fields": len(rows),
        "true_positives": tp,
        "false_positives": fp_all,
        "precision": _rate(tp, tp + fp_all),
        "gold_confirmed": gold_pos,
        "false_negatives": fn,
        "recall": _rate(tp, gold_pos),
        "false_negative_rate": _rate(fn, gold_pos),
        "gold_negative": gold_neg,
        "false_positives_on_gold_negative": fp_neg,
        "false_positive_rate": _rate(fp_neg, gold_neg),
        "evidence_compared": ev_compared,
        "evidence_matched": ev_matched,
        "evidence_accuracy": _rate(ev_matched, ev_compared),
        "abstention": {
            "gold_uncertain": {
                **unc,
                "abstention_rate": _rate(unc["abstained"], unc["total"]),
            },
            "gold_unconfirmed": {
                **unconf,
                "correct_rate": _rate(unconf["correct"], unconf["total"]),
            },
        },
    }


# ------------------------------------------------------------------ report --

def header_lines(book):
    lines = [
        "=" * 72,
        "TruTrace gold metrics: verification decisions vs gold labels",
        f"Gold version scored against: {book.version}",
    ]
    if book.provenance == "ai-drafted":
        lines += [
            "Gold source: AI drafted labels in datasets/ (frozen 27 Nov 2026).",
            "IMPORTANT: this gold version is AI drafted and pending human",
            "review. These numbers measure AGREEMENT WITH AI DRAFTED LABELS,",
            "not validated correctness.",
        ]
    else:
        lines += [
            f"Gold source: human reviewed export (reviewer: {book.reviewer or 'unnamed'}, "
            f"exported: {book.exported_at or 'unknown'}).",
            f"Human reviewed coverage: {book.reviewed_fields} of {book.total_fields} "
            "dataset fields; unreviewed fields keep the AI drafted label "
            f"({GOLD_VERSION_AI_DRAFTED}) and are agreement measures for those fields.",
        ]
    lines.append("=" * 72)
    return lines


def format_report(book, rows):
    by_config = {}
    for r in rows:
        by_config.setdefault(r["config"], []).append(r)
    out = header_lines(book)
    for config in sorted(by_config):
        m = compute_metrics(by_config[config])
        au = m["abstention"]["gold_uncertain"]
        an = m["abstention"]["gold_unconfirmed"]
        out += [
            "",
            f"Configuration: {config}",
            f"  fields scored:            {m['fields']}",
            f"  precision:                {m['precision']}  "
            f"(TP {m['true_positives']} of {m['true_positives'] + m['false_positives']} asserted confirmed)",
            f"  recall:                   {m['recall']}  "
            f"(TP {m['true_positives']} of {m['gold_confirmed']} gold confirmed)",
            f"  false positive rate:      {m['false_positive_rate']}  "
            f"({m['false_positives_on_gold_negative']} of {m['gold_negative']} gold unconfirmed/conflicting asserted)",
            f"  false negative rate:      {m['false_negative_rate']}  "
            f"({m['false_negatives']} of {m['gold_confirmed']} gold confirmed missed)",
            f"  evidence accuracy:        {m['evidence_accuracy']}  "
            f"({m['evidence_matched']} of {m['evidence_compared']} comparable spans)"
            if m["evidence_compared"]
            else "  evidence accuracy:        not measurable (no recorded run cites spans comparable to gold)",
            "  abstention, kept separate and never folded into the rates above:",
            f"    gold uncertain ({au['total']}): abstained {au['abstained']}, "
            f"asserted {au['asserted']}, other {au['other']} "
            f"(abstention rate {au['abstention_rate']})",
            f"    gold unconfirmed ({an['total']}): correct {an['correct']}, "
            f"asserted {an['asserted']}, other {an['other']} "
            f"(correct rate {an['correct_rate']})",
        ]
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--gold",
        help="human reviewed gold export (gold_labels_v2.json); "
        "default: the frozen AI drafted labels",
    )
    parser.add_argument(
        "--results",
        nargs="*",
        help="result files or run directories; default: all recorded "
        "final eval results and workbench runs",
    )
    args = parser.parse_args(argv)
    book = load_gold(args.gold)
    paths = args.results if args.results else default_result_paths()
    rows = load_rows(paths, book)
    print(format_report(book, rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
