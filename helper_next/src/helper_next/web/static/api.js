async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      if (Array.isArray(payload.detail)) {
        detail = payload.detail.join("\n");
      } else if (payload.detail) {
        detail = String(payload.detail);
      }
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || `Request failed: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function getProject() {
  return requestJson("/api/project");
}

export async function getPipelines() {
  return requestJson("/api/pipelines");
}

export async function getPipeline(name) {
  return requestJson(`/api/pipelines/${encodeURIComponent(name)}`);
}

export async function newPipelineDraft(template = null) {
  return requestJson("/api/pipelines/new/draft", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({template}),
  });
}

export async function validatePipeline(config) {
  return requestJson("/api/pipelines/validate/draft", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({config}),
  });
}

export async function savePipeline(name, config, overwrite) {
  return requestJson("/api/pipelines", {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name, config, overwrite}),
  });
}

export async function deletePipeline(name) {
  return requestJson(`/api/pipelines/${encodeURIComponent(name)}`, {method: "DELETE"});
}

export async function getTools(filename = "tools_cfg/tools.cfg") {
  const params = new URLSearchParams({filename});
  return requestJson(`/api/tools?${params.toString()}`);
}

export async function validateTools(config) {
  return requestJson("/api/tools/validate/draft", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({config}),
  });
}

export async function saveTools(filename, config, revision) {
  return requestJson("/api/tools", {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({filename, config, revision}),
  });
}

export async function testTool(resourceType, name, config) {
  return requestJson("/api/tools/test", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({resource_type: resourceType, name, config}),
  });
}

export async function getAnalysisPipeline(path) {
  const params = new URLSearchParams({path});
  return requestJson(`/api/analysis/pipeline-config?${params.toString()}`);
}

export async function previewSampleSheetFiles(payload) {
  return requestJson("/api/samplesheet/preview-files", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
}

export async function browseSampleSheetFiles(step, path = "") {
  const params = new URLSearchParams({step});
  if (path) params.set("path", path);
  return requestJson(`/api/samplesheet/browse-files?${params.toString()}`);
}

export async function savePickerSelection(pickerId, files) {
  return requestJson(`/api/samplesheet/picker-selection/${encodeURIComponent(pickerId)}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({files}),
  });
}

export async function getPickerSelection(pickerId) {
  return requestJson(`/api/samplesheet/picker-selection/${encodeURIComponent(pickerId)}`);
}

export async function loadSampleSheet(payload) {
  return requestJson("/api/samplesheet/load", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
}

export async function buildSampleSheet(payload) {
  return requestJson("/api/samplesheet/build", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
}

export async function startRealAnalysis(payload) {
  return requestJson("/api/analysis/real-run", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
}

export async function validateAnalysisRun(payload) {
  return requestJson("/api/analysis/validate-run", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
}

export async function getAnalysisRunStatus(runDir) {
  const params = new URLSearchParams({run_dir: runDir});
  return requestJson(`/api/analysis/run-status?${params.toString()}`);
}

export async function stopAnalysisRun(runDir) {
  return requestJson("/api/analysis/stop-run", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({run_dir: runDir}),
  });
}
