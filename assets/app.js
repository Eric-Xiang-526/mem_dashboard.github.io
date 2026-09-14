const state = {
  registry: null,
  meta: null,
  runs: [],
  datasetId: null,
};

const els = {
  datasetTabs: document.getElementById("dataset-tabs"),
  datasetDesc: document.getElementById("dataset-desc"),
  sections: document.getElementById("sections"),
};

const GROUPS = ["main", "ablation", "other"];
const GROUP_LABEL = { main: "Main experiments", ablation: "Ablation experiments", other: "Other experiments" };
const GROUP_VAR = { main: "--cat-main", ablation: "--cat-ablation", other: "--cat-other" };

init();

async function init() {
  state.registry = await (await fetch("data/registry.json")).json();

  els.datasetTabs.innerHTML = state.registry.datasets
    .map((ds, i) => `<button class="tab${i === 0 ? " is-active" : ""}" data-id="${escapeHtml(ds.id)}" role="tab">${escapeHtml(ds.name)}</button>`)
    .join("");

  els.datasetTabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    [...els.datasetTabs.children].forEach((t) => t.classList.remove("is-active"));
    btn.classList.add("is-active");
    loadDataset(btn.dataset.id);
  });

  if (state.registry.datasets.length) {
    await loadDataset(state.registry.datasets[0].id);
  } else {
    els.datasetDesc.textContent = "No datasets registered yet. Add one to data/registry.json.";
  }
}

async function loadDataset(id) {
  const entry = state.registry.datasets.find((d) => d.id === id);
  if (!entry) return;
  state.datasetId = id;

  state.meta = await (await fetch(`${entry.path}meta.json`)).json();
  state.runs = await Promise.all(
    state.meta.runs.map((runId) => fetch(`${entry.path}runs/${runId}.json`).then((r) => r.json()))
  );

  els.datasetDesc.textContent = state.meta.description || "";
  renderSections();
}

function taskValue(run, taskId) {
  const r = run.results.find((x) => x.task === taskId);
  return r ? r.headline_value : null;
}

function taskMetrics(task) {
  return task.metrics && task.metrics.length ? task.metrics : [{ key: task.headline_metric, label: "Value" }];
}

function taskMetricValue(run, task, metricKey) {
  const r = run.results.find((x) => x.task === task.id);
  if (!r) return null;
  const v = metricKey === task.headline_metric ? r.headline_value : r[metricKey];
  return typeof v === "number" ? v : null;
}

function runMean(run) {
  const vals = state.meta.tasks.map((t) => taskValue(run, t.id)).filter((v) => v !== null && v !== undefined);
  if (!vals.length) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function renderSections() {
  els.sections.innerHTML = GROUPS.map((g) => sectionHtml(g)).join("");
}

function sectionHtml(group) {
  const runs = state.runs.filter((r) => r.group === group);
  const sorted = [...runs].sort((a, b) => (runMean(b) ?? -1) - (runMean(a) ?? -1));

  const totalMetricCols = state.meta.tasks.reduce((n, t) => n + taskMetrics(t).length, 0);
  const bodyHtml = sorted.length
    ? sorted.map((run) => rowHtml(run)).join("")
    : `<tr><td colspan="${totalMetricCols + 3}"><div class="empty-state">No runs in this group yet.</div></td></tr>`;

  return `
    <section class="run-section">
      <h2 class="section-title">
        <span class="badge-dot" style="background:var(${GROUP_VAR[group]})"></span>
        ${GROUP_LABEL[group]}
      </h2>
      <div class="table-scroll">
        <table class="results-table">
          <thead>
            <tr>
              <th rowspan="2">Run</th>
              ${state.meta.tasks.map((t) => `<th colspan="${taskMetrics(t).length}">${escapeHtml(t.short)}</th>`).join("")}
              <th rowspan="2">Avg</th>
              <th rowspan="2">Notes</th>
            </tr>
            <tr>
              ${state.meta.tasks.map((t) => taskMetrics(t).map((m) => `<th class="metric-subhead">${escapeHtml(m.label)}</th>`).join("")).join("")}
            </tr>
          </thead>
          <tbody>${bodyHtml}</tbody>
        </table>
      </div>
    </section>
  `;
}

function rowHtml(run) {
  const cells = state.meta.tasks
    .map((t) =>
      taskMetrics(t)
        .map((m) => {
          const v = taskMetricValue(run, t, m.key);
          if (v === null || v === undefined) return `<td class="metric-cell">—</td>`;
          const { bg, fg } = seqColor(v);
          return `<td class="metric-cell" style="background:${bg};color:${fg}">${pct(v)}</td>`;
        })
        .join("")
    )
    .join("");
  const m = runMean(run);
  const n = run.results[0] ? run.results[0].n_judged : null;
  const sub = [run.date ? run.date.slice(0, 10) : "", n === null || n === undefined ? "" : `n=${n}`]
    .filter(Boolean)
    .join(" · ");
  return `
    <tr>
      <td>
        <div class="run-cell">
          <span class="run-label">${escapeHtml(run.label)}</span>
          ${sub ? `<span class="run-sub">${sub}</span>` : ""}
        </div>
      </td>
      ${cells}
      <td class="mean-cell">${m === null ? "—" : pct(m)}</td>
      <td class="notes-cell">${escapeHtml(run.description || "")}</td>
    </tr>
  `;
}

function seqColor(value) {
  const idx = Math.max(0, Math.min(6, Math.floor(value * 7)));
  const isDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const bg = `var(--seq-${idx})`;
  const fg = isDark ? (idx <= 3 ? "#ffffff" : "#0b0b0b") : (idx >= 3 ? "#ffffff" : "#0b0b0b");
  return { bg, fg };
}

function pct(v) {
  return `${(v * 100).toFixed(1)}%`;
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
