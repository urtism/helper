import {loadArchivedAnalysis, monitorAnalysisRun} from "./analysis.js?v=20260922-1";

let records = [];
let selectedId = null;
let busy = false;
const workflowLabels = {
  prealignment: "Pre-alignment",
  alignment: "Alignment",
  preprocessing: "Pre-processing",
  variantcalling: "Variant calling",
  postprocessing: "Post-processing",
  annotation: "Annotation",
};

async function api(path = "", payload, method = "POST") {
  const response = await fetch(`/api/analysis/history${path}`, payload ? {
    method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload),
  } : method === "POST" ? {} : {method});
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : JSON.stringify(result.detail));
  return result;
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function table(headers, rows) {
  const wrapper = element("div", undefined, "history-table-scroll");
  const node = element("table");
  const head = element("tr");
  headers.forEach(label => head.append(element("th", label)));
  const thead = element("thead");
  thead.append(head);
  node.append(thead);
  const body = element("tbody");
  rows.forEach(values => {
    const row = element("tr");
    values.forEach(value => {
      const cell = element("td");
      if (value instanceof Node) cell.append(value);
      else cell.textContent = value ?? "—";
      row.append(cell);
    });
    body.append(row);
  });
  node.append(body);
  wrapper.append(node);
  return wrapper;
}

function date(value) { return value ? new Date(value).toLocaleString() : "—"; }
function status(message) { document.querySelector("#history-status").textContent = message; }

function renderList() {
  const query = document.querySelector("#history-search").value.toLowerCase();
  const filtered = records.filter(row => JSON.stringify(row).toLowerCase().includes(query));
  const rows = filtered.map(row => {
    const button = element("button", row.run_id, "ghost-button");
    button.addEventListener("click", () => select(row.id).catch(error => status(error.message)));
    const remove = element("button", "Delete", "danger-action");
    remove.addEventListener("click", () => removeRecord(row));
    return [button, date(row.created_at), row.status, row.samples.length,
      row.request.gene_panel_design || "—", row.request.pipeline_path || "Default",
      row.workflow.join(" → "), remove];
  });
  document.querySelector("#history-list").replaceChildren(rows.length
    ? table(["Run", "Started", "Status", "Samples", "Panel", "Pipeline", "Steps", "Actions"], rows)
    : element("p", records.length ? "No matching analyses." : "No archived analyses yet. New runs will appear here automatically.", "muted"));
}

async function removeRecord(record) {
  if (busy) return;
  if (!window.confirm(`Remove ${record.run_id} from history? Run files and results will not be deleted.`)) return;
  busy = true;
  status(`Removing ${record.run_id} from history…`);
  try {
    await api(`/${record.id}`, null, "DELETE");
    if (selectedId === record.id) {
      selectedId = null;
      const detail = document.querySelector("#history-detail");
      detail.hidden = true;
      detail.replaceChildren();
    }
    await refresh();
    status(`${record.run_id} removed from history. Results were left on disk.`);
  } catch (error) {
    status(error.message);
  } finally {
    busy = false;
  }
}

async function refresh() {
  const result = await api();
  records = result.runs;
  document.querySelector("#history-location").textContent = `Persistent archive: ${result.database}`;
  renderList();
}

async function select(id) {
  selectedId = id;
  const record = await api(`/${id}`);
  if (selectedId !== id) return;
  const detail = document.querySelector("#history-detail");
  detail.hidden = false;
  detail.replaceChildren(element("h3", record.run_id));
  const summary = element("p", statusSummary(record));
  summary.id = "history-detail-status";
  detail.append(summary);
  detail.append(element("p", `Working directory: ${record.run_dir}`, "muted"));
  if (record.parent_id) {
    const parent = element("button", "Open original run", "ghost-button");
    parent.onclick = () => select(record.parent_id).catch(error => status(error.message));
    detail.append(parent);
  }
  const actions = element("div", undefined, "history-actions");
  const runId = element("input");
  runId.placeholder = "New run ID (automatic if empty)";
  runId.setAttribute("aria-label", "New run ID");
  const workdir = element("input");
  workdir.value = record.request.workdir;
  workdir.setAttribute("aria-label", "Reanalysis working directory");
  const rerun = element("button", "Reanalyse");
  const modify = element("button", "Modify & reanalyse", "ghost-button");
  const resume = element("button", "Resume from cache", "ghost-button");
  const viewConsole = element("button", "View live console", "ghost-button");
  const restartPanel = element("div", undefined, "history-restart-panel");
  const restartLabel = element("label", "Restart from completed step");
  const restartStep = element("select");
  restartStep.setAttribute("aria-label", "Step to restart");
  for (const step of record.workflow || []) {
    restartStep.add(new Option(workflowLabels[step] || step, step));
  }
  const restart = element("button", "Restart from step", "ghost-button");
  restart.disabled = !restartStep.options.length;
  restartLabel.append(restartStep);
  restartPanel.append(restartLabel, restart);
  function showConsole(runDir, runId) {
    monitorAnalysisRun(runDir, runId);
    document.querySelector('[data-section="analysis"]')?.click();
    window.requestAnimationFrame(() => {
      document.querySelector(".analysis-console-panel")?.scrollIntoView({behavior: "smooth", block: "start"});
    });
  }
  async function replay(mode) {
    if (busy) return;
    busy = true;
    rerun.disabled = modify.disabled = resume.disabled = restart.disabled = restartStep.disabled = viewConsole.disabled = true;
    status(mode === "restart" ? `Restarting from ${workflowLabels[restartStep.value] || restartStep.value}…` : "Submitting analysis from archived settings…");
    try {
      const result = await api(`/${id}/replay`, {
        mode,
        run_id: runId.value,
        workdir: workdir.value,
        restart_from_step: mode === "restart" ? restartStep.value : "",
      });
      status(`Submitted ${result.run_id}`);
      await refresh();
      showConsole(result.run_dir, result.run_id);
    } catch (error) { status(error.message); }
    finally {
      busy = false;
      rerun.disabled = modify.disabled = resume.disabled = restartStep.disabled = viewConsole.disabled = false;
      restart.disabled = !restartStep.options.length;
    }
  }
  rerun.onclick = () => replay("rerun");
  modify.onclick = () => {
    loadArchivedAnalysis(record, {runId: runId.value || record.run_id, workdir: workdir.value});
    document.querySelector('[data-section="analysis"]')?.click();
  };
  resume.onclick = () => replay("resume");
  restart.onclick = () => replay("restart");
  viewConsole.onclick = () => showConsole(record.run_dir, record.run_id);
  actions.append(runId, workdir, rerun, modify, resume, viewConsole);
  detail.append(
    actions,
    restartPanel,
    element("p", "Restart from step keeps the same run: earlier steps are restored from cache, while the selected step and every following configured step are executed again. Resume uses every valid cached result. Reanalyse creates a new run without cache. Existing input/reference files and the Nextflow cache are required.", "muted"),
  );
  detail.append(element("h4", "Samples"));
  const columns = [...new Set(record.samples.flatMap(row => Object.keys(row)))];
  detail.append(table(columns, record.samples.map(row => columns.map(key => row[key]))));
  detail.append(element("h4", "Step progress"));
  const progress = element("div");
  progress.id = "history-step-progress";
  progress.append(progressTable(record));
  detail.append(progress);
  for (const [label, data] of [
    ["Pipeline and substeps", record.pipeline_config], ["Panel", record.panel_design],
    ["Run settings", record.run_config], ["Tools", record.tools_config],
    ["Sample sheet", record.samplesheet], ["Execution and logs", {command: record.command, exit_code: record.exit_code, error: record.error, logs: record.last_status?.content}],
  ]) {
    const section = element("details");
    section.append(element("summary", label), element("pre", JSON.stringify(data, null, 2), "analysis-console"));
    detail.append(section);
  }
  const download = element("button", "Download archived metadata", "ghost-button");
  download.onclick = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], {type: "application/json"}));
    const anchor = element("a");
    anchor.href = url;
    anchor.download = `${record.run_id}-${record.id}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  detail.append(download);
}

function statusSummary(record) {
  return `${record.status} · Started: ${date(record.created_at)} · Updated: ${date(record.updated_at)} · Finished: ${date(record.finished_at)}`;
}

function progressTable(record) {
  const matrix = record.last_status?.workflow_matrix || [];
  return matrix.length ? table(["Step", "Sample", "Role", "Status", "Started", "Completed", "Exit code"],
    matrix.flatMap(step => step.samples.map(sample => [step.step, sample.sample_name, sample.role, sample.status, sample.started, sample.completed, sample.exit_code])))
    : element("p", "No step status recorded yet.", "muted");
}

async function refreshProgress() {
  if (!selectedId) return;
  const id = selectedId;
  const record = await api(`/${id}`);
  if (selectedId !== id || busy) return;
  const summary = document.querySelector("#history-detail-status");
  const progress = document.querySelector("#history-step-progress");
  if (summary) summary.textContent = statusSummary(record);
  if (progress) progress.replaceChildren(progressTable(record));
}

export function initAnalysisHistory() {
  document.querySelector("#history-search").addEventListener("input", renderList);
  document.querySelector("#history-refresh").onclick = () => refresh().then(() => selectedId && select(selectedId)).catch(error => status(error.message));
  document.querySelector('[data-section="analysis-history"]').addEventListener("click", () => refresh().catch(error => status(error.message)));
  setInterval(() => {
    if (!document.querySelector("#analysis-history").classList.contains("active") || busy) return;
    // Keep editable reanalysis controls intact during background list updates.
    Promise.all([refresh(), refreshProgress()]).catch(error => status(error.message));
  }, 5000);
}
