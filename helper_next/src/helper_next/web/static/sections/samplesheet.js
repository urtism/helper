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
  activeAnalysisGroup: null,
  json: {},
};

const analysisTypes = [
  ["only cases", "Only case"],
  ["family", "Family"],
  ["case-control", "Case-control"],
  ["tumor-normal", "Tumor-normal"],
];

const familyRelationships = ["proband", "father", "mother", "sibling", "other"];
const caseControlRelationships = ["case", "control"];
const tumorNormalRelationships = ["tumor", "normal"];
const sexValues = ["unknown", "female", "male"];
const affectedValues = ["unknown", "affected", "unaffected"];
const controlRelationshipValues = ["unrelated", "father", "mother", "sibling", "other"];
const specimenTypes = ["unknown", "tumor tissue", "blood", "bone marrow", "saliva", "other"];

const stepColumns = {
  prealignment: ["sample_name", "fastq_R1", "fastq_R2", "fastq_I2"],
  alignment: ["sample_name", "fastq_R1", "fastq_R2", "fastq_I2"],
  preprocessing: ["sample_name", "bam"],
  variantcalling: ["sample_name", "bam"],
  cnvcalling: ["sample_name", "bam"],
  postprocessing: ["sample_name", "gatk_vcf", "freebayes_vcf", "varscan_vcf", "somatic_vcf"],
  annotation: ["sample_name", "merged_vcf", "variants_tsv"],
  postannotation: ["sample_name", "merged_vcf", "variants_tsv"],
};

const stepFileTypes = {
  prealignment: "FASTQ",
  alignment: "FASTQ",
  preprocessing: "BAM/SAM/CRAM",
  variantcalling: "BAM/SAM/CRAM",
  cnvcalling: "BAM/SAM/CRAM",
  postprocessing: "VCF",
  annotation: "Merged VCF + TSV",
  postannotation: "Merged VCF + TSV",
};

const stepFileAccepts = {
  prealignment: ".fastq,.fastq.gz,.fq,.fq.gz",
  alignment: ".fastq,.fastq.gz,.fq,.fq.gz",
  preprocessing: ".bam,.sam,.cram",
  variantcalling: ".bam,.sam,.cram",
  cnvcalling: ".bam,.sam,.cram",
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
  bindClick("#samplesheet-analysis-drawer-close", closeAnalysisDrawer);
  bindClick("#samplesheet-analysis-drawer-done", closeAnalysisDrawer);
  bindClick("#samplesheet-analysis-drawer-backdrop", closeAnalysisDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sampleSheet.activeAnalysisGroup) closeAnalysisDrawer();
  });
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
  sampleSheet.organizationRows = analysisRowsFromLegacy(data.organization_rows, "only cases");
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
  sampleSheet.organizationRows = analysisRowsFromLegacy(data.organization_rows, data.organization);
  sampleSheet.selectedRowIndex = -1;
  sampleSheet.json = data.samplesheet;
  document.querySelector("#samplesheet-step").value = sampleSheet.step;
  updateExpectedFileControls();
  updateDataDropZoneText();
  renderWarnings([]);
  renderSampleSheet();
  await buildSampleSheet();
}

async function buildSampleSheet() {
  sampleSheet.organization = "mixed";
  const data = await buildSampleSheetApi({
    step: sampleSheet.step,
    organization: sampleSheet.organization,
    rows: sampleSheet.rows,
    organization_rows: sampleSheet.organizationRows,
  });
  sampleSheet.json = data.samplesheet;
  renderJson();
  renderOrganizationStatus();
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
  renderOrganizationStatus();
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
  const columns = [
    ["sample_name", "Sample"],
    ["analysis_type", "Analysis"],
    ["analysis_id", "Family / pair"],
    ["relationship", "Role"],
    ["summary", "Details"],
    ["status", "Status"],
    ["configure", ""],
  ];

  if (!sampleSheet.organizationRows.length) {
    sampleSheet.organizationRows = defaultOrganizationRows();
  }

  head.replaceChildren();
  body.replaceChildren();

  const tr = document.createElement("tr");
  for (const [, label] of columns) {
    const th = document.createElement("th");
    th.textContent = label;
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
    tr.dataset.analysisType = row.analysis_type || "only cases";
    columns.forEach(([column]) => {
      const td = document.createElement("td");
      if (column === "sample_name") {
        const value = document.createElement("strong");
        value.textContent = row.sample_name || "";
        td.appendChild(value);
      } else if (column === "analysis_type") {
        const select = makeSelect(analysisTypes, row.analysis_type || "only cases");
        select.setAttribute("aria-label", `Analysis type for ${row.sample_name}`);
        select.addEventListener("change", () => {
          changeAnalysisType(rowIndex, select.value);
        });
        td.appendChild(select);
      } else if (column === "analysis_id" && row.analysis_type !== "only cases") {
        const existingIds = analysisIdOptions(row, rowIndex);
        const currentIdIsExisting = existingIds.some(([value]) => value === row.analysis_id);
        const useExistingIdSelect = existingIds.length > 0 && (!row.analysis_id || currentIdIsExisting);
        const control = document.createElement("div");
        control.className = "analysis-id-control";

        if (useExistingIdSelect) {
          const select = document.createElement("select");
          const newIdValue = "__create_new_analysis_id__";
          const groupLabel = row.analysis_type === "family" ? "family" : "pair";
          select.setAttribute("aria-label", `Select ${groupLabel} for ${row.sample_name}`);
          addOption(select, "", `Select ${groupLabel}…`);
          existingIds.forEach(([value, label]) => addOption(select, value, label));
          addOption(select, newIdValue, `Create new ${groupLabel}…`);
          select.value = currentIdIsExisting ? row.analysis_id : "";
          select.addEventListener("change", () => {
            if (!select.value) return;
            if (select.value === newIdValue) {
              sampleSheet.organizationRows[rowIndex].analysis_id = row.sample_name;
              renderOrganizationRows();
              scheduleBuildSampleSheet();
              return;
            }
            sampleSheet.organizationRows[rowIndex].analysis_id = select.value;
            normalizeAnalysisGroup(rowIndex);
            renderOrganizationRows();
            scheduleBuildSampleSheet();
          });
          control.appendChild(select);
        } else {
          const input = document.createElement("input");
          input.value = row.analysis_id || row.sample_name;
          input.placeholder = row.analysis_type === "family" ? "Family ID" : "Pair ID";
          input.addEventListener("input", () => {
            sampleSheet.organizationRows[rowIndex].analysis_id = input.value;
            scheduleBuildSampleSheet();
          });
          input.addEventListener("change", () => {
            normalizeAnalysisGroup(rowIndex);
            renderOrganizationRows();
            scheduleBuildSampleSheet();
          });
          control.appendChild(input);
        }

        td.appendChild(control);
      } else if (column === "relationship") {
        td.textContent = row.analysis_type === "only cases" ? "Single" : displayValue(row.relationship);
      } else if (column === "summary") {
        td.textContent = analysisRowSummary(row);
        td.className = "analysis-summary-cell";
      } else if (column === "status") {
        const status = analysisGroupStatus(row.analysis_type, row.analysis_id);
        const badge = document.createElement("span");
        badge.className = `analysis-status-badge ${status.complete ? "complete" : "incomplete"}`;
        badge.textContent = status.label;
        td.appendChild(badge);
      } else if (column === "configure" && row.analysis_type !== "only cases") {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "ghost-button compact-button";
        button.textContent = "Configure";
        button.addEventListener("click", () => openAnalysisDrawer(row.analysis_type, row.analysis_id));
        td.appendChild(button);
      } else {
        td.className = "unavailable-cell";
        const unavailable = document.createElement("span");
        unavailable.className = "unavailable-field";
        unavailable.textContent = "—";
        td.appendChild(unavailable);
      }
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });

}

function displayValue(value) {
  if (!value) return "—";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function analysisRowSummary(row) {
  if (row.analysis_type === "only cases") return "Independent analysis";
  if (row.analysis_type === "family") {
    const details = [displayValue(row.sex), displayValue(row.affected)];
    if (row.father || row.mother) details.push("parents linked");
    return details.join(" · ");
  }
  if (row.analysis_type === "case-control") {
    const details = [displayValue(row.sex), displayValue(row.affected)];
    if (row.relationship === "control") details.push(displayValue(row.control_relationship));
    return details.join(" · ");
  }
  const details = [row.individual_id || row.sample_name, displayValue(row.specimen_type)];
  if (row.relationship === "tumor" && row.tumor_purity) details.push(`${row.tumor_purity}% purity`);
  return details.join(" · ");
}

function analysisGroupStatus(analysisType, analysisId) {
  if (analysisType === "only cases") return {complete: true, label: "Ready"};
  const members = analysisGroupMembers(analysisType, analysisId);
  if (analysisType === "family") {
    const hasProband = members.filter((row) => row.relationship === "proband").length === 1;
    const detailsComplete = members.every((row) => row.sex !== "unknown" && row.affected !== "unknown");
    return {complete: hasProband && detailsComplete, label: hasProband && detailsComplete ? "Ready" : "Needs details"};
  }
  if (analysisType === "case-control") {
    const rolesComplete = members.filter((row) => row.relationship === "case").length === 1
      && members.filter((row) => row.relationship === "control").length === 1;
    const detailsComplete = members.every((row) => row.sex !== "unknown" && row.affected !== "unknown");
    return {complete: rolesComplete && detailsComplete, label: rolesComplete && detailsComplete ? "Ready" : "Needs details"};
  }
  const rolesComplete = members.filter((row) => row.relationship === "tumor").length === 1
    && members.filter((row) => row.relationship === "normal").length === 1;
  const detailsComplete = members.every(
    (row) => row.individual_id && row.sex !== "unknown" && row.specimen_type && row.specimen_type !== "unknown"
  );
  const sameIndividual = new Set(members.map((row) => row.individual_id).filter(Boolean)).size === 1;
  return {complete: rolesComplete && detailsComplete && sameIndividual, label: rolesComplete && detailsComplete && sameIndividual ? "Ready" : "Needs details"};
}

function analysisGroupMembers(analysisType, analysisId) {
  return sampleSheet.organizationRows.filter(
    (row) => row.analysis_type === analysisType && row.analysis_id === analysisId
  );
}

function openAnalysisDrawer(analysisType, analysisId) {
  sampleSheet.activeAnalysisGroup = {analysisType, analysisId};
  const drawer = document.querySelector("#samplesheet-analysis-drawer");
  const backdrop = document.querySelector("#samplesheet-analysis-drawer-backdrop");
  drawer.hidden = false;
  backdrop.hidden = false;
  drawer.setAttribute("aria-hidden", "false");
  document.body.classList.add("analysis-drawer-open");
  renderAnalysisDrawer();
}

function closeAnalysisDrawer() {
  sampleSheet.activeAnalysisGroup = null;
  const drawer = document.querySelector("#samplesheet-analysis-drawer");
  const backdrop = document.querySelector("#samplesheet-analysis-drawer-backdrop");
  drawer.hidden = true;
  backdrop.hidden = true;
  drawer.setAttribute("aria-hidden", "true");
  document.body.classList.remove("analysis-drawer-open");
}

function renderAnalysisDrawer() {
  const active = sampleSheet.activeAnalysisGroup;
  if (!active) return;
  const members = analysisGroupMembers(active.analysisType, active.analysisId);
  const body = document.querySelector("#samplesheet-analysis-drawer-body");
  const kind = document.querySelector("#samplesheet-analysis-drawer-kind");
  const title = document.querySelector("#samplesheet-analysis-drawer-title");
  body.replaceChildren();
  kind.textContent = displayValue(active.analysisType);
  title.textContent = active.analysisId;

  const intro = document.createElement("p");
  intro.className = "muted drawer-intro";
  intro.textContent = drawerIntroduction(active.analysisType);
  body.appendChild(intro);

  if (active.analysisType === "tumor-normal") {
    const individualId = members.find((row) => row.individual_id)?.individual_id || active.analysisId;
    const advanced = document.createElement("details");
    advanced.className = "drawer-advanced";
    const summary = document.createElement("summary");
    summary.textContent = "Advanced identifiers";
    advanced.appendChild(summary);
    const groupFields = document.createElement("div");
    groupFields.className = "drawer-group-fields";
    appendInputField(groupFields, "Individual ID", individualId, (value) => {
      members.forEach((member) => {
        member.individual_id = value;
      });
      refreshAnalysisConfiguration();
    });
    advanced.appendChild(groupFields);
    body.appendChild(advanced);
  }

  const memberList = document.createElement("div");
  memberList.className = "analysis-member-list";
  members.forEach((member) => memberList.appendChild(renderAnalysisMember(member)));
  body.appendChild(memberList);
  updateDrawerStatus();
}

function drawerIntroduction(analysisType) {
  if (analysisType === "family") return "Configure relationships to the proband. Parent IDs define the pedigree across generations.";
  if (analysisType === "case-control") return "Assign one case and one control, then complete phenotype and control relationship.";
  return "Assign one tumor and one matched normal belonging to the same individual.";
}

function renderAnalysisMember(member) {
  const card = document.createElement("section");
  card.className = "analysis-member-card";
  const heading = document.createElement("div");
  heading.className = "analysis-member-heading";
  const name = document.createElement("strong");
  name.textContent = member.sample_name;
  const role = document.createElement("span");
  role.className = "analysis-member-role";
  role.textContent = displayValue(member.relationship);
  heading.append(name, role);
  card.appendChild(heading);

  const fields = document.createElement("div");
  fields.className = "analysis-member-fields";
  const rowIndex = sampleSheet.organizationRows.indexOf(member);
  appendSelectField(fields, "Role", relationshipOptions(member.analysis_type), member.relationship, (value) => {
    updateMemberRelationship(rowIndex, value);
  });
  appendSelectField(fields, "Sex", sexValues, member.sex || "unknown", (value) => {
    member.sex = value;
    refreshAnalysisConfiguration();
  });

  if (member.analysis_type === "family") {
    const sampleNames = sampleSheet.rows.map((row) => row.sample_name).filter((name) => name && name !== member.sample_name);
    appendDatalistField(fields, "Father", sampleNames, member.father || "", `samplesheet-father-${rowIndex}`, (value) => {
      member.father = value;
      refreshAnalysisConfiguration();
    }, (value) => {
      assignSelectedParent(rowIndex, "father", value);
      refreshAnalysisConfiguration(true);
    }, {placeholder: "Loaded sample or external ID"});
    appendDatalistField(fields, "Mother", sampleNames, member.mother || "", `samplesheet-mother-${rowIndex}`, (value) => {
      member.mother = value;
      refreshAnalysisConfiguration();
    }, (value) => {
      assignSelectedParent(rowIndex, "mother", value);
      refreshAnalysisConfiguration(true);
    }, {placeholder: "Loaded sample or external ID"});
    appendSelectField(fields, "Affected", affectedValues, member.affected || "unknown", (value) => {
      member.affected = value;
      refreshAnalysisConfiguration();
    });
    appendInputField(fields, "Twin group", member.twin_group || "", (value) => {
      member.twin_group = value;
      refreshAnalysisConfiguration();
    }, {placeholder: "Optional"});
  } else if (member.analysis_type === "case-control") {
    appendSelectField(fields, "Affected", affectedValues, member.affected || affectedForCaseControl(member.relationship), (value) => {
      member.affected = value;
      refreshAnalysisConfiguration();
    });
    if (member.relationship === "control") {
      appendSelectField(fields, "Relation to case", controlRelationshipValues, member.control_relationship || "unrelated", (value) => {
        member.control_relationship = value;
        refreshAnalysisConfiguration();
      });
    }
  } else if (member.analysis_type === "tumor-normal") {
    appendSelectField(fields, "Specimen", specimenTypes, member.specimen_type || "unknown", (value) => {
      member.specimen_type = value;
      refreshAnalysisConfiguration();
    });
    if (member.relationship === "tumor") {
      appendInputField(fields, "Tumor purity %", member.tumor_purity || "", (value) => {
        member.tumor_purity = value;
        refreshAnalysisConfiguration();
      }, {type: "number", min: "0", max: "100", step: "0.1", placeholder: "Optional"});
    }
  }

  card.appendChild(fields);
  return card;
}

function relationshipOptions(analysisType) {
  if (analysisType === "family") return familyRelationships;
  if (analysisType === "case-control") return caseControlRelationships;
  return tumorNormalRelationships;
}

function updateMemberRelationship(rowIndex, relationship) {
  const member = sampleSheet.organizationRows[rowIndex];
  const peers = analysisGroupMembers(member.analysis_type, member.analysis_id).filter((row) => row !== member);
  if (member.analysis_type === "family" && ["proband", "father", "mother"].includes(relationship)) {
    peers.filter((row) => row.relationship === relationship).forEach((row) => {
      row.relationship = relationship === "proband" ? "sibling" : "other";
    });
  }
  if (member.analysis_type === "case-control") {
    peers.filter((row) => row.relationship === relationship).forEach((row) => {
      row.relationship = relationship === "case" ? "control" : "case";
      row.affected = affectedForCaseControl(row.relationship);
      row.control_relationship = row.relationship === "control" ? row.control_relationship || "unrelated" : "";
    });
    member.affected = affectedForCaseControl(relationship);
    member.control_relationship = relationship === "control" ? member.control_relationship || "unrelated" : "";
  }
  if (member.analysis_type === "tumor-normal") {
    peers.filter((row) => row.relationship === relationship).forEach((row) => {
      row.relationship = relationship === "tumor" ? "normal" : "tumor";
      if (row.relationship === "normal") row.tumor_purity = "";
    });
    if (relationship === "normal") member.tumor_purity = "";
  }
  member.relationship = relationship;
  if (relationship === "father") member.sex = "male";
  if (relationship === "mother") member.sex = "female";
  refreshAnalysisConfiguration(true);
}

function appendSelectField(container, label, options, value, onChange) {
  const field = drawerField(label);
  const select = makeSelect(options, value);
  select.addEventListener("change", () => onChange(select.value));
  field.appendChild(select);
  container.appendChild(field);
}

function appendInputField(container, label, value, onInput, attributes = {}) {
  const field = drawerField(label);
  const input = document.createElement("input");
  input.value = value || "";
  Object.entries(attributes).forEach(([name, attributeValue]) => {
    input.setAttribute(name, attributeValue);
  });
  input.addEventListener("input", () => onInput(input.value));
  field.appendChild(input);
  container.appendChild(field);
}

function appendDatalistField(container, label, options, value, listId, onInput, onChange, attributes = {}) {
  const field = drawerField(label);
  const input = document.createElement("input");
  const datalist = document.createElement("datalist");
  datalist.id = listId;
  options.forEach((option) => addOption(datalist, option));
  input.value = value || "";
  input.setAttribute("list", listId);
  Object.entries(attributes).forEach(([name, attributeValue]) => {
    input.setAttribute(name, attributeValue);
  });
  input.addEventListener("input", () => onInput(input.value));
  input.addEventListener("change", () => onChange(input.value));
  field.append(input, datalist);
  container.appendChild(field);
}

function drawerField(label) {
  const field = document.createElement("label");
  const text = document.createElement("span");
  text.className = "field-label";
  text.textContent = label;
  field.appendChild(text);
  return field;
}

function refreshAnalysisConfiguration(rerenderDrawer = false) {
  renderOrganizationRows();
  scheduleBuildSampleSheet();
  if (rerenderDrawer) renderAnalysisDrawer();
  else updateDrawerStatus();
}

function updateDrawerStatus() {
  const active = sampleSheet.activeAnalysisGroup;
  if (!active) return;
  const status = analysisGroupStatus(active.analysisType, active.analysisId);
  const node = document.querySelector("#samplesheet-analysis-drawer-status");
  node.textContent = status.complete ? "Configuration complete" : "Some required details are still missing";
  node.className = `muted drawer-status ${status.complete ? "complete" : "incomplete"}`;
}

function defaultOrganizationRows() {
  const names = sampleSheet.rows.map((row) => row.sample_name).filter(Boolean);
  const existing = new Map(sampleSheet.organizationRows.map((row) => [row.sample_name, row]));
  return names.map((name) => existing.get(name) || defaultAnalysisRow(name));
}

function defaultAnalysisRow(sampleName) {
  return {
    sample_name: sampleName,
    analysis_type: "only cases",
    analysis_id: sampleName,
    relationship: "proband",
    sex: "unknown",
    father: "",
    mother: "",
    affected: "unknown",
    individual_id: sampleName,
    control_relationship: "",
    specimen_type: "unknown",
    tumor_purity: "",
    twin_group: "",
  };
}

function analysisRowsFromLegacy(rows, organization) {
  if ((rows || []).some((row) => row.analysis_type)) {
    return rows.map((row) => ({...defaultAnalysisRow(row.sample_name), ...row}));
  }
  const converted = [];
  (rows || []).forEach((row) => {
    const analysisId = row.sample_id || row.case || "";
    if (organization === "case-control") {
      if (row.case) converted.push(analysisRow(row.case, "case-control", analysisId, "case"));
      if (row.control) converted.push(analysisRow(row.control, "case-control", analysisId, "control"));
      return;
    }
    if (organization === "trio") {
      if (row.case) {
        const proband = analysisRow(row.case, "family", analysisId, "proband");
        proband.father = row.parent1 || "";
        proband.mother = row.parent2 || "";
        converted.push(proband);
      }
      if (row.parent1) converted.push(analysisRow(row.parent1, "family", analysisId, "father", "male"));
      if (row.parent2) converted.push(analysisRow(row.parent2, "family", analysisId, "mother", "female"));
      return;
    }
    if (row.case) converted.push(defaultAnalysisRow(row.case));
  });

  const convertedByName = new Map(converted.map((row) => [row.sample_name, row]));
  return sampleSheet.rows
    .map((row) => row.sample_name)
    .filter(Boolean)
    .map((name) => convertedByName.get(name) || defaultAnalysisRow(name));
}

function analysisRow(sampleName, analysisType, analysisId, relationship, sex = "unknown") {
  const row = {
    ...defaultAnalysisRow(sampleName),
    analysis_type: analysisType,
    analysis_id: analysisId || sampleName,
    relationship,
    sex,
  };
  if (analysisType === "case-control") {
    row.affected = affectedForCaseControl(relationship);
    row.control_relationship = relationship === "control" ? "unrelated" : "";
  }
  return row;
}

function changeAnalysisType(rowIndex, analysisType) {
  const row = sampleSheet.organizationRows[rowIndex];
  row.analysis_type = analysisType;
  const existingIds = analysisType === "only cases" ? [] : analysisIdOptions(row, rowIndex);
  row.analysis_id = existingIds.length ? "" : row.sample_name;
  row.relationship = analysisType === "family"
    ? "proband"
    : analysisType === "case-control"
      ? "case"
      : analysisType === "tumor-normal"
        ? "tumor"
        : "proband";
  row.individual_id = row.sample_name;
  row.affected = analysisType === "case-control" ? "affected" : "unknown";
  row.control_relationship = "";
  row.specimen_type = analysisType === "tumor-normal" ? "unknown" : "";
  row.tumor_purity = "";
  if (analysisType !== "family") {
    row.sex = "unknown";
    row.father = "";
    row.mother = "";
    if (analysisType !== "case-control") row.affected = "unknown";
    row.twin_group = "";
  }
  normalizeAnalysisGroup(rowIndex);
  renderOrganizationRows();
  scheduleBuildSampleSheet();
}

function normalizeAnalysisGroup(rowIndex) {
  const row = sampleSheet.organizationRows[rowIndex];
  if (!row || row.analysis_type === "only cases" || !row.analysis_id) return;
  const peers = sampleSheet.organizationRows.filter(
    (candidate, index) => index !== rowIndex && candidate.analysis_type === row.analysis_type && candidate.analysis_id === row.analysis_id
  );

  if (row.analysis_type === "case-control" && row.relationship === "case" && peers.some((candidate) => candidate.relationship === "case")) {
    row.relationship = "control";
    row.affected = "unaffected";
    row.control_relationship = row.control_relationship || "unrelated";
  }

  if (row.analysis_type === "tumor-normal" && row.relationship === "tumor" && peers.some((candidate) => candidate.relationship === "tumor")) {
    row.relationship = "normal";
    row.individual_id = peers[0].individual_id || peers[0].sample_name;
  }

  if (row.analysis_type === "family") {
    if (row.relationship === "proband" && peers.some((candidate) => candidate.relationship === "proband")) {
      row.relationship = "sibling";
    }
    if (row.relationship === "father") row.sex = "male";
    if (row.relationship === "mother") row.sex = "female";
    inheritProbandParents(row);
    propagateFamilyParents(row.analysis_id);
  }
}

function affectedForCaseControl(relationship) {
  if (relationship === "case") return "affected";
  if (relationship === "control") return "unaffected";
  return "unknown";
}

function inheritProbandParents(row) {
  if (!["proband", "sibling"].includes(row.relationship)) return;
  const proband = sampleSheet.organizationRows.find(
    (candidate) => candidate.analysis_type === "family" && candidate.analysis_id === row.analysis_id && candidate.relationship === "proband"
  );
  if (!proband || proband === row) return;
  if (!row.father) row.father = proband.father || "";
  if (!row.mother) row.mother = proband.mother || "";
}

function assignSelectedParent(rowIndex, parentType, sampleName) {
  if (!sampleName) return;
  const child = sampleSheet.organizationRows[rowIndex];
  const parent = sampleSheet.organizationRows.find((candidate) => candidate.sample_name === sampleName);
  if (!child || !parent) return;
  const alreadyInFamily = parent.analysis_type === "family" && parent.analysis_id === child.analysis_id;
  parent.analysis_type = "family";
  parent.analysis_id = child.analysis_id || child.sample_name;
  if (child.relationship === "proband") {
    parent.relationship = parentType;
  } else if (!alreadyInFamily || ["proband", "sibling"].includes(parent.relationship)) {
    parent.relationship = "other";
  }
  parent.sex = parentType === "father" ? "male" : "female";
  propagateFamilyParents(parent.analysis_id);
}

function propagateFamilyParents(analysisId) {
  const members = sampleSheet.organizationRows.filter(
    (row) => row.analysis_type === "family" && row.analysis_id === analysisId
  );
  const father = members.find((row) => row.relationship === "father");
  const mother = members.find((row) => row.relationship === "mother");
  members.forEach((member) => {
    if (!["proband", "sibling"].includes(member.relationship)) return;
    if (!member.father && father) member.father = father.sample_name;
    if (!member.mother && mother) member.mother = mother.sample_name;
  });
}

function makeSelect(options, selectedValue = "") {
  const select = document.createElement("select");
  options.forEach((option) => {
    if (Array.isArray(option)) addOption(select, option[0], option[1]);
    else addOption(select, option);
  });
  select.value = selectedValue || "";
  return select;
}

function analysisIdOptions(row, rowIndex) {
  const existingIds = sampleSheet.organizationRows
    .filter((candidate, index) => index !== rowIndex && candidate.analysis_type === row.analysis_type)
    .map((candidate) => candidate.analysis_id)
    .filter(Boolean);
  return [...new Set(existingIds)].map((id) => [id, id]);
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

function renderOrganizationStatus() {
  const status = document.querySelector("#samplesheet-organization-status");
  const download = document.querySelector("#samplesheet-download");
  if (!status || !download) return;
  const configuredGroups = sampleSheet.organizationRows.filter((row) => row.analysis_type !== "only cases");
  const hasIncompleteGroup = configuredGroups.some(
    (row) => !analysisGroupStatus(row.analysis_type, row.analysis_id).complete
  );
  status.textContent = hasIncompleteGroup
    ? "The samplesheet can be saved, but some analysis groups still need details before the workflow can run."
    : "Samples and analysis groups are ready to save.";
  status.classList.toggle("draft-status", hasIncompleteGroup);
  download.disabled = false;
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

function addOption(select, value, label = value) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label || "-";
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
