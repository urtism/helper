import {browseSampleSheetFiles, savePickerSelection} from "../api.js?v=20260518";

const pickerStorageKey = "helper-next-selected-files";
const pickerBroadcastChannel = "helper-next-file-picker";
const params = new URLSearchParams(window.location.search);
const step = params.get("step") || "prealignment";
const pickerId = params.get("pickerId") || "";
const selected = new Set();

const stepLabels = {
  prealignment: "FASTQ files",
  alignment: "FASTQ files",
  preprocessing: "BAM, SAM, or CRAM files",
  variantcalling: "BAM, SAM, or CRAM files",
  postprocessing: "VCF files",
  annotation: "VCF and TSV files",
  postannotation: "VCF and TSV files",
};

let currentPath = "";
let parentPath = "";
let currentDirectories = [];
let currentFiles = [];

document.querySelector("#picker-step-label").textContent = stepLabels[step] || "Compatible files";
document.querySelector("#picker-close").addEventListener("click", () => window.close());
document.querySelector("#file-picker-add").addEventListener("click", () => useSelectedFiles().catch(showError));
document.querySelector("#file-picker-select-all").addEventListener("click", selectAllCurrentFiles);
document.querySelector("#file-picker-clear").addEventListener("click", clearSelection);
document.querySelector("#file-picker-up").addEventListener("click", () => {
  if (parentPath) loadDirectory(parentPath).catch(showError);
});
document.querySelector("#file-picker-go").addEventListener("click", () => {
  loadDirectory(document.querySelector("#file-picker-path").value).catch(showError);
});
document.querySelector("#file-picker-path").addEventListener("keydown", (event) => {
  if (event.key === "Enter") loadDirectory(event.target.value).catch(showError);
});

loadDirectory("").catch(showError);

async function loadDirectory(path) {
  const data = await browseSampleSheetFiles(step, path);
  currentPath = data.path;
  parentPath = data.parent || "";
  document.querySelector("#file-picker-path").value = currentPath;
  document.querySelector("#file-picker-up").disabled = !parentPath;
  document.querySelector("#file-picker-warnings").textContent = (data.warnings || []).join("\n");
  currentDirectories = data.directories || [];
  currentFiles = data.files || [];
  renderRoots(data.roots || []);
  if (data.locations) {
    renderLocations(data.locations);
    return;
  }
  renderList(currentDirectories, currentFiles);
}

function renderRoots(roots) {
  const node = document.querySelector("#file-picker-roots");
  node.replaceChildren();

  roots.forEach((root) => {
    const button = document.createElement("button");
    button.className = "picker-root-button";
    button.type = "button";
    button.textContent = root.label;
    button.classList.toggle("active", root.path === currentPath);
    button.addEventListener("click", () => loadDirectory(root.path).catch(showError));
    node.appendChild(button);
  });
}

function renderLocations(locations) {
  const list = document.querySelector("#file-picker-list");
  list.replaceChildren();
  currentDirectories = [];
  currentFiles = [];

  if (!locations.length) {
    const empty = document.createElement("div");
    empty.className = "file-picker-empty";
    empty.textContent = "No other locations found";
    list.appendChild(empty);
    updateCount();
    return;
  }

  let activeSection = "";
  locations.forEach((location) => {
    if (location.section !== activeSection) {
      activeSection = location.section;
      const heading = document.createElement("div");
      heading.className = "location-section-heading";
      heading.textContent = activeSection;
      list.appendChild(heading);
    }

    const row = document.createElement("button");
    row.className = "location-row";
    row.type = "button";
    row.addEventListener("click", () => loadDirectory(location.path).catch(showError));

    const icon = document.createElement("span");
    icon.className = "location-icon";
    icon.textContent = location.section === "Networks" ? "NET" : "DISK";

    const name = document.createElement("span");
    name.className = "location-name";
    name.textContent = location.name;

    const detail = document.createElement("span");
    detail.className = "location-detail";
    detail.textContent = location.detail || "";

    const device = document.createElement("span");
    device.className = "location-device";
    device.textContent = location.device || location.path;

    row.appendChild(icon);
    row.appendChild(name);
    row.appendChild(detail);
    row.appendChild(device);
    list.appendChild(row);
  });

  updateCount();
}

function renderList(directories, files) {
  const list = document.querySelector("#file-picker-list");
  list.replaceChildren();

  if (!directories.length && !files.length) {
    const empty = document.createElement("div");
    empty.className = "file-picker-empty";
    empty.textContent = "No compatible files found in this directory";
    list.appendChild(empty);
    updateCount();
    return;
  }

  directories.forEach((directory) => {
    const row = document.createElement("button");
    row.className = "location-row directory-location-row";
    row.type = "button";
    row.addEventListener("click", () => loadDirectory(directory.path).catch(showError));

    const icon = document.createElement("span");
    icon.className = "location-icon";
    icon.textContent = "DIR";

    const name = document.createElement("span");
    name.className = "location-name";
    name.textContent = directory.name;

    const detail = document.createElement("span");
    detail.className = "location-detail";
    detail.textContent = "Folder";

    const path = document.createElement("span");
    path.className = "location-device";
    path.textContent = directory.path;

    row.appendChild(icon);
    row.appendChild(name);
    row.appendChild(detail);
    row.appendChild(path);
    list.appendChild(row);
  });

  files.forEach((file) => {
    const row = document.createElement("div");
    row.className = "location-row file-location-row";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selected.has(file.path);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        selected.add(file.path);
      } else {
        selected.delete(file.path);
      }
      updateCount();
    });

    const icon = document.createElement("span");
    icon.className = "location-icon";
    icon.textContent = "FILE";

    const name = document.createElement("span");
    name.className = "location-name";
    name.textContent = file.name;

    row.addEventListener("click", (event) => {
      if (event.target === checkbox) return;
      checkbox.checked = !checkbox.checked;
      checkbox.dispatchEvent(new Event("change"));
    });

    row.appendChild(checkbox);
    row.appendChild(icon);
    row.appendChild(name);
    row.appendChild(fileDetail(file.size));
    row.appendChild(filePath(file.path));
    list.appendChild(row);
  });

  updateCount();
}

function fileDetail(size) {
  const detail = document.createElement("span");
  detail.className = "location-detail";
  detail.textContent = formatSize(size);
  return detail;
}

function filePath(path) {
  const node = document.createElement("span");
  node.className = "location-device";
  node.textContent = path;
  return node;
}

function formatSize(size) {
  if (!Number.isFinite(size)) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = size;
  for (const unit of units) {
    if (value < 1024 || unit === units[units.length - 1]) {
      return `${value.toFixed(value < 10 && unit !== "B" ? 1 : 0)} ${unit}`;
    }
    value /= 1024;
  }
  return "";
}

async function useSelectedFiles() {
  const files = Array.from(selected);
  if (!files.length) return;
  const message = {type: "helper-next-files-selected", files, createdAt: Date.now()};
  if (pickerId) {
    await savePickerSelection(pickerId, files);
  }
  localStorage.setItem(pickerStorageKey, JSON.stringify(message));
  if ("BroadcastChannel" in window) {
    const channel = new BroadcastChannel(pickerBroadcastChannel);
    channel.postMessage(message);
    channel.close();
  }
  if (window.opener) {
    window.opener.postMessage(message, window.location.origin);
  }
  document.querySelector("#file-picker-warnings").textContent = `${files.length} file${files.length === 1 ? "" : "s"} sent to Sample Sheet`;
  window.setTimeout(() => window.close(), 250);
}

function selectAllCurrentFiles() {
  currentFiles.forEach((file) => selected.add(file.path));
  renderList(currentDirectories, currentFiles);
}

function clearSelection() {
  selected.clear();
  renderList(currentDirectories, currentFiles);
}

function updateCount() {
  const count = selected.size;
  document.querySelector("#file-picker-count").textContent = `${count} file${count === 1 ? "" : "s"} selected`;
}

function showError(error) {
  document.querySelector("#file-picker-warnings").textContent = error.message;
}
