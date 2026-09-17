#!/usr/bin/env python3
"""
Convert one pre-aggregated MemTrapBench ablation summary
(predictions_ablation_<variant>_scored_summary.json, with `by_dataset.<task>
.dimensions.<dim>.{n, mean_raw_1_5}`) into a dashboard run JSON under
data/<dataset>/runs/<run_id>.json.

This is a different source shape than ingest_memtrap_run.py (which reads
raw per-row round1_judge_results_*.json files): here the judge output is
already aggregated per dimension, so this script just reshapes it to match
the same run-JSON schema (task.overall_avg + task.<dim>_avg, headline_value
= overall_avg, format "raw" 1-5 scale) so ablation rows are directly
comparable to the main memtrap_hint_* rows.

overall_avg per task is the n-weighted mean across that task's dimensions'
mean_raw_1_5 (equivalent to averaging every valid row's every dimension
score directly, same convention ingest_memtrap_run.py uses).

Usage:
  python3 scripts/ingest_memtrap_ablation_summary.py \
      --summary-path /path/to/outputs/memtrap/predictions_ablation_full_both_scored_summary.json \
      --dataset memtrap-rerankmem-hint \
      --run-id memtrap_ablation_full_both \
      --label "Full (decompose + rerank)" \
      --group ablation \
      --description "one-line description of what this run tests"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--summary-path", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--group", default="ablation", choices=["main", "ablation", "other"])
    ap.add_argument("--description", default="TODO: describe this run.")
    ap.add_argument("--generation-model", default=None)
    ap.add_argument("--judge-model", default=None, help="Defaults to doc.target_model")
    args = ap.parse_args()

    doc = json.loads(Path(args.summary_path).read_text())
    judge_model = args.judge_model or doc.get("target_model") or "unknown"

    results = []
    for task, task_doc in doc.get("by_dataset", {}).items():
        dims = task_doc.get("dimensions") or {}
        if not dims:
            continue
        weighted_sum = sum(d["mean_raw_1_5"] * d["n"] for d in dims.values() if d.get("n"))
        weighted_n = sum(d["n"] for d in dims.values() if d.get("n"))
        if not weighted_n:
            continue
        overall_avg = weighted_sum / weighted_n
        results.append({
            "task": task,
            "n_judged": task_doc.get("n_total"),
            "headline_metric": "overall_avg",
            "headline_value": overall_avg,
            "overall_avg": overall_avg,
            **{f"{dim_key}_avg": dim_val["mean_raw_1_5"] for dim_key, dim_val in dims.items()},
        })

    if not results:
        raise SystemExit(f"no by_dataset entries found in {args.summary_path}")

    out = {
        "id": args.run_id,
        "label": args.label,
        "group": args.group,
        "description": args.description,
        "generation_model": args.generation_model or "",
        "judge_models": [judge_model],
        "date": "",
        "results": results,
    }

    out_dir = REPO_ROOT / "data" / args.dataset / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.run_id}.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(results)} tasks)")
    print(f"remember to add \"{args.run_id}\" to data/{args.dataset}/meta.json -> runs")


if __name__ == "__main__":
    main()
