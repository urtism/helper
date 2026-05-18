import {buildSampleSheet as buildSampleSheetApi, getPickerSelection, loadSampleSheet, previewSampleSheetFiles} from "../api.js?v=20260518-6";

const pickerStorageKey = "helper-next-selected-files";
const pickerBroadcastChannel = "helper-next-file-picker";
const samplesheetAccept = ".ss,.samplesheet,.json,application/json,text/plain";

const sampleSheet = {
  step: "prealignment",
  organization: "only cases",
  columns: ["sample_name", "fastq_R1", "fastq_R2", "fastq_I2"],
  droppedFiles: [],
  pathWarnings: [],
  loadedContent: "",
  activePickerId: "",
  pickerPoll: null,
  buildTimer: null,
  rows: [],
  organizationRows: [],
  selectedRowIndex: -1,
  json: {},
};

const organizationRoles = {
  "only cases": ["case"],
  "case-control": ["case", "control"],
  trio: ["case", "parent1", "parent2"],
};

const stepColumns = {
  prealignment: ["sample_name", "fastq_R1", "fastq_R2", "fastq_I2"],
  alignment: ["sample_name", "fastq_R1", "fastq_R2", "fastq_I2"],
  preprocessing: ["sample_name", "bam"],
  variantcalling: ["sample_name", "bam"],
  postprocessing: ["sample_name", "gatk_vcf", "freebayes_vcf", "varscan_vcf", "somatic_vcf"],
  annotation: ["sample_name", "merged_vcf", "variants_tsv"],
  postannotation: ["sample_name", "merged_vcf", "variants_tsv"],
};

const stepFileTypes = {
  prealignment: "FASTQ",
  alignment: "FASTQ",
  preprocessing: "BAM/SAM/CRAM",
  variantcalling: "BAM/SAM/CRAM",
  postprocessing: "VCF",
  annotation: "Merged VCF + TSV",
  postannotation: "Merged VCF + TSV",
};

const stepFileAccepts = {
  prealignment: ".fastq,.fastq.gz,.fq,.fq.gz",
  alignment: ".fastq,.fastq.gz,.fq,.fq.gz",
  preprocessing: ".bam,.sam,.cram",
  variantcalling: ".bam,.sam,.cram",
  postprocessing: ".vcf,.vcf.gz",
  annotation: ".vcf,.vcf.gz,.tsv,.tsv.gz",
  postannotation: ".vcf,.vcf.gz,.tsv,.tsv.gz",
};

export function initSampleSheet() {
  document.querySelector("#samplesheet-step").addEventListener("change", (event) => {
    sampleSheet.step = event.target.value;
    sampleSheet.columns = stepColumns[sampleSheet.step];
    updateExpectedFileControls();
    updateDataDropZoneText();
    if (sampleSheet.loadedContent) {
      loadSampleSheetContent(sampleSheet.loadedContent).catch(showSampleSheetError);
      return;
    }
    if (sampleSheet.droppedFiles.length) {
      previewFiles().catch(showSampleSheetError);
      return;
    }
    sampleSheet.rows = [];
    sampleSheet.organizationRows = [];
    sampleSheet.selectedRowIndex = -1;
    sampleSheet.json = {};
    renderSampleSheet();
  });

  document.querySelector("#samplesheet-organization").addEventListener("change", (event) => {
    sampleSheet.organization = event.target.value;
    sampleSheet.organizationRows = defaultOrganizationRows();
    renderSampleSheet();
    buildSampleSheet().catch(showSampleSheetError);
  });

  bindClick("#samplesheet-preview-files", previewFiles);
  bindChange("#samplesheet-open", openSampleSheetFile);
  bindChange("#samplesheet-data-open", openDataFiles);
  bindClick("#samplesheet-search-files", () => {
    openFilePickerPage();
  });
  bindClick("#samplesheet-search-existing", () => {
    const input = document.querySelector("#samplesheet-open");
    input.accept = samplesheetAccept;
    input.click();
  });
  bindClick("#samplesheet-add-row", addSampleRow);
  bindClick("#samplesheet-remove-row", removeSampleRow);
  bindClick("#samplesheet-build", () => buildSampleSheet().catch(showSampleSheetError));
  bindClick("#samplesheet-copy", copySampleSheetJson);
  bindClick("#samplesheet-download", downloadSampleSheetJson);
  initSampleSheetDropZone();
  initFilePickerMessages();

  updateExpectedFileControls();
  updateDataDropZoneText();
  renderSampleSheet();
  renderDroppedFiles();
}

function bindClick(selector, callback) {
  const element = document.querySelector(selector);
  if (element) element.addEventListener("click", callback);
}

function bindChange(selector, callback) {
  const element = document.querySelector(selector);
  if (element) element.addEventListener("change", callback);
}

function initSampleSheetDropZone() {
  const samplesheetDropzone = document.querySelector("#samplesheet-samplesheet-dropzone");

  preventFileDropNavigation();

  bindDropZone(samplesheetDropzone, async (files) => {
    const samplesheetFile = files.find((file) => /\.(ss|samplesheet|json)$/i.test(file.name));
    if (samplesheetFile) {
      await loadSampleSheetContent(await samplesheetFile.text());
      return;
    }
    renderWarnings(["Drop a .ss, .samplesheet, or .json file in the samplesheet area"]);
  });
}

function bindDropZone(dropzone, onDrop) {
  if (!dropzone) return;

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = "copy";
      dropzone.classList.add("active");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      dropzone.classList.remove("active");
    });
  });

  dropzone.addEventListener("drop", async (event) => {
    const files = await droppedFiles(event.dataTransfer);
    if (files.length) await onDrop(files);
    if (!files.length) renderWarnings(["No readable files found in the drop"]);
  });
}

function preventFileDropNavigation() {
  ["dragover", "drop"].forEach((eventName) => {
    window.addEventListener(eventName, (event) => {
      if (!hasFileDrag(event.dataTransfer)) return;
      event.preventDefault();
    });
  });
}

function hasFileDrag(dataTransfer) {
  if (!dataTransfer) return false;
  return Array.from(dataTransfer.types || []).includes("Files");
}

async function droppedFiles(dataTransfer) {
  const itemFiles = await filesFromItems(Array.from(dataTransfer.items || []));
  if (itemFiles.length) return itemFiles;
  return Array.from(dataTransfer.files || []);
}

async function filesFromItems(items) {
  const files = [];
  for (const item of items) {
    if (item.kind !== "file") continue;
    const entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
    if (entry && entry.isDirectory) {
      files.push(...(await filesFromDirectory(entry)));
      continue;
    }
    const file = item.getAsFile();
    if (file) files.push(file);
  }
  return files;
}

function filesFromDirectory(entry) {
  const reader = entry.createReader();
  return new Promise((resolve) => {
    reader.readEntries(async (entries) => {
      const nested = await Promise.all(
        entries.map((child) => {
          if (child.isDirectory) return filesFromDirectory(child);
          return fileFromEntry(child).then((file) => [file]);
        })
      );
      resolve(nested.flat().filter(Boolean));
    });
  });
}

function fileFromEntry(entry) {
  return new Promise((resolve) => {
    entry.file(resolve, () => resolve(null));
  });
}

function initFilePickerMessages() {
  window.addEventListener("message", (event) => {
    if (event.origin !== window.location.origin) return;
    const message = event.data || {};
    if (message.type !== "helper-next-files-selected") return;
    addPickerFiles(message.files || []).catch(showSampleSheetError);
  });

  window.addEventListener("storage", (event) => {
    if (event.key === pickerStorageKey) consumeStoredPickerFiles();
  });

  window.addEventListener("focus", consumeStoredPickerFiles);

  if ("BroadcastChannel" in window) {
    const channel = new BroadcastChannel(pickerBroadcastChannel);
    channel.addEventListener("message", (event) => {
      const message = event.data || {};
      if (message.type !== "helper-next-files-selected") return;
      addPickerFiles(message.files || []).catch(showSampleSheetError);
    });
  }

  window.setInterval(consumeStoredPickerFiles, 750);
}

function openFilePickerPage() {
  const pickerId = `picker-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  sampleSheet.activePickerId = pickerId;
  startPickerPolling(pickerId);
  const params = new URLSearchParams({step: sampleSheet.step, pickerId});
  window.open(`/static/file_picker.html?${params.toString()}`, "helper-next-file-picker");
}

function startPickerPolling(pickerId) {
  if (sampleSheet.pickerPoll) {
    window.clearInterval(sampleSheet.pickerPoll);
  }
  sampleSheet.pickerPoll = window.setInterval(() => {
    pollPickerSelection(pickerId).catch(showSampleSheetError);
  }, 700);
}

async function pollPickerSelection(pickerId) {
  if (!pickerId || pickerId !== sampleSheet.activePickerId) return;
  const data = await getPickerSelection(pickerId);
  if (!data.files || !data.files.length) return;
  window.clearInterval(sampleSheet.pickerPoll);
  sampleSheet.pickerPoll = null;
  sampleSheet.activePickerId = "";
  await addPickerFiles(data.files);
}

async function addPickerFiles(files) {
  if (!files.length) return;
  sampleSheet.pathWarnings = [];
  appendDroppedFiles(files);
  await previewFiles();
}

function consumeStoredPickerFiles() {
  const raw = localStorage.getItem(pickerStorageKey);
  if (!raw) return;
  localStorage.removeItem(pickerStorageKey);

  try {
    const message = JSON.parse(raw);
    addPickerFiles(message.files || []).catch(showSampleSheetError);
  } catch (error) {
    showSampleSheetError(error);
  }
}

async function openDataFiles(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;
  await loadDataFiles(files);
  event.target.value = "";
}

async function loadDataFiles(files) {
  const selected = fileDisplayPaths(files);
  sampleSheet.pathWarnings = selected.warnings;
  appendDroppedFiles(selected.paths);
  await previewFiles();
}

function fileDisplayPaths(files) {
  const warnings = [];
  const paths = files.map((file) => {
    const directPath = file.path || "";
    if (directPath) return directPath;

    const relativePath = file.webkitRelativePath || file.name;
    const directory = dataFilesDirectory();
    if (directory) return joinPath(directory, relativePath);

    warnings.push(`Browser did not expose the full path for ${relativePath}; using the filename only`);
    return relativePath;
  });
  return {paths, warnings};
}

function dataFilesDirectory() {
  const input = document.querySelector("#samplesheet-data-directory");
  return input ? input.value.trim() : "";
}

function joinPath(directory, fileName) {
  return `${directory.replace(/[\\/]+$/, "")}/${fileName.replace(/^[\\/]+/, "")}`;
}

function updateLoadedFileDirectory() {
  const directory = dataFilesDirectory();
  if (!directory || !sampleSheet.droppedFiles.length) return;

  sampleSheet.droppedFiles = uniqueFiles(
    sampleSheet.droppedFiles.map((path) => (isAbsolutePath(path) ? path : joinPath(directory, path)))
  );
  sampleSheet.pathWarnings = [];
  renderDroppedFiles();
  previewFiles().catch(showSampleSheetError);
}

function isAbsolutePath(path) {
  return path.startsWith("/") || /^[A-Za-z]:[\\/]/.test(path);
}

function updateDataDropZoneText() {
  document.querySelector("#samplesheet-data-dropzone").textContent = `${stepFileTypes[sampleSheet.step]} drag and drop disabled. Use Search files to keep full paths.`;
}

function updateExpectedFileControls() {
  document.querySelector("#samplesheet-file-type").textContent = stepFileTypes[sampleSheet.step];
  document.querySelector("#samplesheet-data-open").accept = stepFileAccepts[sampleSheet.step] || "";
  document.querySelector("#samplesheet-open").accept = samplesheetAccept;
}

async function previewFiles() {
  const files = uniqueFiles(sampleSheet.droppedFiles);
  sampleSheet.loadedContent = "";
  if (!files.length) {
    sampleSheet.rows = [];
    sampleSheet.organizationRows = [];
    sampleSheet.selectedRowIndex = -1;
    sampleSheet.json = {};
    renderWarnings([]);
    renderSampleSheet();
    return;
  }

  const data = await previewSampleSheetFiles({step: sampleSheet.step, files});

  sampleSheet.columns = data.columns;
  sampleSheet.rows = data.rows;
  sampleSheet.organizationRows = data.organization_rows;
  sampleSheet.selectedRowIndex = -1;
  sampleSheet.json = {};
  renderWarnings(sampleSheet.pathWarnings.concat(data.warnings));
  renderSampleSheet();
  await buildSampleSheet();
}

async function openSampleSheetFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  await loadSampleSheetContent(await file.text());
  event.target.value = "";
}

async function loadSampleSheetContent(content) {
  const data = await loadSampleSheet({content, step: sampleSheet.step});

  sampleSheet.loadedContent = content;
  sampleSheet.step = data.step;
  sampleSheet.organization = data.organization;
  sampleSheet.columns = stepColumns[sampleSheet.step];
  sampleSheet.rows = data.rows;
  sampleSheet.organizationRows = data.organization_rows;
  sampleSheet.selectedRowIndex = -1;
  sampleSheet.json = data.samplesheet;
  document.querySelector("#samplesheet-step").value = sampleSheet.step;
  document.querySelector("#samplesheet-organization").value = sampleSheet.organization;
  updateExpectedFileControls();
  updateDataDropZoneText();
  renderWarnings([]);
  renderSampleSheet();
  await buildSampleSheet();
}

async function buildSampleSheet() {
  const data = await buildSampleSheetApi({
    step: sampleSheet.step,
    organization: sampleSheet.organization,
    rows: sampleSheet.rows,
    organization_rows: sampleSheet.organizationRows,
  });
  sampleSheet.json = data.samplesheet;
  renderJson();
}

function scheduleBuildSampleSheet() {
  if (sampleSheet.buildTimer) {
    window.clearTimeout(sampleSheet.buildTimer);
  }
  sampleSheet.buildTimer = window.setTimeout(() => {
    sampleSheet.buildTimer = null;
    buildSampleSheet().catch(showSampleSheetError);
  }, 150);
}

function renderSampleSheet() {
  renderSampleRows();
  renderOrganizationRows();
  renderJson();
}

function renderSampleRows() {
  const head = document.querySelector("#samplesheet-head");
  const body = document.querySelector("#samplesheet-body");
  head.replaceChildren();
  body.replaceChildren();

  const tr = document.createElement("tr");
  for (const column of sampleSheet.columns) {
    const th = document.createElement("th");
    th.textContent = column;
    tr.appendChild(th);
  }
  head.appendChild(tr);

  if (!sampleSheet.rows.length) {
    const empty = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = sampleSheet.columns.length;
    td.textContent = "No rows yet";
    empty.appendChild(td);
    body.appendChild(empty);
    return;
  }

  sampleSheet.rows.forEach((row, rowIndex) => {
    const tr = document.createElement("tr");
    tr.classList.toggle("selected-row", rowIndex === sampleSheet.selectedRowIndex);
    tr.tabIndex = 0;
    tr.addEventListener("click", () => selectSampleRow(rowIndex));
    tr.addEventListener("focusin", () => selectSampleRow(rowIndex));
    for (const column of sampleSheet.columns) {
      const td = document.createElement("td");
      const input = document.createElement("input");
      input.value = row[column] || "";
      input.addEventListener("input", () => {
        sampleSheet.rows[rowIndex][column] = input.value;
        if (column === "sample_name") {
          sampleSheet.organizationRows = defaultOrganizationRows();
          renderOrganizationRows();
        }
        scheduleBuildSampleSheet();
      });
      td.appendChild(input);
      tr.appendChild(td);
    }
    body.appendChild(tr);
  });
}

function selectSampleRow(rowIndex) {
  if (rowIndex === sampleSheet.selectedRowIndex) return;
  sampleSheet.selectedRowIndex = rowIndex;
  document.querySelectorAll("#samplesheet-body tr").forEach((row, index) => {
    row.classList.toggle("selected-row", index === rowIndex);
  });
}

function renderOrganizationRows() {
  const head = document.querySelector("#samplesheet-organization-head");
  const body = document.querySelector("#samplesheet-organization-body");
  const roles = organizationRoles[sampleSheet.organization] || organizationRoles["only cases"];
  const columns = ["sample_id"].concat(roles);
  const sampleNames = sampleSheet.rows.map((row) => row.sample_name).filter(Boolean);

  if (!sampleSheet.organizationRows.length) {
    sampleSheet.organizationRows = defaultOrganizationRows();
  }

  head.replaceChildren();
  body.replaceChildren();

  const tr = document.createElement("tr");
  for (const column of columns) {
    const th = document.createElement("th");
    th.textContent = column;
    tr.appendChild(th);
  }
  head.appendChild(tr);

  if (!sampleSheet.organizationRows.length) {
    const empty = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = columns.length;
    td.textContent = "No samples to organize";
    empty.appendChild(td);
    body.appendChild(empty);
    return;
  }

  sampleSheet.organizationRows.forEach((row, rowIndex) => {
    const tr = document.createElement("tr");
    columns.forEach((column) => {
      const td = document.createElement("td");
      if (column === "sample_id") {
        const input = document.createElement("input");
        input.value = row.sample_id || "";
        input.addEventListener("input", () => {
          sampleSheet.organizationRows[rowIndex].sample_id = input.value;
          scheduleBuildSampleSheet();
        });
        td.appendChild(input);
      } else {
        const select = document.createElement("select");
        addOption(select, "");
        sampleNames.forEach((name) => addOption(select, name));
        select.value = row[column] || "";
        select.addEventListener("change", () => {
          sampleSheet.organizationRows[rowIndex][column] = select.value;
          scheduleBuildSampleSheet();
        });
        td.appendChild(select);
      }
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
}

function defaultOrganizationRows() {
  const names = sampleSheet.rows.map((row) => row.sample_name).filter(Boolean);
  if (sampleSheet.organization === "case-control") {
    const rows = [];
    for (let index = 0; index < names.length; index += 2) {
      rows.push({sample_id: names[index], case: names[index], control: names[index + 1] || ""});
    }
    return rows;
  }
  if (sampleSheet.organization === "trio") {
    const rows = [];
    for (let index = 0; index < names.length; index += 3) {
      rows.push({sample_id: names[index], case: names[index], parent1: names[index + 1] || "", parent2: names[index + 2] || ""});
    }
    return rows;
  }
  return names.map((name) => ({sample_id: name, case: name}));
}

function addSampleRow() {
  const row = {};
  sampleSheet.columns.forEach((column) => {
    row[column] = "";
  });
  sampleSheet.rows.push(row);
  sampleSheet.selectedRowIndex = sampleSheet.rows.length - 1;
  sampleSheet.organizationRows = defaultOrganizationRows();
  renderSampleSheet();
  scheduleBuildSampleSheet();
}

function removeSampleRow() {
  if (sampleSheet.selectedRowIndex < 0 || sampleSheet.selectedRowIndex >= sampleSheet.rows.length) {
    renderWarnings(["Select a row before removing it"]);
    return;
  }
  sampleSheet.rows.splice(sampleSheet.selectedRowIndex, 1);
  sampleSheet.selectedRowIndex = Math.min(sampleSheet.selectedRowIndex, sampleSheet.rows.length - 1);
  sampleSheet.organizationRows = defaultOrganizationRows();
  renderSampleSheet();
  scheduleBuildSampleSheet();
}

function appendDroppedFiles(paths) {
  sampleSheet.droppedFiles = uniqueFiles(sampleSheet.droppedFiles.concat(paths));
  renderDroppedFiles();
}

function renderDroppedFiles() {
  const list = document.querySelector("#samplesheet-file-list");
  list.replaceChildren();

  if (!sampleSheet.droppedFiles.length) {
    const empty = document.createElement("li");
    empty.textContent = "No files loaded";
    list.appendChild(empty);
    return;
  }

  sampleSheet.droppedFiles.forEach((path) => {
    const item = document.createElement("li");
    item.textContent = path;
    list.appendChild(item);
  });
}

function uniqueFiles(files) {
  return Array.from(new Set(files.map((file) => file.trim()).filter(Boolean)));
}

function renderJson() {
  document.querySelector("#samplesheet-json").textContent = JSON.stringify(sampleSheet.json || {}, null, 2);
}

function renderWarnings(warnings) {
  document.querySelector("#samplesheet-warnings").textContent = (warnings || []).join("\n");
}

function showSampleSheetError(error) {
  renderWarnings([error.message]);
}

function addOption(select, value) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = value || "-";
  select.appendChild(option);
}

async function copySampleSheetJson() {
  await buildSampleSheet();
  await navigator.clipboard.writeText(JSON.stringify(sampleSheet.json, null, 2));
}

async function downloadSampleSheetJson() {
  await buildSampleSheet();
  const blob = new Blob([JSON.stringify(sampleSheet.json, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "samplesheet.ss";
  link.click();
  URL.revokeObjectURL(url);
}
