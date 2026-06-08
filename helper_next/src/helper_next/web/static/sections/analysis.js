import {getAnalysisRunStatus, startFakeAnalysis, startRealAnalysis} from "../api.js?v=20260518-11";

const analysisState = {
  samplesheetContent: "",
  samplesheetName: "",
  pollTimer: null,
  activeRunDir: "",
};

export function initAnalysis() {
  const runId = document.querySelector("#analysis-run-id");
  if (runId && !runId.value) {
    runId.value = defaultRunId();
  }

  const workdir = document.querySelector("#analysis-workdir");
  if (workdir && !workdir.value) {
    workdir.value = "/tmp/helper_next_analysis";
  }

  bindChange("#analysis-samplesheet-file", loadSamplesheetFile);
  bindClickAll(".analysis-start-fake", startFakeRun);
  bindClick("#analysis-console-refresh", refreshConsole);
  renderAnalysisQueue([{status: "idle", message: "No analysis queued"}]);
}

function bindClick(selector, callback) {
  const element = document.querySelector(selector);
  if (element) element.addEventListener("click", callback);
}

function bindClickAll(selector, callback) {
  document.querySelectorAll(selector).forEach((element) => {
    element.addEventListener("click", callback);
  });
}

function bindChange(selector, callback) {
  const element = document.querySelector(selector);
  if (element) element.addEventListener("change", callback);
}

function defaultRunId() {
  const now = new Date();
  const date = now.toISOString().slice(0, 10).replaceAll("-", "");
  return `${date}_fake_alignment`;
}

async function loadSamplesheetFile(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  analysisState.samplesheetContent = await file.text();
  analysisState.samplesheetName = file.name;
  document.querySelector("#analysis-samplesheet-name").textContent = file.name;
  renderAnalysisQueue([{status: "loaded", message: file.name}]);
  renderConsoleText("Samplesheet loaded: " + file.name);
}

async function startFakeRun() {
  const status = document.querySelector("#analysis-status");
  status.textContent = "";
  stopConsolePolling();

  if (!analysisState.samplesheetContent) {
    status.textContent = "Load a samplesheet first";
    return;
  }

  const payload = {
    run_id: valueOf("#analysis-run-id"),
    workdir: valueOf("#analysis-workdir"),
    aligner: valueOf("#analysis-aligner"),
    keep_intermediates: checkedOf("#analysis-keep-intermediates"),
    execution_profile: valueOf("#analysis-execution-profile") || "local",
    queue: valueOf("#analysis-queue"),
    samplesheet_content: analysisState.samplesheetContent,
  };

  const workflow = valueOf("#analysis-workflow");
  renderAnalysisQueue([{status: "running", message: `${payload.run_id} (${workflow})`}]);
  setConsoleState("Submitting");
  renderConsoleText(`Submitting ${payload.run_id} (${workflow})...`);
  try {
    const result = workflow === "real_alignment" ? await startRealAnalysis(payload) : await startFakeAnalysis(payload);
    renderResult(result);
    startConsolePolling(result.run_dir, result.status === "submitted");
  } catch (error) {
    status.textContent = error.message;
    renderAnalysisQueue([{status: "error", message: error.message}]);
    setConsoleState("Error");
    renderConsoleText(error.message);
  }
}

function valueOf(selector) {
  const element = document.querySelector(selector);
  return element ? element.value.trim() : "";
}

function checkedOf(selector) {
  const element = document.querySelector(selector);
  return element ? element.checked : false;
}

function renderResult(result) {
  document.querySelector("#analysis-status").textContent = result.message;
  const queueItems = [
    {status: result.status, message: result.run_id},
    {status: "manifest", message: result.manifest},
    {status: "run config", message: result.run_config},
  ];
  if (result.pid) queueItems.push({status: "pid", message: String(result.pid)});
  if (result.execution_profile) queueItems.push({status: "profile", message: result.execution_profile});
  if (result.queue) queueItems.push({status: "queue", message: result.queue});
  queueItems.push({status: "intermediates", message: result.keep_intermediates ? "kept" : "discarded"});
  if (result.work_dir) queueItems.push({status: "work dir", message: result.work_dir});
  if (result.nextflow_log) queueItems.push({status: "nextflow log", message: result.nextflow_log});
  if (result.nextflow_trace) queueItems.push({status: "nextflow trace", message: result.nextflow_trace});
  if (result.workflow_plan) queueItems.push({status: "workflow plan", message: result.workflow_plan});
  if (result.pid_file) queueItems.push({status: "pid file", message: result.pid_file});
  if (result.command_file) queueItems.push({status: "command file", message: result.command_file});
  if (result.command) queueItems.push({status: "command", message: result.command});
  if (result.logs && result.logs.step) queueItems.push({status: "step log", message: result.logs.step});
  renderAnalysisQueue(queueItems);
  renderOutputList(result.outputs || [], result.logs ? result.logs.samples || [] : []);
}

function startConsolePolling(runDir, keepPolling) {
  if (!runDir) return;
  analysisState.activeRunDir = runDir;
  refreshConsole();
  if (!keepPolling) return;
  stopConsolePolling();
  analysisState.pollTimer = window.setInterval(refreshConsole, 2000);
}

function stopConsolePolling() {
  if (analysisState.pollTimer) {
    window.clearInterval(analysisState.pollTimer);
    analysisState.pollTimer = null;
  }
}

async function refreshConsole() {
  if (!analysisState.activeRunDir) {
    renderConsoleText("No run selected");
    setConsoleState("Idle");
    return;
  }
  try {
    const status = await getAnalysisRunStatus(analysisState.activeRunDir);
    renderConsoleStatus(status);
    if (!status.running) stopConsolePolling();
  } catch (error) {
    setConsoleState("Error");
    renderConsoleText(error.message);
    stopConsolePolling();
  }
}

function renderConsoleStatus(status) {
  setConsoleState(status.status);
  const content = status.content || {};
  const files = status.files || {};
  const parts = [
    `run_dir=${status.run_dir}`,
    `status=${status.status}`,
    status.pid ? `pid=${status.pid}` : "pid=",
    "",
    sectionText("run matrix", "", content.workflow_matrix),
    sectionText("workflow.plan.tsv", files.workflow_plan, content.workflow_plan),
    sectionText("nextflow.trace.tsv", files.nextflow_trace, content.nextflow_trace),
    sectionText("alignment.step.log", files.alignment_step_log, content.alignment_step_log),
    sectionText("preprocessing.step.log", files.preprocessing_step_log, content.preprocessing_step_log),
    sectionText("nextflow.log", files.nextflow_log, content.nextflow_log),
  ];
  renderConsoleText(parts.join("\n"));
}

function sectionText(title, path, text) {
  const body = text && text.trim() ? text.trimEnd() : "[waiting]";
  return `### ${title}\n${path || ""}\n${body}\n`;
}

function setConsoleState(label) {
  const element = document.querySelector("#analysis-console-state");
  if (element) element.textContent = label;
}

function renderConsoleText(text) {
  const consoleElement = document.querySelector("#analysis-console");
  if (!consoleElement) return;
  consoleElement.textContent = text || "";
  consoleElement.scrollTop = consoleElement.scrollHeight;
}

function renderAnalysisQueue(items) {
  const queue = document.querySelector("#analysis-queue");
  queue.replaceChildren();
  items.forEach((item) => {
    const li = document.createElement("li");
    const status = document.createElement("strong");
    status.textContent = item.status;
    const message = document.createElement("span");
    message.textContent = ` ${item.message}`;
    li.appendChild(status);
    li.appendChild(message);
    queue.appendChild(li);
  });
}

function renderOutputList(outputs, logs) {
  const list = document.querySelector("#analysis-output-list");
  list.replaceChildren();

  const rows = [];
  outputs.forEach((output) => {
    rows.push(`${output.sample_name}: ${output.bam}`);
    rows.push(`${output.sample_name}: ${output.bai}`);
    if (output.sam) rows.push(`${output.sample_name}: ${output.sam}`);
    if (output.unsorted_bam) rows.push(`${output.sample_name}: ${output.unsorted_bam}`);
  });
  logs.forEach((log) => rows.push(log));

  if (!rows.length) {
    const empty = document.createElement("li");
    empty.textContent = "No outputs";
    list.appendChild(empty);
    return;
  }

  rows.forEach((row) => {
    const li = document.createElement("li");
    li.textContent = row;
    list.appendChild(li);
  });
}
