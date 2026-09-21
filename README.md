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
scripts/ingest_memtrap_run.py current helper: memtrap_eval_<tag>/<task>/round1_judge_results_
                              retrieved_memory_<task>_<judge_model>.json (1-5 dimension
                              scores) -> run JSON
scripts/ingest_persist_run.py current helper: checkpoint_<run>.json (entries dict with
                              embedded 1-5 judge.score, split by failure_type) -> run JSON
scripts/ingest_memsyco_flat_judged.py current helper: flat judged_<shortname>_<run>.jsonl
                              files (no <judge_model>/<timestamp>/ nesting, abbreviated
                              task-name prefixes) -> run JSON
scripts/ingest_memtrap_ablation_summary.py current helper: predictions_ablation_<variant>_
                              scored_summary.json (already-aggregated by_dataset.<task>.
                              dimensions.<dim>.mean_raw_1_5) -> run JSON
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
- A task can set `"format": "raw"` in `meta.json` to render its values as a
  plain 2-decimal number instead of the default `"pct"` (×100 with a `%`
  suffix) — use `raw` for benchmarks whose judge already scores on a fixed
  scale that isn't [0,1], e.g. MemTrapBench/PersistBench's 1-5 LLM-judge
  scores. Omitting `format` keeps the old `pct` behavior.
- An earlier sequential-blue heatmap (`seqColor()`) assumed every metric
  lived on a [0,1] scale, which broke once `raw`-format 1-5 scores were
  added, so it was removed outright rather than special-cased per format.
  Cells are otherwise plain — no background fill, no cell borders — but the
  best and second-best distinct value in each metric column (scoped to the
  section it's rendered in: Main / Ablation / Other are ranked separately,
  never against each other) get called out: best in red + bold + underline,
  second-best in orange. This is computed client-side by `columnRanks()` in
  `app.js`, not stored in the data.
- A metric is "higher is better" by default (so the max value in a column is
  "best"). Set `"lowerIsBetter": true` on a `metrics[]` entry in `meta.json`
  to flip this so the *minimum* value counts as best instead — used for
  metrics that are actually failure rates despite living in the same table,
  e.g. `memsyco-rerankmem-hint`'s "Syco.Rate" and "Outdated Mem" columns.
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
- Nine Qwen3-8B baselines added (`main` group): No Memory, Full Dialog,
  NaiveRAG, Mem0, A-Mem, LightMem, MemGPT, MemoryBank, SuperMemory.
  Originally hand-transcribed Acc.-only from the paper's main-results table
  via `scripts/seed_qwen3_8b_baselines.py`; superseded by real judged
  results (all metrics, not just Acc., plus `n_judged`/`n_scored` counts)
  ingested from `qwen3_8b_paper_tasks_extracted/qwen3_8b_paper_tasks/` via
  `scripts/ingest_qwen3_8b_paper_tasks.py`. `No Memory` only reports
  Objective Fact Judgment (the only task it's evaluated on); other tasks
  show as `—`.
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
  RerankMem-family runs and the Qwen3-8B baselines (now real judged
  results) have this second field populated.
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
- A fourth ablation-group row, `ablation_baseline_hint_rl134`, duplicates
  `local_hint_rl134_live_traj`'s results (full, unablated RerankMem) so the
  three ablations above have a reference point inside the same section.
  Row order within a section is always sorted by descending Avg, not by
  `meta.json`'s `runs` list order, so this row does not literally render
  first — it lands wherever its score ranks (currently 2nd of the four
  ablation-group rows).
- Three more LoCoMo ablation runs added to `locomo-refined` (`ablation`
  group, its first-ever ablation rows), same `ablation_full_both` /
  `ablation_full_decomp_only` / `ablation_full_rerank_only` split as the
  MemSyco ablations above, all n=1382, ingested with the existing
  `ingest_locomo_scored_summary.py --group ablation`: llm_score 0.6230 /
  0.6288 / 0.5507 respectively.
- Two new datasets added: `memtrap-rerankmem-hint` (MemTrapBench: 6
  adversarial memory-trap tasks — hallucination, hurt, inertia,
  number_game, poison, unclear) and `persist-rerankmem-hint` (PersistBench:
  3 memory-persistence failure modes — cross_domain, sycophancy,
  beneficial_memory_usage). Both use `"format": "raw"` on every task —
  their LLM judge scores 1-5, not a [0,1] pass rate, so values render as
  plain 2-decimal numbers rather than a percentage.
  - MemTrapBench: judged per-task by 1-5 scores across 2-4 dimensions
    (`dimension_1_factual_correctness`, `dimension_2_instruction_compliance`,
    `dimension_3_relevance_purity`, `dimension_4_delivery_efficiency`; only
    2 dims for `number_game`, and `poison` uses its own safety-specific
    dimension names). "Overall" is the mean across all valid per-row
    dimension scores; a handful of rows per task fail to parse
    (`{"parse_error": true, "raw": "..."}` instead of real dimension
    scores) and are excluded from the average but still counted in
    `n_judged`. Only `deepseek-v4.1-flash` judged results are used — a
    second judge model, `qwen3-30b-a3b-instruct-2507`, mostly failed
    (`skipped`/`target_error` on most rows for several tasks) and is not
    ingested. Two runs ingested, both `main`: `memtrap_hint_instruct2507`
    and `memtrap_hint_rl134`. Ingested with `scripts/ingest_memtrap_run.py`.
  - PersistBench: `checkpoint_<run>.json`'s `entries` is a dict keyed by
    hash id, not a list; each entry carries one `failure_type` and a
    `results.<model>.generations[0].judge.score` (1-5 int). Each
    `failure_type` is treated as its own dashboard task/column (plus the
    usual Avg column across all three). Judge model is read from
    `metadata.judge_model` in the checkpoint file itself
    (`deepseek-v4.1-flash` for both ingested runs) rather than assumed.
    Two runs ingested, both `main`: `persist_hint_instruct2507` and
    `persist_hint_rl134`. Ingested with `scripts/ingest_persist_run.py`.
- Two more ablations added to `memsyco-rerankmem-hint` (`ablation` group):
  `ablation_dataaug_resume` (RL134-classic checkpoint continued/resumed
  training on the augmented dataset) and `ablation_dataaug_scratch`
  (RL134-classic trained from scratch on the augmented dataset), sourced
  from `infer/handoffs/memsyco-rerankmem-hint/outputs/
  memsyco_hint_rl134_classic_dataaug_{resume,scratch}/`. Same standard
  `<judge_model>/<timestamp>/judged_<task>.jsonl` layout as the main runs,
  ingested with the existing `ingest_outputs_run.py` (no new script
  needed). Neither source directory has a `generation/extract_results.jsonl`
  to auto-detect the generation model from, so `generation_model` was set
  to `"qwen3-8b"` by hand to match the rest of the RL134-classic family.
  Both fully judged (5/5 tasks) by `deepseek-v4.1-flash`. Resume scores
  slightly lower than scratch on Avg (0.528 vs 0.552) and both land below
  the full-RerankMem baseline (0.552) within this ablation section.
- Two new datasets added for the `gpt-5.6-luna` base model, sourced from
  `infer/outputs/luna/`: `memsyco-luna-hint` and `locomo-luna-hint`. Kept as
  separate tabs rather than folded into the existing
  `memsyco-rerankmem-hint`/`locomo-refined` tabs' Other group, since
  gpt-5.6-luna is a different base model than the qwen3-8b/qwen3-4b-
  instruct-2507/rl-iter134 family those tables compare — mixing them into
  one ranked table would be misleading.
  - `memsyco-luna-hint`: same 5 tasks/metrics as `memsyco-rerankmem-hint`.
    Source data (`infer/outputs/luna/memsyco/`) is laid out as flat
    `judged_<shortname>_<run>.jsonl` files (no `<judge_model>/<timestamp>/`
    nesting) using abbreviated task prefixes (`scope`, `evid`, `obj`,
    `pers`, `valid`) — a layout distinct from both `ingest_outputs_run.py`
    and `ingest_ablation_embedded_judge.py`, so ingested with the new
    `scripts/ingest_memsyco_flat_judged.py` instead (same
    `TASK_JUDGE_FIELDS` mapping, so results are directly comparable to the
    main pipeline's numbers). Base model (`gpt-5.6-luna`) and judge model
    (`deepseek-v4.1-flash`) are both read from the data, not assumed. Two
    runs ingested, both `main`: `memsyco_luna_hint_instruct2507` and
    `memsyco_luna_hint_rl134_classic`.
  - `locomo-luna-hint`: same single `locomo_qa` task as `locomo-refined`.
    Ingested with `scripts/ingest_locomo_scored_summary.py --dataset
    locomo-luna-hint` (the script gained a `--dataset` flag this round;
    previously it always wrote to the hardcoded `locomo-refined`). Only
    `locomo_luna_hint_instruct2507` (llm_score 0.6787, n=1382) is ingested
    so far — the rl134_classic variant has predictions but no
    `_scored_summary.json` yet, same situation as `locomo-refined`'s
    still-unscored `rl134_classic` run. Add it once scoring finishes.
- Three RerankMem ablations added to `memtrap-rerankmem-hint` (`ablation`
  group): `memtrap_ablation_full_both` (decompose + rerank both enabled),
  `memtrap_ablation_full_decomp_only` (rerank stage removed), and
  `memtrap_ablation_full_rerank_only` (decompose stage removed) — the same
  three-way split as the existing MemSyco/LoCoMo ablations, generation
  model `qwen3-8b`. Source data
  (`predictions_ablation_<variant>_scored_summary.json`) is a different
  shape than the main memtrap runs: judge output is already aggregated per
  dimension (`by_dataset.<task>.dimensions.<dim>.{n, mean_raw_1_5}`)
  instead of raw per-row `round1_judge_results_*.json` files, so these are
  ingested with the new `scripts/ingest_memtrap_ablation_summary.py`
  instead of `ingest_memtrap_run.py`. Each task's `overall_avg` is the
  n-weighted mean across that task's dimension means, mathematically
  equivalent to `ingest_memtrap_run.py`'s row-level average — so ablation
  rows are directly comparable to `memtrap_hint_instruct2507`/
  `memtrap_hint_rl134`. All three runs cover all 6 tasks.
- A fourth ablation-group row, `ablation_baseline_hint_rl134`, duplicates
  `memtrap_hint_rl134`'s results (full, unablated RerankMem) so the three
  memtrap ablations above have a reference point inside the same section —
  same pattern as `memsyco-rerankmem-hint`'s `ablation_baseline_hint_rl134`.
  Row order within a section is always sorted by descending Avg, so this
  row doesn't necessarily render first; here it happens to rank 1st of the
  four ablation-group rows since none of the three ablations beat full
  RerankMem.
- Two more ablations added to `locomo-refined` (`ablation` group):
  `locomo_ablation_dataaug_resume` and `locomo_ablation_dataaug_scratch` —
  same RL134-classic DataAug resume/scratch split as the memsyco-side
  ablations above, sourced from `infer/outputs/locomo/predictions_locomo_
  hint_rl134_classic_dataaug_{resume,scratch}_scored_summary.json`. Same
  flat `_scored_summary.json` shape the existing
  `ingest_locomo_scored_summary.py` already handles, so no new script was
  needed; `generation_model` was passed explicitly as `"qwen3-8b"` via
  `--generation-model` (this script takes it as a flag, unlike
  `ingest_outputs_run.py` which needed a manual post-hoc fix for the
  memsyco-side DataAug runs). Both n=1382: resume llm_score=0.5434,
  scratch llm_score=0.4949 — both land below the two `full_*` ablations
  (0.623/0.629) and the `rerank_only` ablation (0.551) within this section.
- Three RerankMem ablations added to `locomo-luna-hint` (`ablation` group,
  its first-ever ablation rows): `locomo_luna_ablation_full_both`,
  `locomo_luna_ablation_decomp_only`, `locomo_luna_ablation_rerank_only` —
  same three-way split as `locomo-refined`'s ablations, generation model
  `gpt-5.6-luna` (matching this dataset's existing main run). Sourced from
  `infer/outputs/luna/locomo/predictions_ablation_luna_{both,decomp_only.
  dedup,rerank_only}_scored_summary.json`, same flat `_scored_summary.json`
  shape as every other locomo ingestion, no new script needed. All three
  n=1382: full_both llm_score=0.6143, decomp_only llm_score=0.6288,
  rerank_only llm_score=0.5586 — decompose-only ranks highest, mirroring
  the same ordering seen in `locomo-refined`'s ablation section.
- One new ablation row, `ablation_dataaug_scratch_decomp_rerank`, added to
  all three of `memsyco-rerankmem-hint`, `locomo-refined` (as
  `locomo_ablation_dataaug_scratch_decomp_rerank`), and
  `persist-rerankmem-hint` (its first-ever ablation row) — a fresh
  RL134-classic-from-scratch-on-DataAug run with the full pipeline
  (decompose + rerank both enabled), distinct from the existing
  `ablation_dataaug_scratch`/`locomo_ablation_dataaug_scratch` rows (those
  came from a different source directory,
  `memsyco_hint_rl134_classic_dataaug_scratch`, predating this pipeline
  variant). Sourced from `infer/outputs/{memsyco,locomo,persist}/`
  files/dirs timestamped `20260918`-`20260919`. memsyco and locomo used the
  existing `ingest_outputs_run.py`/`ingest_locomo_scored_summary.py`
  (memsyco again needed the `generation_model` hand-fix to `"qwen3-8b"`,
  same gap as the other DataAug ablations). Persist used
  `ingest_persist_run.py` against `checkpoint_persist_hint_rl134_classic_
  20260918_1742.json`; its `generation_model` was also normalized to
  `"qwen3-8b"` by hand (the raw checkpoint's model tag,
  `persist_qwen3-4b-rl-multiscope-fromscratch-iter148_qwen3-8b`, was kept
  out of this field for consistency with sibling ablation rows). Its source
  checkpoint's `metadata.judge_model` said `moonshotai/kimi-k2-thinking`,
  but that was a mislabel in the checkpoint metadata — this run was
  actually judged by `deepseek-v4.1-flash`, same as every other
  persist-rerankmem-hint run, so `judge_models` was corrected accordingly
  and its score (Avg 2.81) is directly comparable to the two main-section
  rows (3.26/2.90). memsyco Avg 0.578 (2nd of 7 ablation rows,
  just behind `ablation_full_both`'s 0.579); locomo Avg 0.552 (mid-pack of
  6 ablation rows).
- Six Qwen3-8B baselines added to `locomo-refined` (`main` group):
  `baseline_a_mem_qwen3_8b`, `baseline_memgpt_qwen3_8b`,
  `baseline_mem0_qwen3_8b`, `baseline_memorybank_qwen3_8b`,
  `baseline_naiverag_qwen3_8b`, `baseline_supermemory_qwen3_8b` — the same
  baseline family already present in `memsyco-rerankmem-hint`, now added
  to LoCoMo too. Sourced from `infer/outputs/locomo/<Method>_ctrl_20260918/
  predictions_<method>_scored_summary.json` (the source folder for the
  Mem0 baseline is named `MemZero_ctrl_20260918`; labeled "Mem0" here to
  match the memsyco-side naming convention for the same tool). All
  n=1382, ingested with the existing `ingest_locomo_scored_summary.py
  --group main --generation-model qwen3-8b` (generation model isn't
  recorded in these source files, so it was passed explicitly to match
  the memsyco baseline family convention). llm_score: MemoryBank 0.528
  (best of the six, and above both existing RerankMem main-section rows),
  A-Mem 0.506, MemGPT 0.502, NaiveRAG 0.436, Mem0 0.295, SuperMemory 0.208.
- Main-table restructuring across `memsyco-rerankmem-hint`, `locomo-refined`,
  and `persist-rerankmem-hint` (the three datasets that have an "Ours"-style
  DataAug-scratch-decomp+rerank result; `memtrap-rerankmem-hint` left
  untouched since it has no such result yet):
  - The old "Hint (Instruct-2507)"-style main row (the 4B-instruct2507
    generation model, no RL training) is relabeled `no_training_4b` and
    moved from `main` to `ablation` in all three datasets — it's a
    no-RL-training reference point for the ablation section, not a
    competitive main-table entry. Run ids unchanged
    (`local_hint_4b_instruct2507_live_traj` / `locomo_hint_instruct2507` /
    `persist_hint_instruct2507`), only `label`/`group`/`description`
    edited.
  - The old "Hint (RL134)"-style main row (RL-iter134 generation, trained
    on the pre-DataAug dataset) is relabeled `old_data_4b` and moved from
    `main` to `ablation` in all three datasets, for the same reason — it's
    now a "trained on old data" reference point, not the headline result.
    Run ids unchanged (`local_hint_rl134_live_traj` / `locomo_hint_rl134` /
    `persist_hint_rl134`).
  - `ablation_dataaug_scratch_decomp_rerank` (and its locomo counterpart
    `locomo_ablation_dataaug_scratch_decomp_rerank`) — the newest
    RL134-classic-scratch-DataAug, full-pipeline result added in the
    previous round — is relabeled `Ours` and moved from `ablation` to
    `main` in all three datasets. This is now the headline row: memsyco
    Avg 0.578, locomo Avg 0.552, persist Avg 2.81 — each currently the top
    (or only) row in its dataset's main section.
  - `memsyco-rerankmem-hint`'s `ablation_baseline_hint_rl134` (a duplicate
    of the RL134 result kept only as a same-section reference point for
    the ablation rows) was deleted — now that `old_data_4b` carries the
    identical RL134 numbers directly into the ablation section, the
    duplicate baseline row would have shown the same score twice in one
    table.
- `memtrap-rerankmem-hint` caught up to the same restructuring once its own
  "Ours" result showed up (see below): `memtrap_hint_instruct2507` →
  `no_training_4b` and `memtrap_hint_rl134` → `old_data_4b`, both moved
  `main` → `ablation`; its `ablation_baseline_hint_rl134` duplicate (same
  redundancy as memsyco's) was deleted for the same reason.
- `ours_dataaug_scratch_decomp_rerank` added to `memtrap-rerankmem-hint`
  (`main` group) — the memtrap counterpart of the "Ours" result already
  added to the other three datasets: RL134-classic trained from scratch on
  the augmented dataset, full pipeline (decompose + rerank both enabled).
  Sourced from `infer/outputs/memtrap/predictions_rlfromscratch_ablate_
  both_scored_summary.json` (same pre-aggregated `by_dataset.<task>.
  dimensions.<dim>.mean_raw_1_5` shape as the other memtrap ablations,
  covers all 6 tasks, judge `deepseek-v4.1-flash` read straight from
  `target_model`), ingested with the existing
  `ingest_memtrap_ablation_summary.py --group main --generation-model
  qwen3-8b`. Avg 4.199 — now the top row in memtrap's main section,
  narrowly ahead of `old_data_4b`'s 4.195.
- New dataset tab `locomo-origin` ("LoCoMo (Origin)") added, covering the
  ORIGINAL (unrefined) LoCoMo QA set — 1986 questions across 5 official
  snap-research categories, scored with token-F1 via a new script,
  `scripts/ingest_locomo_origin_run.py` (re-implements
  `infer/handoffs/locomo-origin/score_origin.py`'s normalize/stem/F1 logic
  standalone, reading gold answers + categories from
  `infer/handoffs/locomo-origin/bench/data/public/questions.jsonl`).
  Category 5 ("adversarial", refusal-style scoring, not comparable to
  token-F1 on the other four) is **excluded from every row**: only
  categories 1 (multi-hop), 2 (temporal), 3 (open-domain), 4 (single-hop)
  are shown as metrics, and the headline `avg4_f1` is the n-weighted mean
  over just those four (1540 of the 1986 questions). The excluded
  category-5 score/count is still stored on each run's result object
  (`cat5_adversarial_f1_excluded` / `_n_excluded`) for reference but never
  surfaced in `metrics`, so it can't accidentally show up in the UI.
  Populated from `infer/outputs/locomo_origin/`: 6 baselines (A-Mem,
  MemGPT, Mem0/MemZero, MemoryBank, NaiveRAG, SuperMemory) plus `ours_full`
  ("Ours", full RerankMem hint pipeline), all `main` group, all
  `qwen3-8b` generation. Avg4 F1: MemoryBank 0.410, A-Mem 0.371, MemGPT
  0.370, NaiveRAG 0.358, Mem0 0.238, SuperMemory 0.177, **Ours 0.416**
  (top of the table). Judge field is `token_f1` (deterministic metric, no
  LLM judge involved) rather than a model name.
- Added 6 baselines to `memtrap-rerankmem-hint`'s main section (A-Mem,
  MemGPT, Mem0/MemZero, MemoryBank, NaiveRAG, SuperMemory — same set as
  the locomo-origin/locomo-refined baselines), from
  `infer/outputs/memtrap/baseline/<System>/memtrap_eval_retrieved_<tag>/`,
  ingested with the existing `ingest_memtrap_run.py` (raw
  `round1_judge_results_retrieved_memory_<task>_<judge>.json` per-task
  layout, same as the other memtrap runs). The judge filenames say
  `qwen3-8b`, but per user confirmation that's a labeling mistake — these
  were actually judged by `deepseek-v4.1-flash` like every other row in
  this table, so `judge_models` was corrected post-ingestion and each
  description notes the discrepancy. Task-mean scores: NaiveRAG 3.28,
  A-Mem 3.25, MemoryBank 3.17, Mem0 3.11, MemGPT 2.74, SuperMemory 2.40 —
  all well below `Ours` (4.20) and `old_data_4b` (4.19).
