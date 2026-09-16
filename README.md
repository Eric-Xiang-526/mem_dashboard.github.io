# Mem Dashboard

A static, dependency-free HTML/CSS/JS console for browsing memory-system eval
results (main runs, ablations, smoke tests, whatever) across multiple
datasets/handoffs. No backend, no build step — deploy as-is with GitHub
Pages (Settings → Pages → deploy from branch, root).

## Structure

```
index.html                    page shell
assets/style.css              theme tokens + layout
assets/app.js                 fetches data/*.json and renders the sections/tables
data/registry.json            list of datasets shown in the top tab bar
data/<dataset-id>/
  meta.json                    dataset name/description + task list + run order
  runs/<run-id>.json           one eval run: label, group, description, results
scripts/ingest_run.py         legacy helper: summary.json + run_config.txt -> run JSON
scripts/ingest_outputs_run.py current helper: outputs/<gen_run>/<judge_model>/<ts>/
                              (judged_<task>.jsonl or results_<task>.json) -> run JSON
scripts/ingest_locomo_scored_summary.py
                              locomo-refined helper: predictions_..._scored_summary.json
                              -> run JSON (single "locomo_qa" task)
scripts/ingest_ablation_embedded_judge.py
                              ablation helper: generation/extract_results.jsonl with an
                              inline per-row "judge" dict -> run JSON
```

The dataset switcher is a tab bar (one tab per dataset, more will be added
over time). Within a dataset, results are always shown as three static
stacked sections — Main / Ablation / Other — never behind a filter click.

Everything is plain JSON fetched client-side — adding a result means adding
or editing a JSON file, not touching the JS.

## Data model

`data/<dataset>/meta.json`:

```json
{
  "id": "memsyco-rerankmem-hint",
  "name": "MemSyco · RerankMem (Hint)",
  "description": "what this handoff is testing",
  "tasks": [
    {
      "id": "task_id",
      "short": "short_label",
      "headline_metric": "metric_name",
      "metrics": [
        { "key": "metric_name", "label": "Acc." },
        { "key": "other_metric_name", "label": "Syco.Rate" }
      ]
    }
  ],
  "runs": ["run_id_1", "run_id_2"]
}
```

`data/<dataset>/runs/<run-id>.json`:

```json
{
  "id": "run_id",
  "label": "Human label shown in the table",
  "group": "main | ablation | other",
  "description": "what this specific run is / why it exists",
  "generation_model": "qwen3-8b",
  "judge_models": ["deepseek-v4.1-flash"],
  "date": "2026-09-01T22:49:10",
  "results": [ { "task": "...", "headline_metric": "...", "headline_value": 0.0, "...": "..." } ]
}
```

`results[i].headline_value` is the number the dashboard uses for sorting
rows and for the Avg column (averaged across `meta.json`'s task list) —
it must equal whichever `results[i]` field `task.headline_metric` names.

- Each task in `meta.json` can list a `metrics` array — every entry becomes
  its own column under that task's header (a two-row `<thead>`: task name
  spanning its columns, then each metric's `label` underneath), rendered
  side by side, not nested inside one cell. The first entry is normally the
  same field as `headline_metric` (used for row sort/Avg); any further
  entries just look up that field name directly on `results[i]`. Omitting
  `metrics` falls back to a single "Value" column showing `headline_value`.
- **group** drives which of the three static sections (Main / Ablation /
  Other) a run's row lands in, and the section-title dot color (main = blue,
  ablation = orange, other = aqua/green). Keep to these three so the fixed
  color order stays meaningful as more datasets are added.
- Metric values are treated as an absolute 0–100% scale (not normalized per
  column), so the heatmap stays comparable as more runs/tasks are added
  later.
- `judge_models` records which judge model(s) actually produced each run's
  numbers — a run can mix judges per task when only some tasks have been
  re-judged with the preferred model yet.

## Adding a new run to an existing dataset

The current eval pipeline writes to
`outputs/<generation_run>/<judge_model>/<timestamp>/`, either as
`judged_<task>.jsonl` (raw per-example rows with a `judge` dict) or
`results_<task>.json` (pre-aggregated). Ingest a generation-run folder with:

```
python3 scripts/ingest_outputs_run.py \
  --run-dir /path/to/outputs/<generation_run> \
  --dataset memsyco-rerankmem-hint \
  --run-id <run_id> \
  --label "<label>" \
  --group main \
  --description "<what this run/arm tests>"
```

This defaults to `deepseek-v4.1-flash` as the judge, falling back
per-task to `deepseek-v4-flash` (or whatever `--judge-priority` lists) when
the preferred judge hasn't scored that task yet. Then add `<run_id>` to
`data/<dataset>/meta.json` → `runs`.

(`scripts/ingest_run.py` still works for the older `summary.json` +
`run_config.txt` run-directory shape, if that ever shows up again.)

## Adding a new dataset

1. `mkdir -p data/<new-dataset-id>/runs`
2. Write `data/<new-dataset-id>/meta.json` (name, description, tasks, runs).
3. Ingest each run as above.
4. Add `{ "id": ..., "name": ..., "path": "data/<new-dataset-id>/" }` to
   `data/registry.json`.

## Current status

- Dataset: `memsyco-rerankmem-hint`, sourced from
  `infer/handoffs/memsyco-rerankmem-hint/outputs`.
- Four generation-run folders ingested, all tagged `main`, all fully judged
  (5/5 tasks) by `deepseek-v4.1-flash`:
  `local_qwen3_8b_live_traj`, `local_hint_rl134_live_traj`,
  `local_hint_memonly_needs_iter134_live_traj`,
  `local_hint_4b_instruct2507_live_traj`.
- Headline metric per task is the paper's "Acc." column (first metric):
  `accuracy_avg` for scope/evidence, `objective_correctness_avg` for
  objective fact, `answer_accuracy_avg` for personalized use,
  `uses_latest_preference_avg` for valid selection. The old composite
  `*_pass_avg` fields (which weren't always equal to Acc.) are kept as
  extra fields in each result but no longer drive the table.
- Pass rate denominator = every row in `judged_<task>.jsonl` (`n_judged`),
  including rows with `judge_parse_ok=false`/`judge_error` set — those just
  never count as a pass. This matches how the eval harness itself reports
  pass rate off the raw judged file, so dashboard numbers line up exactly
  with what's reported from the run.
- `n_judged` varies by task for one structural reason: `valid_memory_selection`
  has 350 samples by design vs. 300 for the other four tasks.
- Nine Qwen3-8B literature baselines added (`main` group), Acc.-only,
  transcribed from the paper's main-results table via
  `scripts/seed_qwen3_8b_baselines.py`: No Memory, Full Dialog, NaiveRAG,
  Mem0, A-Mem, LightMem, MemGPT, MemoryBank, SuperMemory. `No Memory` only
  reports Objective Fact Judgment (the only task it's evaluated on in the
  paper); other tasks show as `—`. These have no `n_judged` (not resampled
  here, just literature numbers).
- The three old `rerank_online_hint*` runs (built from the now-deprecated
  `outputs/_legacy/` source) were removed.
- Each task in `memsyco-rerankmem-hint`'s `meta.json` now lists a `metrics`
  array so the paper's second column per task renders as its own column
  (side by side with Acc., not nested inside one cell), labeled the way the
  paper labels it: "Syco.Rate" for scope / evidence conflict / objective
  fact (`incorrectly_used_preference_avg`, `misled_by_conflicting_memory_avg`,
  `preference_answer_selected_avg`), "Correct Mem Use" for personalized use
  (`preference_used_avg`), "Outdated Mem" for valid selection
  (`outdated_preference_contamination_avg`). Only the four real
  RerankMem-family runs have this second field populated — the Qwen3-8B
  literature baselines were only transcribed Acc.-only, so their second
  column shows `—`.
- Dataset: `locomo-refined` added, sourced from
  `infer/handoffs/locomo-rerankmem-hint/outputs`, via
  `scripts/ingest_locomo_scored_summary.py` (reads a flat
  `predictions_<run>_scored_summary.json`, one task `locomo_qa` with all
  three metrics shown side by side — "LLM Score" (`llm_score`, also the
  headline/sort field, the pipeline's own `primary_metric`), "F1"
  (`f1_score`), "BLEU" (`bleu_score`); a per-category (1-4) breakdown is
  kept as extra fields, not currently rendered).
  Two runs ingested so far, both `main`, both n=1382:
  `locomo_hint_instruct2507` (llm_score 0.5014) and `locomo_hint_rl134`
  (llm_score 0.4993). A third run, `predictions_locomo_hint_rl134_classic_
  20260914_1544.jsonl`, has predictions but **no `_scored*` file yet** — it
  hasn't been scored, so it isn't ingested. Add it once its
  `_scored_summary.json` shows up.
- Dataset and run descriptions are placeholders (`TODO`) pending the
  write-up, except locomo-refined's dataset description and the two ingested
  run descriptions, which are filled in.
- Three RerankMem ablations added to `memsyco-rerankmem-hint` (`ablation`
  group): `ablation_full_both` (decompose + rerank both enabled),
  `ablation_full_decomp_only` (rerank stage removed), and
  `ablation_full_rerank_only` (decompose stage removed). These runs judge
  inline — each row of `generation/extract_results.jsonl` already carries
  its own `judge` dict (same field names as `judged_<task>.jsonl`, e.g.
  `accuracy`, `incorrectly_used_preference`, `scope_pass`) rather than
  writing separate `<judge_model>/<timestamp>/judged_<task>.jsonl` files,
  so they're ingested with `scripts/ingest_ablation_embedded_judge.py`
  instead of `ingest_outputs_run.py` (same `TASK_JUDGE_FIELDS` mapping,
  so results line up with the four main runs). Judge model
  (`deepseek-v4.1-flash`) isn't recorded per-row in this layout and was
  confirmed manually rather than read from the data.
