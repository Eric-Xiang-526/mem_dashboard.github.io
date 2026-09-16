#!/usr/bin/env python3
"""
Convert one ablation run directory whose judging is embedded directly in
generation/extract_results.jsonl (each row already carries a `judge` dict,
rather than the standard judge_traj.py layout of separate
<judge_model>/<timestamp>/judged_<task>.jsonl files) into a dashboard run
JSON under data/<dataset>/runs/<run_id>.json.

Reuses the same TASK_JUDGE_FIELDS field mapping as ingest_outputs_run.py so
results line up with the four already-ingested main runs.

Usage:
  python3 scripts/ingest_ablation_embedded_judge.py \
      --run-dir /path/to/outputs/ablation_full_both \
      --dataset memsyco-rerankmem-hint \
      --run-id ablation_full_both \
      --label "Ablation: full (both)" \
      --group ablation \
      --judge-model deepseek-v4.1-flash \
      --description "one-line description of what this ablation tests"
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TASK_JUDGE_FIELDS = {
    "contextual_scope_control": ("accuracy", ["incorrectly_used_preference", "scope_pass"]),
    "memory_evidence_conflict": ("accuracy", ["misled_by_conflicting_memory", "evidence_pass"]),
    "objective_fact_judgment": ("objective_correctness", ["preference_contamination", "preference_answer_selected", "suppress_pass"]),
    "personalized_memory_use": ("answer_accuracy", ["preference_used", "memory_use_pass"]),
    "valid_memory_selection": ("uses_latest_preference", ["outdated_preference_contamination", "valid_selection_pass"]),
}


def aggregate_rows(rows: list[dict], pass_field: str, extra_fields: list[str]) -> dict:
    n_total = 0
    n_valid = 0
    pass_sum = 0
    extra_sums = {f: 0.0 for f in extra_fields}
    extra_counts = {f: 0 for f in extra_fields}
    for row in rows:
        n_total += 1
        judge = row.get("judge") or {}
        if not judge.get("judge_parse_ok", False) or judge.get("judge_error"):
            continue
        n_valid += 1
        if judge.get(pass_field):
            pass_sum += 1
        for f in extra_fields:
            v = judge.get(f)
            if isinstance(v, bool):
                extra_sums[f] += 1 if v else 0
                extra_counts[f] += 1
            elif isinstance(v, (int, float)):
                extra_sums[f] += v
                extra_counts[f] += 1
    out = {
        "n_judged": n_total,
        "n_valid": n_valid,
        "headline_value": (pass_sum / n_total) if n_total else None,
    }
    for f in extra_fields:
        out[f"{f}_avg"] = (extra_sums[f] / extra_counts[f]) if extra_counts[f] else None
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, help="Ablation run directory, e.g. outputs/ablation_full_both")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--group", default="ablation", choices=["main", "ablation", "other"])
    ap.add_argument("--description", default="TODO: describe this run.")
    ap.add_argument("--judge-model", required=True, help="Judge model name to record (not present per-row in this layout)")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    extract_path = run_dir / "generation" / "extract_results.jsonl"
    if not extract_path.is_file():
        raise SystemExit(f"no such file: {extract_path}")

    rows_by_task: dict[str, list[dict]] = defaultdict(list)
    generation_model = None
    with extract_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            rows_by_task[row["task"]].append(row)
            if generation_model is None:
                generation_model = row.get("answer_model")

    results = []
    for task, (pass_field, extra_fields) in TASK_JUDGE_FIELDS.items():
        rows = rows_by_task.get(task)
        if not rows:
            continue
        agg = aggregate_rows(rows, pass_field, extra_fields)
        if not agg["n_judged"]:
            continue
        results.append({
            "task": task,
            "arm": "with_memory",
            "n_judged": agg["n_judged"],
            "headline_metric": f"{pass_field}_avg",
            "headline_value": agg["headline_value"],
            **{k: v for k, v in agg.items() if k.endswith("_avg")},
        })

    if not results:
        raise SystemExit(f"no judged rows found under {extract_path}")

    out = {
        "id": args.run_id,
        "label": args.label,
        "group": args.group,
        "description": args.description,
        "generation_model": generation_model,
        "judge_models": [args.judge_model],
        "date": "",
        "results": results,
    }

    out_dir = REPO_ROOT / "data" / args.dataset / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.run_id}.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(results)}/{len(TASK_JUDGE_FIELDS)} tasks, judge={args.judge_model})")
    print(f"remember to add \"{args.run_id}\" to data/{args.dataset}/meta.json -> runs")


if __name__ == "__main__":
    main()
