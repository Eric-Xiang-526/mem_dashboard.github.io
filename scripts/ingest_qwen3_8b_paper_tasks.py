#!/usr/bin/env python3
"""
Replace the hand-transcribed Qwen3-8B literature-baseline runs (written by
seed_qwen3_8b_baselines.py from the paper's LaTeX table) with real numbers
computed from the actual result JSONs under
qwen3_8b_paper_tasks_extracted/qwen3_8b_paper_tasks/<Paper Task Folder>/
<method>_qwen_qwen3_8b_<task_slug>_results_final.json.

Each file's metrics.with_memory.<field>_avg is the real per-run metric
(metrics.no_memory.<field>_avg for the no_memory method). This supersedes the
paper-table transcription for every method it covers.

Usage:
  python3 scripts/ingest_qwen3_8b_paper_tasks.py \
      --source-dir /path/to/qwen3_8b_paper_tasks_extracted/qwen3_8b_paper_tasks
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET = "memsyco-rerankmem-hint"

# dashboard task id -> (paper-task folder name, filename task slug, "results"|"result")
TASKS = {
    "objective_fact_judgment": ("Objective Fact Judgment", "objective_consensus_judgment", "results"),
    "contextual_scope_control": ("Contextual Scope Limits", "memory_scope_overgeneralization_v3", "results"),
    "memory_evidence_conflict": ("Preference-Fact Conflict", "evidence_memory_conflict_noisy", "results"),
    "personalized_memory_use": ("Personalized Recommendation", "recommend_question_open", "results"),
    "valid_memory_selection": ("Preference Change", "preference_update_open_eval", "result"),
}

TASK_HEADLINE_METRIC = {
    "contextual_scope_control": "accuracy_avg",
    "memory_evidence_conflict": "accuracy_avg",
    "objective_fact_judgment": "objective_correctness_avg",
    "personalized_memory_use": "answer_accuracy_avg",
    "valid_memory_selection": "uses_latest_preference_avg",
}

# filename method slug -> (run_id, dashboard label)
METHODS = {
    "amem": ("baseline_a_mem_qwen3_8b", "A-Mem (Qwen3-8B)"),
    "lightmem_full": ("baseline_lightmem_qwen3_8b", "LightMem (Qwen3-8B)"),
    "memgpt_minimal": ("baseline_memgpt_qwen3_8b", "MemGPT (Qwen3-8B)"),
    "memorybank": ("baseline_memorybank_qwen3_8b", "MemoryBank (Qwen3-8B)"),
    "memzero": ("baseline_mem0_qwen3_8b", "Mem0 (Qwen3-8B)"),
    "naive_rag": ("baseline_naiverag_qwen3_8b", "NaiveRAG (Qwen3-8B)"),
    "raw_dialogue": ("baseline_full_dialog_qwen3_8b", "Full Dialog (Qwen3-8B)"),
    "supermemory": ("baseline_supermemory_qwen3_8b", "SuperMemory (Qwen3-8B)"),
}

NO_MEMORY_RUN_ID = "baseline_no_memory_qwen3_8b"
NO_MEMORY_LABEL = "No Memory (Qwen3-8B)"
NO_MEMORY_FILE = "no_memory_qwen_qwen3_8b_objective_fact_judgment_results_final.json"


def find_result_file(source_dir: Path, folder: str, slug: str, result_word: str, method: str) -> Path | None:
    task_dir = source_dir / folder
    for p in sorted(task_dir.glob(f"{method}_qwen_qwen3_8b_{slug}_{result_word}_final.json")):
        return p
    return None


def task_result(doc: dict, task_id: str, arm: str) -> dict:
    metrics = (doc.get("metrics") or {}).get(arm) or {}
    headline_key = TASK_HEADLINE_METRIC[task_id]
    return {
        "task": task_id,
        "arm": arm,
        "n_judged": metrics.get("n_judged", metrics.get("n_scored")),
        "headline_metric": headline_key,
        "headline_value": metrics.get(headline_key),
        **{k: v for k, v in metrics.items() if k.endswith("_avg") and k != headline_key},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--source-dir",
        required=True,
        help="Path to qwen3_8b_paper_tasks_extracted/qwen3_8b_paper_tasks",
    )
    args = ap.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        raise SystemExit(f"no such source dir: {source_dir}")

    out_dir = REPO_ROOT / "data" / DATASET / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    missing = []

    for method, (run_id, label) in METHODS.items():
        results = []
        for task_id, (folder, slug, result_word) in TASKS.items():
            path = find_result_file(source_dir, folder, slug, result_word, method)
            if path is None:
                missing.append(f"{method}/{task_id}")
                continue
            doc = json.loads(path.read_text())
            results.append(task_result(doc, task_id, "with_memory"))
        if not results:
            continue
        out = {
            "id": run_id,
            "label": label,
            "group": "main",
            "description": "Qwen3-8B baseline, computed from qwen3_8b_paper_tasks eval outputs (real judged results, not paper-table transcription).",
            "generation_model": "qwen3-8b",
            "date": "",
            "results": results,
        }
        (out_dir / f"{run_id}.json").write_text(json.dumps(out, indent=2) + "\n")
        written.append(run_id)

    # no_memory: only reported for objective_fact_judgment, from the no_memory arm
    no_mem_path = source_dir / "Objective Fact Judgment" / NO_MEMORY_FILE
    if no_mem_path.exists():
        doc = json.loads(no_mem_path.read_text())
        out = {
            "id": NO_MEMORY_RUN_ID,
            "label": NO_MEMORY_LABEL,
            "group": "main",
            "description": "Qwen3-8B baseline, computed from qwen3_8b_paper_tasks eval outputs (real judged results, not paper-table transcription).",
            "generation_model": "qwen3-8b",
            "date": "",
            "results": [task_result(doc, "objective_fact_judgment", "no_memory")],
        }
        (out_dir / f"{NO_MEMORY_RUN_ID}.json").write_text(json.dumps(out, indent=2) + "\n")
        written.append(NO_MEMORY_RUN_ID)
    else:
        missing.append("no_memory/objective_fact_judgment")

    print(f"wrote {len(written)} run files to {out_dir.relative_to(REPO_ROOT)}")
    for run_id in written:
        print(f"  {run_id}")
    if missing:
        print("missing (not found in source, left un-updated):")
        for m in missing:
            print(f"  {m}")


if __name__ == "__main__":
    main()
