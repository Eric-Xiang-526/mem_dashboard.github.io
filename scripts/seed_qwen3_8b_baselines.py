#!/usr/bin/env python3
"""
Seed literature-baseline run JSONs for the memsyco-rerankmem-hint dataset,
Qwen3-8B block only, from the paper's main-results table (Acc. column only,
i.e. the first metric per task). Source: paper Table (Main results on
MemSyco-Bench), Qwen3-8B section.

Not a real judged-output ingestion (no raw jsonl for these) -- values are
hand-transcribed from the LaTeX table and written directly. Re-run this to
regenerate if a transcription error is found; do not hand-edit the output
files.
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET = "memsyco-rerankmem-hint"

# method -> {task: acc_percent}; missing task = not reported for that method.
QWEN3_8B_ACC = {
    "no_memory": {
        "objective_fact_judgment": 49.12,
    },
    "full_dialog": {
        "objective_fact_judgment": 30.62,
        "contextual_scope_control": 70.00,
        "memory_evidence_conflict": 0.67,
        "personalized_memory_use": 45.67,
        "valid_memory_selection": 27.79,
    },
    "naiverag": {
        "objective_fact_judgment": 34.00,
        "contextual_scope_control": 52.33,
        "memory_evidence_conflict": 17.00,
        "personalized_memory_use": 51.67,
        "valid_memory_selection": 30.40,
    },
    "mem0": {
        "objective_fact_judgment": 35.67,
        "contextual_scope_control": 13.34,
        "memory_evidence_conflict": 21.33,
        "personalized_memory_use": 52.33,
        "valid_memory_selection": 32.57,
    },
    "a_mem": {
        "objective_fact_judgment": 36.00,
        "contextual_scope_control": 53.06,
        "memory_evidence_conflict": 25.91,
        "personalized_memory_use": 55.33,
        "valid_memory_selection": 24.00,
    },
    "lightmem": {
        "objective_fact_judgment": 34.67,
        "contextual_scope_control": 13.67,
        "memory_evidence_conflict": 2.34,
        "personalized_memory_use": 48.16,
        "valid_memory_selection": 24.07,
    },
    "memgpt": {
        "objective_fact_judgment": 30.00,
        "contextual_scope_control": 40.00,
        "memory_evidence_conflict": 3.72,
        "personalized_memory_use": 46.33,
        "valid_memory_selection": 41.14,
    },
    "memorybank": {
        "objective_fact_judgment": 31.67,
        "contextual_scope_control": 51.33,
        "memory_evidence_conflict": 13.67,
        "personalized_memory_use": 49.33,
        "valid_memory_selection": 40.86,
    },
    "supermemory": {
        "objective_fact_judgment": 26.00,
        "contextual_scope_control": 34.67,
        "memory_evidence_conflict": 0.00,
        "personalized_memory_use": 54.52,
        "valid_memory_selection": 42.00,
    },
}

LABELS = {
    "no_memory": "No Memory (Qwen3-8B)",
    "full_dialog": "Full Dialog (Qwen3-8B)",
    "naiverag": "NaiveRAG (Qwen3-8B)",
    "mem0": "Mem0 (Qwen3-8B)",
    "a_mem": "A-Mem (Qwen3-8B)",
    "lightmem": "LightMem (Qwen3-8B)",
    "memgpt": "MemGPT (Qwen3-8B)",
    "memorybank": "MemoryBank (Qwen3-8B)",
    "supermemory": "SuperMemory (Qwen3-8B)",
}

TASK_HEADLINE_METRIC = {
    "contextual_scope_control": "accuracy_avg",
    "memory_evidence_conflict": "accuracy_avg",
    "objective_fact_judgment": "objective_correctness_avg",
    "personalized_memory_use": "answer_accuracy_avg",
    "valid_memory_selection": "uses_latest_preference_avg",
}


def main():
    out_dir = REPO_ROOT / "data" / DATASET / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for method, tasks in QWEN3_8B_ACC.items():
        run_id = f"baseline_{method}_qwen3_8b"
        results = [
            {
                "task": task,
                "arm": "baseline",
                "n_judged": None,
                "headline_metric": TASK_HEADLINE_METRIC[task],
                "headline_value": acc_pct / 100,
            }
            for task, acc_pct in tasks.items()
        ]
        out = {
            "id": run_id,
            "label": LABELS[method],
            "group": "other",
            "description": "Literature baseline, Acc. column only, from the paper's main-results table.",
            "generation_model": "qwen3-8b",
            "date": "",
            "results": results,
        }
        out_path = out_dir / f"{run_id}.json"
        out_path.write_text(json.dumps(out, indent=2) + "\n")
        written.append(run_id)

    print(f"wrote {len(written)} baseline run files to {out_dir.relative_to(REPO_ROOT)}")
    for run_id in written:
        print(f'  "{run_id}",')
    print("remember to add these ids to data/memsyco-rerankmem-hint/meta.json -> runs")


if __name__ == "__main__":
    main()
