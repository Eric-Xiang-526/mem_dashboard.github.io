#!/usr/bin/env python3
"""
Convert one original-LoCoMo `predictions_*.jsonl` file into a dashboard run
JSON under data/locomo-origin/runs/<run_id>.json.

Scores with the official snap-research token-F1 metric (mirrors
infer/handoffs/locomo-origin/score_origin.py), broken down by question
category (1 multi-hop, 2 temporal, 3 open-domain, 4 single-hop, 5
adversarial). Category 5 (adversarial) is deliberately EXCLUDED from the
headline/avg — its refusal-style scoring isn't comparable to token-F1 on
the other four categories — so `avg4_f1` is the n-weighted mean over
categories 1-4 only.

Usage:
  python3 scripts/ingest_locomo_origin_run.py \
      --predictions /path/to/predictions_<run>.jsonl \
      --run-id ours_full \
      --label "Ours (full)" \
      --group main \
      --generation-model qwen3-8b \
      --description "one-line description of what this run tests"
"""
from __future__ import annotations

import argparse
import json
import string
from collections import defaultdict
from pathlib import Path

import regex
from nltk.stem import PorterStemmer

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUESTIONS = (
    REPO_ROOT.parent
    / "infer"
    / "handoffs"
    / "locomo-origin"
    / "bench"
    / "data"
    / "public"
    / "questions.jsonl"
)

ps = PorterStemmer()
CAT_NAMES = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop", 5: "adversarial"}


def normalize_answer(s: str) -> str:
    s = (s or "").replace(",", "")

    def remove_articles(text: str) -> str:
        return regex.sub(r"\b(a|an|the|and)\b", " ", text)

    def white_space_fix(text: str) -> str:
        return " ".join(text.split())

    def remove_punc(text: str) -> str:
        exclude = set(string.punctuation)
        return "".join(ch for ch in text if ch not in exclude)

    return white_space_fix(remove_articles(remove_punc(s.lower())))


def f1_score(prediction: str, ground_truth: str) -> float:
    prediction_tokens = [ps.stem(w) for w in normalize_answer(prediction).split()]
    ground_truth_tokens = [ps.stem(w) for w in normalize_answer(ground_truth).split()]
    if not prediction_tokens or not ground_truth_tokens:
        return 0.0
    common_tokens = set(prediction_tokens) & set(ground_truth_tokens)
    num_same = sum(min(prediction_tokens.count(t), ground_truth_tokens.count(t)) for t in common_tokens)
    if num_same == 0:
        return 0.0
    precision = 1.0 * num_same / len(prediction_tokens)
    recall = 1.0 * num_same / len(ground_truth_tokens)
    return (2 * precision * recall) / (precision + recall)


def f1_multi(prediction: str, ground_truth: str) -> float:
    predictions = [p.strip() for p in prediction.split(",")]
    ground_truths = [g.strip() for g in ground_truth.split(",")]
    if not ground_truths:
        return 0.0
    return float(sum(max(f1_score(p, gt) for p in predictions) for gt in ground_truths) / len(ground_truths))


def score_one(category: int, prediction: str, answer: str) -> float:
    output = prediction or ""
    if category == 3:
        answer = (answer or "").split(";")[0].strip()
    if category in (2, 3, 4):
        return f1_score(output, answer or "")
    if category == 1:
        return f1_multi(output, answer or "")
    if category == 5:
        low = output.lower()
        if "no information available" in low or "not mentioned" in low:
            return 1.0
        return 0.0
    raise ValueError("unknown category %s" % category)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--predictions", required=True, help="Path to a predictions_*.jsonl file")
    ap.add_argument("--questions", default=str(DEFAULT_QUESTIONS), help="Path to questions.jsonl (has qa_id/category/answer)")
    ap.add_argument("--dataset", default="locomo-origin")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--group", default="other", choices=["main", "ablation", "other"])
    ap.add_argument("--description", default="TODO: describe this run.")
    ap.add_argument("--generation-model", default=None)
    args = ap.parse_args()

    gold = {}
    with open(args.questions, encoding="utf-8") as fin:
        for line in fin:
            if line.strip():
                r = json.loads(line)
                gold[r["qa_id"]] = r

    preds = {}
    with open(args.predictions, encoding="utf-8") as fin:
        for line in fin:
            if line.strip():
                r = json.loads(line)
                preds[r["qa_id"]] = r.get("predicted_answer") or ""

    by_cat = defaultdict(list)
    missing = 0
    for qa_id, g in gold.items():
        if qa_id not in preds:
            missing += 1
            continue
        cat = int(g["category"])
        answer = g.get("answer")
        answer = "" if answer is None else str(answer)
        pred = preds[qa_id]
        pred = "" if pred is None else str(pred)
        by_cat[cat].append(score_one(cat, pred, answer))

    cat_stats = {c: (len(v), (sum(v) / len(v) if v else 0.0)) for c, v in by_cat.items()}
    n4 = sum(cat_stats.get(c, (0, 0.0))[0] for c in (1, 2, 3, 4))
    s4 = sum(cat_stats.get(c, (0, 0.0))[0] * cat_stats.get(c, (0, 0.0))[1] for c in (1, 2, 3, 4))
    avg4 = s4 / n4 if n4 else 0.0

    result = {
        "task": "locomo_qa",
        "n_judged": n4,
        "headline_metric": "avg4_f1",
        "headline_value": avg4,
        "avg4_f1": avg4,
    }
    for c in (1, 2, 3, 4):
        n, mean = cat_stats.get(c, (0, 0.0))
        result[f"cat{c}_f1"] = mean
        result[f"cat{c}_n"] = n
    if 5 in cat_stats:
        n5, mean5 = cat_stats[5]
        result["cat5_adversarial_f1_excluded"] = mean5
        result["cat5_adversarial_n_excluded"] = n5

    out = {
        "id": args.run_id,
        "label": args.label,
        "group": args.group,
        "description": args.description,
        "generation_model": args.generation_model,
        "judge_models": ["token_f1"],
        "date": "",
        "results": [result],
    }

    out_dir = REPO_ROOT / "data" / args.dataset / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.run_id}.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {out_path.relative_to(REPO_ROOT)} (n4={n4}, avg4_f1={avg4:.4f}, missing={missing})")
    print(f'remember to add "{args.run_id}" to data/{args.dataset}/meta.json -> runs')


if __name__ == "__main__":
    main()
