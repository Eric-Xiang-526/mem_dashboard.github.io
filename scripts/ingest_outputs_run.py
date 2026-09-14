#!/usr/bin/env python3
"""
Convert one generation-run directory under a handoff's outputs/ tree (the
layout produced by the current memsyco eval pipeline:
  outputs/<gen_run>/<judge_model>/<timestamp>/judged_<task>.jsonl
  outputs/<gen_run>/<judge_model>/<timestamp>/results_<task>.json
  outputs/<gen_run>/generation/extract_results.jsonl
into a dashboard run JSON under data/<dataset>/runs/<run_id>.json.

For each task, judge subfolders are tried in --judge-priority order
(default: deepseek-v4.1-flash, then deepseek-v4-flash) and the first
timestamp folder containing that task's judged data wins. This lets a run
mix judge models per task when only some tasks have been re-judged with the
preferred model yet -- each task result records which judge model it
actually came from.

Usage:
  python3 scripts/ingest_outputs_run.py \
      --run-dir /path/to/handoffs/<dataset>/outputs/<gen_run> \
      --dataset memsyco-rerankmem-hint \
      --run-id local_hint_memonly_needs_iter134 \
      --label "Hint memonly (iter134)" \
      --group ablation \
      --description "one-line description of what this run tests"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# task -> (headline field in judge dict == the paper's "Acc." column,
#          extra *_avg fields to also surface, incl. the old composite pass field)
TASK_JUDGE_FIELDS = {
    "contextual_scope_control": ("accuracy", ["incorrectly_used_preference", "scope_pass"]),
    "memory_evidence_conflict": ("accuracy", ["misled_by_conflicting_memory", "evidence_pass"]),
    "objective_fact_judgment": ("objective_correctness", ["preference_contamination", "preference_answer_selected", "suppress_pass"]),
    "personalized_memory_use": ("answer_accuracy", ["preference_used", "memory_use_pass"]),
    "valid_memory_selection": ("uses_latest_preference", ["outdated_preference_contamination", "valid_selection_pass"]),
}


def latest_timestamp_dir(judge_dir: Path) -> list[Path]:
    """All timestamp subdirs under a judge model dir, newest first."""
    dirs = [d for d in judge_dir.iterdir() if d.is_dir()]
    return sorted(dirs, key=lambda d: d.name, reverse=True)


def aggregate_judged_jsonl(path: Path, pass_field: str, extra_fields: list[str]) -> dict:
    # Denominator is every row in the file (n_total), matching how the eval
    # harness itself reports pass rate: a row with judge_parse_ok=false or a
    # judge_error still counts against the denominator, it just never counts
    # as a pass. This keeps ingested numbers identical to what's reported
    # off the raw judged_<task>.jsonl files.
    n_total = 0
    n_valid = 0
    pass_sum = 0
    extra_sums = {f: 0.0 for f in extra_fields}
    extra_counts = {f: 0 for f in extra_fields}
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n_total += 1
            row = json.loads(line)
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


def find_task_result(run_dir: Path, task: str, judge_priority: list[str]) -> dict | None:
    pass_field, extra_fields = TASK_JUDGE_FIELDS[task]
    for judge_model in judge_priority:
        judge_dir = run_dir / judge_model
        if not judge_dir.is_dir():
            continue
        for ts_dir in latest_timestamp_dir(judge_dir):
            jsonl_path = ts_dir / f"judged_{task}.jsonl"
            if jsonl_path.exists():
                agg = aggregate_judged_jsonl(jsonl_path, pass_field, extra_fields)
                if agg["n_judged"]:
                    return {
                        "task": task,
                        "arm": "with_memory",
                        "n_judged": agg["n_judged"],
                        "headline_metric": f"{pass_field}_avg",
                        "headline_value": agg["headline_value"],
                        "judge_model": judge_model,
                        **{k: v for k, v in agg.items() if k.endswith("_avg")},
                    }
            # fall back to pre-aggregated results_<task>.json (official-pipeline runs)
            results_path = ts_dir / f"results_{task}.json"
            if results_path.exists():
                doc = json.loads(results_path.read_text())
                metrics = (doc.get("metrics") or {}).get("with_memory") or {}
                headline_key = f"{pass_field}_avg"
                if headline_key in metrics:
                    return {
                        "task": task,
                        "arm": "with_memory",
                        "n_judged": metrics.get("n_scored") or metrics.get("n_judged"),
                        "headline_metric": headline_key,
                        "headline_value": metrics[headline_key],
                        "judge_model": doc.get("judge_model", judge_model),
                        **{k: v for k, v in metrics.items() if k.endswith("_avg") and k != headline_key},
                    }
    return None


def generation_model(run_dir: Path) -> str | None:
    extract_path = run_dir / "generation" / "extract_results.jsonl"
    if not extract_path.exists():
        return None
    with extract_path.open() as fh:
        line = fh.readline()
    if not line.strip():
        return None
    return json.loads(line).get("answer_model")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, help="Generation-run directory under outputs/, e.g. outputs/<gen_run>")
    ap.add_argument("--dataset", required=True, help="Dataset id, e.g. memsyco-rerankmem-hint")
    ap.add_argument("--run-id", required=True, help="Output run id (used as filename and dashboard key)")
    ap.add_argument("--label", required=True, help="Human-readable label shown in the dashboard")
    ap.add_argument("--group", default="other", choices=["main", "ablation", "other"])
    ap.add_argument("--description", default="TODO: describe this run.")
    ap.add_argument(
        "--judge-priority",
        default="deepseek-v4.1-flash,deepseek-v4-flash",
        help="Comma-separated judge model dir names, most preferred first.",
    )
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        raise SystemExit(f"no such run dir: {run_dir}")

    judge_priority = [j.strip() for j in args.judge_priority.split(",") if j.strip()]

    results = []
    judge_models_used = set()
    for task in TASK_JUDGE_FIELDS:
        r = find_task_result(run_dir, task, judge_priority)
        if r is None:
            continue
        judge_models_used.add(r.pop("judge_model", None))
        results.append(r)

    if not results:
        raise SystemExit(f"no judged data found under {run_dir} for judge models {judge_priority}")

    out = {
        "id": args.run_id,
        "label": args.label,
        "group": args.group,
        "description": args.description,
        "generation_model": generation_model(run_dir),
        "judge_models": sorted(m for m in judge_models_used if m),
        "date": "",
        "results": results,
    }

    out_dir = REPO_ROOT / "data" / args.dataset / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.run_id}.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(results)}/{len(TASK_JUDGE_FIELDS)} tasks, judges={sorted(judge_models_used)})")
    print(f"remember to add \"{args.run_id}\" to data/{args.dataset}/meta.json -> runs")


if __name__ == "__main__":
    main()
