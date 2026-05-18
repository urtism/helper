async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function getProject() {
  return requestJson("/api/project");
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
