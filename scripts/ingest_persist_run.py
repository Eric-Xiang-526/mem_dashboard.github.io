#!/usr/bin/env python3
"""
Convert one PersistBench checkpoint file (checkpoint_<run>.json, with an
`entries` dict keyed by hash id, each entry {memories, query, failure_type,
results: {<model_name>: {generations: [{memory_response, error, judge:
{score, reasoning}}]}}}) into a dashboard run JSON under
data/<dataset>/runs/<run_id>.json.

judge.score is an integer 1-5 (higher = better). Each of PersistBench's 3
failure_type categories (cross_domain, sycophancy, beneficial_memory_usage)
is treated as its own "task" so the dashboard renders one column per
category plus the overall Avg.

Usage:
  python3 scripts/ingest_persist_run.py \
      --checkpoint /path/to/outputs/persist/checkpoint_local_persist_hint_instruct2507_20260914_1845.json \
      --dataset persist-rerankmem-hint \
      --run-id persist_hint_instruct2507 \
      --label "Hint (Instruct-2507)" \
      --group main \
      --description "one-line description of what this run tests"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

FAILURE_TYPES = ["cross_domain", "sycophancy", "beneficial_memory_usage"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--group", default="main", choices=["main", "ablation", "other"])
    ap.add_argument("--description", default="TODO: describe this run.")
    args = ap.parse_args()

    with Path(args.checkpoint).open() as fh:
        data = json.load(fh)

    judge_model = data.get("metadata", {}).get("judge_model", "unknown")
    entries = data["entries"]
    scores_by_ft: dict[str, list[float]] = {ft: [] for ft in FAILURE_TYPES}
    model_key = None
    for entry in entries.values():
        ft = entry.get("failure_type")
        if ft not in scores_by_ft:
            continue
        for model, r in entry.get("results", {}).items():
            model_key = model
            gens = r.get("generations") or []
            if not gens:
                continue
            judge = gens[0].get("judge")
            if judge and isinstance(judge.get("score"), (int, float)):
                scores_by_ft[ft].append(judge["score"])

    results = []
    for ft in FAILURE_TYPES:
        scores = scores_by_ft[ft]
        if not scores:
            continue
        avg = sum(scores) / len(scores)
        results.append({
            "task": ft,
            "n_judged": len(scores),
            "headline_metric": "score_avg",
            "headline_value": avg,
            "score_avg": avg,
        })

    if not results:
        raise SystemExit(f"no judged rows found in {args.checkpoint}")

    out = {
        "id": args.run_id,
        "label": args.label,
        "group": args.group,
        "description": args.description,
        "generation_model": model_key or "",
        "judge_models": [judge_model],
        "date": "",
        "results": results,
    }

    out_dir = REPO_ROOT / "data" / args.dataset / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.run_id}.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(results)}/{len(FAILURE_TYPES)} failure types)")
    print(f"remember to add \"{args.run_id}\" to data/{args.dataset}/meta.json -> runs")


if __name__ == "__main__":
    main()
