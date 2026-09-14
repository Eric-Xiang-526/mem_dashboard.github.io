#!/usr/bin/env python3
"""
Convert one eval run directory (summary.json + run_config.txt, the shape
produced by the memsyco/evoontomem eval harness) into a dashboard run JSON
under data/<dataset>/runs/<run_id>.json.

Usage:
  python3 scripts/ingest_run.py \
      --run-dir /path/to/handoffs/<dataset>/runs/<run_name> \
      --dataset memsyco-rerankmem-hint \
      --run-id rerank_online_hint_v3 \
      --label "RerankMem online hint (v3)" \
      --group main \
      --description "one-line description of what this run tests"

This only writes data/<dataset>/runs/<run-id>.json. Add the run id to
data/<dataset>/meta.json's "runs" list yourself so it shows up on the page —
that keeps ordering and grouping an explicit, reviewable edit.
"""
import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_run_config(text: str) -> dict:
    parsed = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("---"):
            continue
        for token in line.split():
            if "=" in token:
                k, v = token.split("=", 1)
                if re.fullmatch(r"-?\d+", v):
                    v = int(v)
                elif re.fullmatch(r"-?\d+\.\d+", v):
                    v = float(v)
                parsed[k] = v
    return parsed


def parse_timestamp(text: str) -> str:
    m = re.search(r"---\s*([\d-]+ [\d:]+)", text)
    return m.group(1).replace(" ", "T") if m else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, help="Directory containing summary.json and run_config.txt")
    ap.add_argument("--dataset", required=True, help="Dataset id, e.g. memsyco-rerankmem-hint")
    ap.add_argument("--run-id", required=True, help="Output run id (used as filename and dashboard key)")
    ap.add_argument("--label", required=True, help="Human-readable label shown in the dashboard")
    ap.add_argument("--group", default="other", choices=["main", "ablation", "other"])
    ap.add_argument("--description", default="TODO: describe this run.")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    summary_path = run_dir / "summary.json"
    config_path = run_dir / "run_config.txt"
    if not summary_path.exists():
        raise SystemExit(f"no summary.json in {run_dir}")

    results = json.loads(summary_path.read_text())
    generation_model = results[0]["generation_model"] if results else None

    run_config_text = config_path.read_text().strip() if config_path.exists() else ""

    out = {
        "id": args.run_id,
        "label": args.label,
        "group": args.group,
        "description": args.description,
        "generation_model": generation_model,
        "date": parse_timestamp(run_config_text),
        "run_config": run_config_text,
        "run_config_parsed": parse_run_config(run_config_text),
        "results": results,
    }

    out_dir = REPO_ROOT / "data" / args.dataset / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.run_id}.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {out_path.relative_to(REPO_ROOT)}")
    print(f"remember to add \"{args.run_id}\" to data/{args.dataset}/meta.json -> runs")


if __name__ == "__main__":
    main()
