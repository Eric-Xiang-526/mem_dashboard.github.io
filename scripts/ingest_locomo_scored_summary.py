#!/usr/bin/env python3
"""
Convert one `<predictions>_scored_summary.json` file (the layout produced by
the locomo-refined eval pipeline: predictions_<run>_scored_summary.json with
`overall`, `by_category`, `metadata.llm_judge`) into a dashboard run JSON
under data/locomo-refined/runs/<run_id>.json.

There's a single flat task ("locomo_qa") with `llm_score` as the headline
(primary) metric and `f1_score` / `bleu_score` kept as extra fields, plus a
per-category (1-4) breakdown surfaced as extra fields for reference.

Usage:
  python3 scripts/ingest_locomo_scored_summary.py \
      --summary-path /path/to/outputs/predictions_..._scored_summary.json \
      --run-id locomo_hint_instruct2507 \
      --label "Hint (Qwen3-4B-Instruct-2507)" \
      --group main \
      --description "one-line description of what this run tests"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET = "locomo-refined"

METRIC_FIELDS = ["llm_score", "f1_score", "bleu_score"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--summary-path", required=True, help="Path to a *_scored_summary.json file")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--group", default="other", choices=["main", "ablation", "other"])
    ap.add_argument("--description", default="TODO: describe this run.")
    ap.add_argument("--generation-model", default=None, help="Answer-generation model, if known")
    args = ap.parse_args()

    summary_path = Path(args.summary_path)
    doc = json.loads(summary_path.read_text())

    overall = doc["overall"]
    primary_metric = doc.get("primary_metric", "llm_score")

    result = {
        "task": "locomo_qa",
        "arm": "with_memory",
        "n_judged": overall["count"],
        "headline_metric": f"{primary_metric}_avg",
        "headline_value": overall[primary_metric],
    }
    for f in METRIC_FIELDS:
        if f in overall:
            result[f"{f}_avg"] = overall[f]

    by_category = doc.get("by_category") or {}
    for cat_id, cat_doc in sorted(by_category.items()):
        for f in METRIC_FIELDS:
            if f in cat_doc:
                result[f"cat{cat_id}_{f}_avg"] = cat_doc[f]
        result[f"cat{cat_id}_n"] = cat_doc.get("count")

    judge_model = (doc.get("metadata") or {}).get("llm_judge")

    out = {
        "id": args.run_id,
        "label": args.label,
        "group": args.group,
        "description": args.description,
        "generation_model": args.generation_model,
        "judge_models": [judge_model] if judge_model else [],
        "date": "",
        "results": [result],
    }

    out_dir = REPO_ROOT / "data" / DATASET / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.run_id}.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {out_path.relative_to(REPO_ROOT)} (n={overall['count']}, {primary_metric}={overall[primary_metric]:.4f})")
    print(f"remember to add \"{args.run_id}\" to data/{DATASET}/meta.json -> runs")


if __name__ == "__main__":
    main()
