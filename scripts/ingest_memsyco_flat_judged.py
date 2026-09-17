#!/usr/bin/env python3
"""
Convert one set of flat `judged_<shortname>_<run>.jsonl` files (the layout
used by the luna base-model experiments: one file per task directly under
the run directory, no <judge_model>/<timestamp>/ nesting, using abbreviated
task-name prefixes) into a dashboard run JSON under
data/<dataset>/runs/<run_id>.json.

Row schema matches the standard judged_<task>.jsonl rows used elsewhere
(each row has a "judge" dict keyed the same way as TASK_JUDGE_FIELDS), so
this reuses the exact same aggregation as ingest_outputs_run.py, just
pointed at a flat directory with short filename prefixes instead of a
nested judge-model/timestamp tree.

Usage:
  python3 scripts/ingest_memsyco_flat_judged.py \
      --run-dir /path/to/luna/memsyco \
      --run-suffix memsyco_hint_instruct2507_20260916_1937 \
      --dataset memsyco-luna-hint \
      --run-id memsyco_luna_hint_instruct2507 \
      --label "Hint (Instruct-2507)" \
      --group main \
      --judge-model deepseek-v4.1-flash \
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

# short filename prefix -> full task id
SHORT_TASK_NAMES = {
    "scope": "contextual_scope_control",
    "evid": "memory_evidence_conflict",
    "obj": "objective_fact_judgment",
    "pers": "personalized_memory_use",
    "valid": "valid_memory_selection",
}


def aggregate_judged_jsonl(path: Path, pass_field: str, extra_fields: list[str]) -> dict:
    n_total = 0
    n_valid = 0
    pass_sum = 0
    extra_sums = {f: 0.0 for f in extra_fields}
    extra_counts = {f: 0 for f in extra_fields}
    answer_model = None
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n_total += 1
            row = json.loads(line)
            if answer_model is None:
                answer_model = row.get("answer_model")
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
        "answer_model": answer_model,
    }
    for f in extra_fields:
        out[f"{f}_avg"] = (extra_sums[f] / extra_counts[f]) if extra_counts[f] else None
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, help="Directory holding the flat judged_<shortname>_<run-suffix>.jsonl files")
    ap.add_argument("--run-suffix", required=True, help="The <run> part of judged_<shortname>_<run>.jsonl")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--group", default="main", choices=["main", "ablation", "other"])
    ap.add_argument("--description", default="TODO: describe this run.")
    ap.add_argument("--judge-model", default="deepseek-v4.1-flash")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    results = []
    answer_model = None
    for short_name, task in SHORT_TASK_NAMES.items():
        jsonl_path = run_dir / f"judged_{short_name}_{args.run_suffix}.jsonl"
        if not jsonl_path.exists():
            continue
        pass_field, extra_fields = TASK_JUDGE_FIELDS[task]
        agg = aggregate_judged_jsonl(jsonl_path, pass_field, extra_fields)
        if not agg["n_judged"]:
            continue
        answer_model = answer_model or agg["answer_model"]
        results.append({
            "task": task,
            "arm": "with_memory",
            "n_judged": agg["n_judged"],
            "headline_metric": f"{pass_field}_avg",
            "headline_value": agg["headline_value"],
            "judge_model": args.judge_model,
            **{k: v for k, v in agg.items() if k.endswith("_avg")},
        })

    if not results:
        raise SystemExit(f"no judged rows found under {run_dir} for suffix {args.run_suffix}")

    out = {
        "id": args.run_id,
        "label": args.label,
        "group": args.group,
        "description": args.description,
        "generation_model": answer_model or "",
        "judge_models": [args.judge_model],
        "date": "",
        "results": results,
    }

    out_dir = REPO_ROOT / "data" / args.dataset / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.run_id}.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(results)}/{len(SHORT_TASK_NAMES)} tasks)")
    print(f"remember to add \"{args.run_id}\" to data/{args.dataset}/meta.json -> runs")


if __name__ == "__main__":
    main()
