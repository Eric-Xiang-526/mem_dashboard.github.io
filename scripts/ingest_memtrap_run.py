#!/usr/bin/env python3
"""
Convert one MemTrapBench eval directory (memtrap_eval_<tag>/<task>/
round1_judge_results_retrieved_memory_<task>_<judge_model>.json, one file
per task) into a dashboard run JSON under data/<dataset>/runs/<run_id>.json.

Each judge file is a flat list of rows: {"id": ..., "dimensions": {
"dimension_N_<name>": {"score": 1-5, "justification": "..."}, ...}}. Some
rows fail to parse and carry {"parse_error": true, "raw": "..."} instead of
real dimensions -- those still count toward n_judged but are excluded from
the per-dimension score averages.

Usage:
  python3 scripts/ingest_memtrap_run.py \
      --run-dir /path/to/outputs/memtrap/memtrap_eval_<tag> \
      --dataset memtrap-rerankmem-hint \
      --run-id <run_id> \
      --label "<label>" \
      --group main \
      --judge-model deepseek-v4.1-flash \
      --description "one-line description of what this run tests"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TASKS = ["hallucination", "hurt", "inertia", "number_game", "poison", "unclear"]


def aggregate_task(rows: list[dict]) -> dict:
    n_total = len(rows)
    dim_sums: dict[str, float] = {}
    dim_counts: dict[str, int] = {}
    for row in rows:
        dims = row.get("dimensions") or {}
        if "parse_error" in dims or "raw" in dims:
            continue
        for dim_key, dim_val in dims.items():
            if not isinstance(dim_val, dict):
                continue
            score = dim_val.get("score")
            if isinstance(score, (int, float)):
                dim_sums[dim_key] = dim_sums.get(dim_key, 0.0) + score
                dim_counts[dim_key] = dim_counts.get(dim_key, 0) + 1

    dim_avgs = {f"{k}_avg": (dim_sums[k] / dim_counts[k]) for k in dim_sums}
    overall_avg = (sum(dim_sums.values()) / sum(dim_counts.values())) if dim_counts else None

    return {
        "n_judged": n_total,
        "overall_avg": overall_avg,
        **dim_avgs,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, help="memtrap_eval_<tag> directory")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--group", default="main", choices=["main", "ablation", "other"])
    ap.add_argument("--description", default="TODO: describe this run.")
    ap.add_argument("--judge-model", required=True)
    ap.add_argument("--generation-model", default="")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    results = []
    for task in TASKS:
        judge_path = run_dir / task / f"round1_judge_results_retrieved_memory_{task}_{args.judge_model}.json"
        if not judge_path.is_file():
            continue
        with judge_path.open() as fh:
            rows = json.load(fh)
        agg = aggregate_task(rows)
        if not agg["n_judged"]:
            continue
        results.append({
            "task": task,
            "n_judged": agg["n_judged"],
            "headline_metric": "overall_avg",
            "headline_value": agg["overall_avg"],
            **{k: v for k, v in agg.items() if k != "n_judged"},
        })

    if not results:
        raise SystemExit(f"no judged rows found under {run_dir}")

    out = {
        "id": args.run_id,
        "label": args.label,
        "group": args.group,
        "description": args.description,
        "generation_model": args.generation_model,
        "judge_models": [args.judge_model],
        "date": "",
        "results": results,
    }

    out_dir = REPO_ROOT / "data" / args.dataset / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.run_id}.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(results)}/{len(TASKS)} tasks, judge={args.judge_model})")
    print(f"remember to add \"{args.run_id}\" to data/{args.dataset}/meta.json -> runs")


if __name__ == "__main__":
    main()
