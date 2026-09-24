#!/usr/bin/env python3
"""
Convert the GPT-4o-mini MemSyco results under
infer/outputs/4omini/memsyco/ into dashboard run JSONs under
data/memsyco-4omini-hint/runs/ (a separate dataset tab from the
qwen3-8b-generation memsyco-rerankmem-hint table, mirroring the
locomo-4omini-hint / *-luna-hint pattern).

Two source shapes are handled:

1. Ours (combined answer+judge shard): `ours/answer_shard_0.jsonl`, one row
   per question with an embedded `judge` dict (same judge-field schema as
   TASK_JUDGE_FIELDS elsewhere). Aggregation matches
   ingest_ablation_embedded_judge.py: headline = pass-field rate over all
   rows, extra <field>_avg fields alongside.

2. Literature baselines: flat per-task folders
   `<task_slug>/<method>_openai_gpt_4o_mini_<task_slug>_<results|result>_final.json`
   (the baseline_opt_v2 layout, same shape the qwen3-8b paper-tasks
   ingester reads), each carrying pre-aggregated
   `metrics.with_memory.<field>_avg` (+ `metrics.no_memory` for the
   no_memory run's objective task).

Usage:
  python3 scripts/ingest_gpt4omini_memsyco.py \
      --source-dir /path/to/infer/outputs/4omini/memsyco \
      --ours-shard ours/answer_shard_0.jsonl
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET = "memsyco-4omini-hint"

TASK_JUDGE_FIELDS = {
    "contextual_scope_control": ("accuracy", ["incorrectly_used_preference", "scope_pass"]),
    "memory_evidence_conflict": ("accuracy", ["misled_by_conflicting_memory", "evidence_pass"]),
    "objective_fact_judgment": ("objective_correctness", ["preference_contamination", "preference_answer_selected", "suppress_pass"]),
    "personalized_memory_use": ("answer_accuracy", ["preference_used", "memory_use_pass"]),
    "valid_memory_selection": ("uses_latest_preference", ["outdated_preference_contamination", "valid_selection_pass"]),
}

# task -> (folder name, filename task slug, "results"|"result")
TASKS = {
    "objective_fact_judgment": ("objective_fact_judgment", "objective_consensus_judgment", "results"),
    "contextual_scope_control": ("contextual_scope_control", "memory_scope_overgeneralization_v3", "results"),
    "memory_evidence_conflict": ("memory_evidence_conflict", "evidence_memory_conflict_noisy", "results"),
    "personalized_memory_use": ("personalized_memory_use", "recommend_question_open", "results"),
    "valid_memory_selection": ("valid_memory_selection", "preference_update_open_eval", "result"),
}

TASK_HEADLINE_METRIC = {
    "contextual_scope_control": "accuracy_avg",
    "memory_evidence_conflict": "accuracy_avg",
    "objective_fact_judgment": "objective_correctness_avg",
    "personalized_memory_use": "answer_accuracy_avg",
    "valid_memory_selection": "uses_latest_preference_avg",
}

# filename method slug -> (run-id suffix, dashboard label)
METHODS = {
    "amem": ("a_mem", "A-Mem"),
    "lightmem_full": ("lightmem", "LightMem"),
    "memgpt_minimal": ("memgpt", "MemGPT"),
    "memorybank": ("memorybank", "MemoryBank"),
    "memzero": ("mem0", "Mem0"),
    "naive_rag": ("naiverag", "NaiveRAG"),
    "raw_dialogue": ("full_dialog", "Full Dialog"),
    "supermemory": ("supermemory", "SuperMemory"),
}

NO_MEMORY_SUFFIX = "no_memory"
NO_MEMORY_LABEL = "No Memory"
MODEL_TAG = "openai_gpt_4o_mini"
GEN_MODEL = "gpt-4o-mini"
JUDGE_MODEL = "deepseek-v4.1-flash"


def aggregate_shard(shard_path: Path) -> list[dict]:
    rows_by_task: dict[str, list[dict]] = defaultdict(list)
    generation_model = None
    with shard_path.open() as fh:
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
        n_total = len(rows)
        pass_sum = 0
        extra_sums = {f: 0.0 for f in extra_fields}
        extra_counts = {f: 0 for f in extra_fields}
        for row in rows:
            judge = row.get("judge") or {}
            if not judge.get("judge_parse_ok", False) or judge.get("judge_error"):
                continue
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
        results.append({
            "task": task,
            "arm": "with_memory",
            "n_judged": n_total,
            "headline_metric": f"{pass_field}_avg",
            "headline_value": pass_sum / n_total,
            **{f"{f}_avg": (extra_sums[f] / extra_counts[f]) if extra_counts[f] else None for f in extra_fields},
        })
    return results, generation_model


def task_result(doc: dict, task_id: str, arm: str) -> dict:
    metrics = (doc.get("metrics") or {}).get(arm) or {}
    headline_key = TASK_HEADLINE_METRIC[task_id]
    n = metrics.get("n_judged", metrics.get("n_scored", metrics.get("n_samples")))
    return {
        "task": task_id,
        "arm": arm,
        "n_judged": n,
        "headline_metric": headline_key,
        "headline_value": metrics.get(headline_key),
        **{k: v for k, v in metrics.items() if k.endswith("_avg") and k != headline_key},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-dir", required=True, help="Path to infer/outputs/4omini/memsyco")
    ap.add_argument("--ours-shard", default="ours/answer_shard_0.jsonl", help="Shard path relative to --source-dir")
    ap.add_argument("--ours-run-id", default="ours_gpt_4o_mini")
    args = ap.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        raise SystemExit(f"no such source dir: {source_dir}")

    out_dir = REPO_ROOT / "data" / DATASET / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    # 1. Ours (combined answer+judge shard)
    shard_path = source_dir / args.ours_shard
    if shard_path.is_file():
        results, gen_model = aggregate_shard(shard_path)
        out = {
            "id": args.ours_run_id,
            "label": "Ours (GPT-4o-mini)",
            "group": "main",
            "description": "RerankMem full pipeline (decompose + rerank enabled, hint model qwen3-8b) with GPT-4o-mini as the answer model; combined answer+judge run (judge embedded per row).",
            "generation_model": gen_model or GEN_MODEL,
            "judge_models": [JUDGE_MODEL],
            "date": "",
            "results": results,
        }
        (out_dir / f"{args.ours_run_id}.json").write_text(json.dumps(out, indent=2) + "\n")
        written.append(args.ours_run_id)

    # 2. Literature baselines from the flat per-task final.json files
    for method, (suffix, name) in METHODS.items():
        results = []
        for task_id, (folder, slug, result_word) in TASKS.items():
            path = source_dir / folder / f"{method}_{MODEL_TAG}_{slug}_{result_word}_final.json"
            if not path.is_file():
                continue
            doc = json.loads(path.read_text())
            results.append(task_result(doc, task_id, "with_memory"))
        if not results:
            continue
        run_id = f"baseline_{suffix}_gpt_4o_mini"
        out = {
            "id": run_id,
            "label": f"{name} (GPT-4o-mini)",
            "group": "main",
            "description": "GPT-4o-mini answer model baseline, computed from the 4o-mini flat eval outputs (pre-aggregated metrics.with_memory; judged by deepseek-v4.1-flash).",
            "generation_model": GEN_MODEL,
            "judge_models": [JUDGE_MODEL],
            "date": "",
            "results": results,
        }
        (out_dir / f"{run_id}.json").write_text(json.dumps(out, indent=2) + "\n")
        written.append(run_id)

    # 3. no_memory: only reported for objective_fact_judgment, no_memory arm
    no_mem_path = source_dir / "objective_fact_judgment" / f"no_memory_{MODEL_TAG}_objective_consensus_judgment_results_final.json"
    if no_mem_path.is_file():
        doc = json.loads(no_mem_path.read_text())
        run_id = f"baseline_{NO_MEMORY_SUFFIX}_gpt_4o_mini"
        out = {
            "id": run_id,
            "label": f"{NO_MEMORY_LABEL} (GPT-4o-mini)",
            "group": "main",
            "description": "GPT-4o-mini no-memory reference, objective_fact_judgment only (no_memory arm), from the 4o-mini flat eval outputs.",
            "generation_model": GEN_MODEL,
            "judge_models": [JUDGE_MODEL],
            "date": "",
            "results": [task_result(doc, "objective_fact_judgment", "no_memory")],
        }
        (out_dir / f"{run_id}.json").write_text(json.dumps(out, indent=2) + "\n")
        written.append(run_id)

    print(f"wrote {len(written)} run files to {out_dir.relative_to(REPO_ROOT)}")
    for run_id in written:
        print(f"  {run_id}")


if __name__ == "__main__":
    main()
