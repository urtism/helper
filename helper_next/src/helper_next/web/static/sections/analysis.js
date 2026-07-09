import {getAnalysisRunStatus, getAnalysisPipeline, startFakeAnalysis, startRealAnalysis, validateAnalysisRun, stopAnalysisRun, getProject, getPickerSelection} from "../api.js?v=20260629-8";

const baseWorkflowTree = [
  {
    id: "prealignment",
    label: "Prealignment",
    detail: "FASTQ quality control",
    inputs: ["fastq"],
    outputs: ["fastq"],
    children: [{id: "fastq_QC", label: "fastq_QC", detail: "FastQC reports"}],
  },
  {
    id: "alignment",
    label: "Alignment",
    detail: "FASTQ to sorted BAM",
    inputs: ["fastq"],
    outputs: ["bam"],
    children: [
      {id: "fastq_alignment", label: "fastq_alignment", detail: "BWA, Bowtie2, Novoalign"},
      {id: "sam_to_bam", label: "sam_to_bam", detail: "samtools view"},
      {id: "sort_bam", label: "sort_bam", detail: "samtools sort"},
      {id: "index_bam", label: "index_bam", detail: "samtools index"},
    ],
  },
  {
    id: "preprocessing",
    label: "Preprocessing",
    detail: "BAM cleanup and indexing",
    inputs: ["bam"],
    outputs: ["bam"],
    children: [
      {id: "filter_bam", label: "filter_bam", detail: "BAM filtering module pending", disabled: true},
      {id: "merge_UMI", label: "merge_UMI", detail: "UMI merge module pending", disabled: true},
      {id: "add_readgroups", label: "add_readgroups", detail: "Picard AddOrReplaceReadGroups"},
      {id: "mark_pcr_dup", label: "mark_pcr_dup", detail: "Picard MarkDuplicates"},
      {id: "indel_realignment", label: "indel_realignment", detail: "GATK3 RealignerTargetCreator + IndelRealigner", defaultChecked: false},
      {id: "BQ_recalibration", label: "BQ_recalibration", detail: "GATK3 BaseRecalibrator + PrintReads", defaultChecked: false},
    ],
  },
  {
    id: "variantcalling",
    label: "Variant Calling",
    detail: "SNV/InDel, CNV, and SV calling",
    inputs: ["bam"],
    outputs: ["vcf", "cnv", "sv"],
    children: [
      {id: "short_variants", label: "Short Variants", detail: "SNV and small InDel calling"},
      {id: "cnv_calling", label: "CNV Calling", detail: "Copy-number variant calling module pending", disabled: true},
      {id: "sv_calling", label: "SV Calling", detail: "Structural variant calling module pending", disabled: true},
    ],
  },
  {
    id: "postprocessing",
    label: "Postprocessing",
    detail: "VCF normalization, filtering, and TSV export",
    inputs: ["vcf"],
    outputs: ["vcf", "tsv"],
    children: [
      {id: "vcf_norm", label: "vcf_norm", detail: "Normalize VCF records with bcftools", defaultChecked: false},
      {id: "vcf_filter", label: "vcf_filter", detail: "Apply configured VCF filters", defaultChecked: false},
      {id: "vcf_to_tsv", label: "vcf_to_tsv", detail: "Export core VCF fields to TSV"},
    ],
  },
  {
    id: "annotation",
    label: "Annotation",
    detail: "Variant annotation and annotated TSV export",
    inputs: ["vcf"],
    outputs: ["vcf", "tsv"],
    children: [
      {id: "vep_annotation", label: "VEP Annotation", detail: "Annotate variants with Ensembl VEP"},
      {id: "ann_vcf_to_tsv", label: "ann_vcf_to_tsv", detail: "Export annotated VCF fields to TSV"},
    ],
  },
];

let workflowTree = cloneWorkflowTree(baseWorkflowTree);

const analysisState = {
  samplesheetContent: "",
  samplesheetName: "",
  pollTimer: null,
  activeRunDir: "",
  activeRunPayload: null,
  workdirPickerPoll: null,
  activeWorkdirPickerId: "",
  pipelineConfig: null,
  pipelineName: "",
  queueItems: [],
  workflowExpanded: new Set(workflowTree.map((node) => node.id)),
  workflowChecked: new Set(
    workflowTree
      .filter((node) => !node.disabled)
      .flatMap((node) => [
        node.id,
        ...node.children
          .filter((child) => !child.disabled && child.defaultChecked !== false)
          .map((child) => child.id),
      ]),
  ),
  workflowAvailable: new Set(workflowTree.filter((node) => !node.disabled).map((node) => node.id)),
  workflowUnavailableReasons: Object.fromEntries(
    workflowTree.filter((node) => node.disabled).map((node) => [node.id, node.detail]),
  ),
  inputTypes: new Set(["fastq"]),
};

const defaultWorkdirStorageKey = "helper_next.analysis.default_workdir";

export function initAnalysis() {
  const runId = document.querySelector("#analysis-run-id");
  if (runId && !runId.value) {
    runId.value = defaultRunId();
  }

  const workdir = document.querySelector("#analysis-workdir");
  if (workdir && !workdir.value) {
    workdir.value = window.localStorage.getItem(defaultWorkdirStorageKey) || "/tmp/helper_next_analysis";
  }

  bindChange("#analysis-samplesheet-file", loadSamplesheetFile);
  bindChange("#analysis-pipeline-file", loadPipelineFile);
  bindChange("#analysis-set-workdir-default", updateDefaultWorkdir);
  bindChange("#analysis-workdir", updateDefaultWorkdir);
  bindClick("#analysis-workdir-browse", openWorkdirPickerPage);
  bindClickAll(".analysis-start-fake", startFakeRun);
  bindClick("#analysis-add-to-queue", addCurrentRunToQueue);
  bindClick("#analysis-stop-run", stopCurrentRunAndContinue);
  bindClick("#analysis-console-refresh", refreshConsole);
  loadRunSetupOptions();
  renderWorkflowTree();
  renderQueueList();
  renderSelectedWorkflow();
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
  analysisState.inputTypes = inferSamplesheetInputTypes(analysisState.samplesheetContent);
  document.querySelector("#analysis-samplesheet-name").textContent = file.name;
  updateWorkflowAvailability();
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
  if (!selectedWorkflowSteps().length) {
    status.textContent = "Select at least one workflow step";
    return;
  }
  updateDefaultWorkdir();

  const payload = analysisPayload();

  await startAnalysisPayload(payload);
}

function valueOf(selector) {
  const element = document.querySelector(selector);
  return element ? element.value.trim() : "";
}

function checkedOf(selector) {
  const element = document.querySelector(selector);
  return element ? element.checked : false;
}

async function loadRunSetupOptions() {
  try {
    const project = await getProject();
    populateSelect(
      "#analysis-gene-panel-design",
      project.gene_panel_designs || project.pipelines || [],
      "Select a saved design",
    );
    populateSelect(
      "#analysis-pipeline-file",
      project.pipelines || [],
      "Generated default pipeline",
    );
    populateSelect(
      "#analysis-tools-file",
      project.tool_config_files || project.tool_configs || [],
      "Default tools_cfg/tools.cfg",
    );
  } catch (error) {
    populateSelect("#analysis-gene-panel-design", [], "No saved designs found");
    populateSelect("#analysis-pipeline-file", [], "Generated default pipeline");
    populateSelect("#analysis-tools-file", [], "Default tools_cfg/tools.cfg");
  }
}

async function loadPipelineFile() {
  const selected = valueOf("#analysis-pipeline-file");
  if (!selected) {
    analysisState.pipelineConfig = null;
    analysisState.pipelineName = "";
    workflowTree = cloneWorkflowTree(baseWorkflowTree);
    resetDefaultWorkflowSelection();
    updateWorkflowAvailability();
    renderConsoleText("Pipeline: generated default pipeline");
    return;
  }
  try {
    const result = await getAnalysisPipeline(selected);
    analysisState.pipelineConfig = result.config || null;
    analysisState.pipelineName = result.name || selected;
    applyPipelineToWorkflowTree(analysisState.pipelineConfig);
    updateWorkflowAvailability();
    renderConsoleText(`Pipeline loaded: ${analysisState.pipelineName}`);
  } catch (error) {
    document.querySelector("#analysis-status").textContent = error.message;
    renderConsoleText(error.message);
  }
}

function populateSelect(selector, items, placeholder) {
  const select = document.querySelector(selector);
  if (!select) return;
  select.replaceChildren();

  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = placeholder;
  select.appendChild(empty);

  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item;
    option.textContent = item;
    select.appendChild(option);
  });
}

function updateDefaultWorkdir() {
  const checkbox = document.querySelector("#analysis-set-workdir-default");
  const workdir = valueOf("#analysis-workdir");
  if (!checkbox) return;
  if (checkbox.checked && workdir) {
    window.localStorage.setItem(defaultWorkdirStorageKey, workdir);
  } else if (!checkbox.checked) {
    window.localStorage.removeItem(defaultWorkdirStorageKey);
  }
}

function openWorkdirPickerPage() {
  const pickerId = `workdir-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  analysisState.activeWorkdirPickerId = pickerId;
  startWorkdirPickerPolling(pickerId);
  const params = new URLSearchParams({
    mode: "directory",
    step: "prealignment",
    pickerId,
  });
  const current = valueOf("#analysis-workdir");
  if (current) params.set("path", current);
  window.open(`/static/file_picker.html?${params.toString()}`, "helper-next-directory-picker");
}

function startWorkdirPickerPolling(pickerId) {
  if (analysisState.workdirPickerPoll) {
    window.clearInterval(analysisState.workdirPickerPoll);
  }
  analysisState.workdirPickerPoll = window.setInterval(() => {
    pollWorkdirPickerSelection(pickerId).catch(showAnalysisError);
  }, 700);
}

async function pollWorkdirPickerSelection(pickerId) {
  if (!pickerId || pickerId !== analysisState.activeWorkdirPickerId) return;
  const data = await getPickerSelection(pickerId);
  const directory = data.files && data.files[0];
  if (!directory) return;
  window.clearInterval(analysisState.workdirPickerPoll);
  analysisState.workdirPickerPoll = null;
  analysisState.activeWorkdirPickerId = "";
  setWorkdir(directory);
}

function setWorkdir(directory) {
  const workdir = document.querySelector("#analysis-workdir");
  if (!workdir) return;
  workdir.value = directory;
  workdir.dispatchEvent(new Event("change", {bubbles: true}));
  renderConsoleText(`Work directory selected: ${directory}`);
}

async function startAnalysisPayload(payload) {
  const status = document.querySelector("#analysis-status");
  const workflow = payload.mode || "fake_alignment";
  analysisState.activeRunPayload = payload;
  renderQueueList();
  setConsoleState("Submitting");
  renderConsoleText(`Submitting ${payload.run_id} (${workflow})...`);
  try {
    const result = workflow === "real_alignment" ? await startRealAnalysis(payload) : await startFakeAnalysis(payload);
    renderResult(result);
    startConsolePolling(result.run_dir, result.status === "submitted");
  } catch (error) {
    status.textContent = error.message;
    renderQueueList();
    setConsoleState("Error");
    renderConsoleText(error.message);
  }
}

async function stopCurrentRunAndContinue() {
  const status = document.querySelector("#analysis-status");
  if (!analysisState.activeRunDir) {
    status.textContent = "No running analysis selected";
    return;
  }
  if (!window.confirm("Stop the current analysis and start the next queued analysis?")) {
    return;
  }
  try {
    const result = await stopAnalysisRun(analysisState.activeRunDir);
    stopConsolePolling();
    setConsoleState("Stopping");
    renderConsoleText(`${result.message}\nrun_dir=${result.run_dir}\npid=${result.pid || ""}`);
    analysisState.activeRunDir = "";
    analysisState.activeRunPayload = null;
    const next = analysisState.queueItems.shift();
    if (!next) {
      renderQueueList();
      status.textContent = "Analysis stop requested";
      return;
    }
    renderQueueList();
    status.textContent = `Analysis stop requested. Starting next queued analysis: ${next.message}`;
    await startAnalysisPayload(next.payload);
  } catch (error) {
    status.textContent = error.message;
    renderConsoleText(error.message);
  }
}

function showAnalysisError(error) {
  const status = document.querySelector("#analysis-status");
  if (status) status.textContent = error.message;
}

function cloneWorkflowTree(tree) {
  return tree.map((node) => ({...node, children: node.children.map((child) => ({...child}))}));
}

function resetDefaultWorkflowSelection() {
  analysisState.workflowChecked = new Set(
    workflowTree
      .filter((node) => !node.disabled)
      .flatMap((node) => [
        node.id,
        ...node.children
          .filter((child) => !child.disabled && child.defaultChecked !== false)
          .map((child) => child.id),
      ]),
  );
  analysisState.workflowExpanded = new Set(workflowTree.map((node) => node.id));
}

function applyPipelineToWorkflowTree(config) {
  workflowTree = cloneWorkflowTree(baseWorkflowTree);
  analysisState.workflowChecked = new Set();
  analysisState.workflowExpanded = new Set(workflowTree.map((node) => node.id));
  const workflow = Array.isArray(config?.workflow) ? config.workflow : [];

  workflowTree.forEach((node) => {
    const stepConfig = config?.[node.id] || {};
    if (workflow.includes(node.id)) {
      analysisState.workflowChecked.add(node.id);
    }
    const configuredSubsteps = Array.isArray(stepConfig.workflow) ? stepConfig.workflow : [];
    node.children.forEach((child) => {
      if (configuredSubsteps.includes(child.id) && !child.disabled) {
        analysisState.workflowChecked.add(child.id);
      }
      const childConfig = stepConfig[child.id] || {};
      if (childConfig.tool) {
        child.detail = `${child.detail}. Tool: ${childConfig.tool}`;
      }
    });
    if (node.id === "variantcalling" && Array.isArray(stepConfig.tools) && stepConfig.tools.length) {
      node.children = [
        {
          id: "short_variants",
          label: "Short Variants",
          detail: `SNV and small InDel calling. Tools: ${stepConfig.tools.join(", ")}`,
        },
        {id: "cnv_calling", label: "CNV Calling", detail: "Copy-number variant calling module pending", disabled: true},
        {id: "sv_calling", label: "SV Calling", detail: "Structural variant calling module pending", disabled: true},
      ];
      if (workflow.includes(node.id)) {
        analysisState.workflowChecked.add("short_variants");
      }
    }
    if (node.id === "annotation") {
      const vepTool = stepConfig.vep_annotation?.tool;
      if (vepTool) {
        const vep = node.children.find((child) => child.id === "vep_annotation");
        if (vep) vep.detail = `Annotate variants with Ensembl VEP. Tool: ${vepTool}`;
      }
    }
  });
}

function selectedWorkflowSteps() {
  return workflowTree
    .filter((node) => analysisState.workflowChecked.has(node.id) && analysisState.workflowAvailable.has(node.id))
    .map((node) => node.id);
}

function selectedPreprocessingSubsteps() {
  if (!analysisState.workflowChecked.has("preprocessing")) {
    return [];
  }
  const preprocessing = workflowTree.find((node) => node.id === "preprocessing");
  if (!preprocessing) return [];
  return preprocessing.children
    .filter((child) => !child.disabled && analysisState.workflowChecked.has(child.id))
    .map((child) => child.id);
}

function selectedPostprocessingSubsteps() {
  if (!analysisState.workflowChecked.has("postprocessing")) {
    return [];
  }
  const postprocessing = workflowTree.find((node) => node.id === "postprocessing");
  if (!postprocessing) return [];
  return postprocessing.children
    .filter((child) => !child.disabled && analysisState.workflowChecked.has(child.id))
    .map((child) => child.id);
}

function selectedAnnotationSubsteps() {
  if (!analysisState.workflowChecked.has("annotation")) {
    return [];
  }
  const annotation = workflowTree.find((node) => node.id === "annotation");
  if (!annotation) return [];
  return annotation.children
    .filter((child) => !child.disabled && analysisState.workflowChecked.has(child.id))
    .map((child) => child.id);
}

function inferSamplesheetInputTypes(content) {
  const text = content || "";
  const types = new Set();
  if (/fastq_R1|fastq_R2|\.f(ast)?q(\.gz)?/i.test(text)) types.add("fastq");
  if (/"bam"\s*:|\.bam\b|\.sam\b|\.cram\b/i.test(text)) types.add("bam");
  if (/merged_vcf|"\s*vcf"\s*:|\.vcf(\.gz)?\b/i.test(text)) types.add("vcf");
  if (/variants_tsv|"\s*tsv"\s*:|\.tsv(\.gz)?\b/i.test(text)) types.add("tsv");
  return types.size ? types : new Set(["fastq"]);
}

function updateWorkflowAvailability() {
  const availableTypes = new Set(analysisState.inputTypes);
  const availableSteps = new Set();
  const reasons = {};

  workflowTree.forEach((node) => {
    if (node.disabled) {
      reasons[node.id] = node.detail;
      analysisState.workflowChecked.delete(node.id);
      return;
    }
    const canRun = node.inputs.some((type) => availableTypes.has(type));
    if (canRun) {
      availableSteps.add(node.id);
      if (analysisState.workflowChecked.has(node.id)) {
        node.outputs.forEach((type) => availableTypes.add(type));
      }
    } else {
      reasons[node.id] = `${node.label} requires ${node.inputs.join("/")} input`;
      analysisState.workflowChecked.delete(node.id);
    }
  });

  analysisState.workflowAvailable = availableSteps;
  analysisState.workflowUnavailableReasons = reasons;
  renderWorkflowTree();
}

function renderWorkflowTree() {
  const tree = document.querySelector("#analysis-workflow-tree");
  if (!tree) return;
  tree.replaceChildren();

  workflowTree.forEach((node) => {
    const isAvailable = analysisState.workflowAvailable.has(node.id);
    const nodeElement = document.createElement("div");
    nodeElement.className = `checkbox-tree-node${isAvailable ? "" : " unavailable"}`;
    nodeElement.dataset.step = node.id;
    nodeElement.setAttribute("role", "treeitem");
    nodeElement.setAttribute("aria-expanded", String(analysisState.workflowExpanded.has(node.id)));

    const row = document.createElement("div");
    row.className = "checkbox-tree-row macro";
    row.tabIndex = 0;

    const expand = document.createElement("button");
    expand.className = "checkbox-tree-expand";
    expand.type = "button";
    expand.textContent = analysisState.workflowExpanded.has(node.id) ? "▾" : "▸";
    expand.setAttribute("aria-label", `Toggle ${node.label}`);
    expand.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleExpanded(node.id);
    });

    const checkbox = treeCheckbox(node.id, analysisState.workflowChecked.has(node.id), parentIsIndeterminate(node));
    checkbox.disabled = !isAvailable;
    checkbox.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleChecked(node.id);
    });

    const label = document.createElement("span");
    label.className = "checkbox-tree-label";
    label.innerHTML = `<strong>${node.label}</strong><small>${isAvailable ? node.detail : analysisState.workflowUnavailableReasons[node.id]}</small>`;

    const count = document.createElement("span");
    count.className = "checkbox-tree-count";
    count.textContent = node.children.length
      ? `${node.children.length} ${node.children.length === 1 ? "step" : "steps"}`
      : "macrostep";

    row.append(expand, checkbox, label, count);
    row.addEventListener("click", () => toggleChecked(node.id));
    row.addEventListener("keydown", (event) => {
      if (event.key === "ArrowRight") {
        analysisState.workflowExpanded.add(node.id);
        renderWorkflowTree();
      } else if (event.key === "ArrowLeft") {
        analysisState.workflowExpanded.delete(node.id);
        renderWorkflowTree();
      } else if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        toggleChecked(node.id);
      }
    });
    nodeElement.appendChild(row);

    if (analysisState.workflowExpanded.has(node.id)) {
      const group = document.createElement("div");
      group.className = "checkbox-tree-children";
      group.setAttribute("role", "group");
      node.children.forEach((child) => {
        const childRow = document.createElement("div");
        childRow.className = `checkbox-tree-row micro${child.disabled ? " unavailable" : ""}`;
        childRow.setAttribute("role", "treeitem");
        childRow.tabIndex = 0;

        const branch = document.createElement("span");
        branch.className = "checkbox-tree-branch";

        const childCheckbox = treeCheckbox(child.id, analysisState.workflowChecked.has(child.id), false);
        childCheckbox.disabled = Boolean(child.disabled);
        childCheckbox.addEventListener("click", (event) => {
          event.stopPropagation();
          toggleChecked(child.id);
        });

        const childLabel = document.createElement("span");
        childLabel.className = "checkbox-tree-label";
        childLabel.innerHTML = `<strong>${child.label}</strong><small>${child.detail}</small>`;

        childRow.append(branch, childCheckbox, childLabel);
        childRow.addEventListener("click", () => toggleChecked(child.id));
        childRow.addEventListener("keydown", (event) => {
          if (event.key !== " " && event.key !== "Enter") return;
          event.preventDefault();
          toggleChecked(child.id);
        });
        group.appendChild(childRow);
      });
      nodeElement.appendChild(group);
    }

    tree.appendChild(nodeElement);
  });
  renderSelectedWorkflow();
}

function treeCheckbox(id, checked, indeterminate) {
  const checkbox = document.createElement("input");
  checkbox.className = "checkbox-tree-check";
  checkbox.type = "checkbox";
  checkbox.value = id;
  checkbox.checked = checked;
  checkbox.indeterminate = indeterminate;
  return checkbox;
}

function parentIsIndeterminate(node) {
  if (!analysisState.workflowChecked.has(node.id)) {
    return false;
  }
  const enabledChildren = node.children.filter((child) => !child.disabled);
  const checkedChildren = enabledChildren.filter((child) => analysisState.workflowChecked.has(child.id)).length;
  return checkedChildren > 0 && checkedChildren < enabledChildren.length;
}

function toggleExpanded(id) {
  if (analysisState.workflowExpanded.has(id)) {
    analysisState.workflowExpanded.delete(id);
  } else {
    analysisState.workflowExpanded.add(id);
  }
  renderWorkflowTree();
}

function toggleChecked(id) {
  if (workflowTree.some((node) => node.children.some((child) => child.id === id && child.disabled))) {
    return;
  }
  if (!analysisState.workflowAvailable.has(id) && workflowTree.some((node) => node.id === id)) {
    return;
  }
  if (analysisState.workflowChecked.has(id)) {
    analysisState.workflowChecked.delete(id);
  } else {
    analysisState.workflowChecked.add(id);
  }
  updateWorkflowAvailability();
}

function renderSelectedWorkflow() {
  const selected = selectedWorkflowSteps();
  const status = document.querySelector("#analysis-status");
  const summary = document.querySelector("#analysis-selected-workflow");
  if (summary) {
    const inputs = Array.from(analysisState.inputTypes).join(", ");
    summary.textContent = selected.length ? `Input: ${inputs}. Selected: ${selected.join(" -> ")}` : `Input: ${inputs}. No workflow steps selected`;
  }
  if (!status) return;
  if (!selected.length) {
    status.textContent = "Select at least one workflow step";
  } else if (status.textContent === "Select at least one workflow step") {
    status.textContent = "";
  }
}

function analysisPayload() {
  return {
    run_id: valueOf("#analysis-run-id"),
    mode: valueOf("#analysis-workflow"),
    workdir: valueOf("#analysis-workdir"),
    gene_panel_design: valueOf("#analysis-gene-panel-design"),
    tools_path: valueOf("#analysis-tools-file"),
    pipeline_path: valueOf("#analysis-pipeline-file"),
    set_workdir_default: checkedOf("#analysis-set-workdir-default"),
    keep_intermediates: checkedOf("#analysis-keep-intermediates"),
    execution_profile: valueOf("#analysis-execution-profile") || "local",
    queue: valueOf("#analysis-slurm-queue"),
    requested_workflow: selectedWorkflowSteps(),
    requested_preprocessing_workflow: selectedPreprocessingSubsteps(),
    requested_postprocessing_workflow: selectedPostprocessingSubsteps(),
    requested_annotation_workflow: selectedAnnotationSubsteps(),
    samplesheet_content: analysisState.samplesheetContent,
  };
}

async function addCurrentRunToQueue() {
  const status = document.querySelector("#analysis-status");
  const selected = selectedWorkflowSteps();
  status.textContent = "";
  if (!analysisState.samplesheetContent) {
    status.textContent = "Load a samplesheet first";
    return;
  }
  if (!selected.length) {
    status.textContent = "Select at least one workflow step";
    return;
  }
  updateDefaultWorkdir();
  const payload = analysisPayload();
  renderQueueList();
  status.textContent = `Validating ${payload.run_id || "unnamed run"}...`;
  let validation;
  try {
    validation = await validateAnalysisRun(payload);
  } catch (error) {
    renderQueueList();
    status.textContent = error.message;
    renderConsoleText(error.message);
    return;
  }
  if (queueHasDuplicate(payload)) {
    renderQueueList();
    status.textContent = "This analysis is already in queue";
    return;
  }
  const item = {
    status: "queued",
    message: `${validation.run_id || payload.run_id || "unnamed run"} (${selected.join(", ")})`,
    editable: true,
    payload,
  };
  analysisState.queueItems.push(item);
  renderQueueList();
  status.textContent = `Run added to queue. Checked ${validation.checked_files} input file${validation.checked_files === 1 ? "" : "s"}.`;
}

function queueHasDuplicate(payload) {
  const signature = queueSignature(payload);
  return analysisState.queueItems.some((item) => item.editable && queueSignature(item.payload) === signature);
}

function queueSignature(payload) {
  const relevant = {
    run_id: payload.run_id,
    mode: payload.mode,
    workdir: payload.workdir,
    gene_panel_design: payload.gene_panel_design,
    tools_path: payload.tools_path,
    pipeline_path: payload.pipeline_path,
    keep_intermediates: payload.keep_intermediates,
    execution_profile: payload.execution_profile,
    queue: payload.queue,
    requested_workflow: payload.requested_workflow,
    requested_preprocessing_workflow: payload.requested_preprocessing_workflow,
    requested_postprocessing_workflow: payload.requested_postprocessing_workflow,
    requested_annotation_workflow: payload.requested_annotation_workflow,
    samplesheet_content: payload.samplesheet_content,
  };
  return JSON.stringify(relevant);
}

function renderResult(result) {
  document.querySelector("#analysis-status").textContent = result.message;
  const runDetails = [
    {status: result.status, message: result.run_id},
    {status: "manifest", message: result.manifest},
    {status: "run config", message: result.run_config},
  ];
  if (result.pid) runDetails.push({status: "pid", message: String(result.pid)});
  if (result.execution_profile) runDetails.push({status: "profile", message: result.execution_profile});
  if (result.queue) runDetails.push({status: "queue", message: result.queue});
  if (result.gene_panel_design) runDetails.push({status: "design", message: result.gene_panel_design});
  if (result.tools_path) runDetails.push({status: "tools", message: result.tools_path});
  runDetails.push({status: "intermediates", message: result.keep_intermediates ? "kept" : "discarded"});
  if (result.work_dir) runDetails.push({status: "work dir", message: result.work_dir});
  if (result.nextflow_log) runDetails.push({status: "nextflow log", message: result.nextflow_log});
  if (result.nextflow_trace) runDetails.push({status: "nextflow trace", message: result.nextflow_trace});
  if (result.workflow_plan) runDetails.push({status: "workflow plan", message: result.workflow_plan});
  if (result.pid_file) runDetails.push({status: "pid file", message: result.pid_file});
  if (result.command_file) runDetails.push({status: "command file", message: result.command_file});
  if (result.command) runDetails.push({status: "command", message: result.command});
  if (result.logs && result.logs.step) runDetails.push({status: "step log", message: result.logs.step});
  renderQueueList();
  renderConsoleText(runDetails.map((item) => `${item.status}: ${item.message}`).join("\n"));
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
    sectionText("prealignment.step.log", files.prealignment_step_log, content.prealignment_step_log),
    sectionText("alignment.step.log", files.alignment_step_log, content.alignment_step_log),
    sectionText("preprocessing.step.log", files.preprocessing_step_log, content.preprocessing_step_log),
    sectionText("variantcalling.step.log", files.variantcalling_step_log, content.variantcalling_step_log),
    sectionText("postprocessing.step.log", files.postprocessing_step_log, content.postprocessing_step_log),
    sectionText("annotation.step.log", files.annotation_step_log, content.annotation_step_log),
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
  const queue = document.querySelector("#analysis-queue-list");
  queue.replaceChildren();
  items.forEach((item, index) => {
    const li = document.createElement("li");
    if (item.editable) li.className = "queue-editable-item";
    const status = document.createElement("strong");
    status.textContent = item.status;
    const message = document.createElement("span");
    message.textContent = ` ${item.message}`;
    li.appendChild(status);
    li.appendChild(message);
    if (item.editable) {
      li.appendChild(queueActions(index));
    }
    queue.appendChild(li);
  });
}

function renderQueueState(items) {
  renderAnalysisQueue(items);
}

function renderQueueList() {
  renderQueueState(analysisState.queueItems.length ? analysisState.queueItems : [{status: "idle", message: "No analysis queued"}]);
}

function queueActions(index) {
  const actions = document.createElement("span");
  actions.className = "queue-actions";
  actions.append(
    queueActionButton("Up", () => moveQueueItem(index, -1), index === 0),
    queueActionButton("Down", () => moveQueueItem(index, 1), index === analysisState.queueItems.length - 1),
    queueActionButton("Remove", () => removeQueueItem(index), false),
  );
  return actions;
}

function queueActionButton(label, callback, disabled) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.disabled = disabled;
  button.addEventListener("click", callback);
  return button;
}

function moveQueueItem(index, direction) {
  const target = index + direction;
  if (target < 0 || target >= analysisState.queueItems.length) return;
  const [item] = analysisState.queueItems.splice(index, 1);
  analysisState.queueItems.splice(target, 0, item);
  renderQueueList();
}

function removeQueueItem(index) {
  analysisState.queueItems.splice(index, 1);
  renderQueueList();
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
