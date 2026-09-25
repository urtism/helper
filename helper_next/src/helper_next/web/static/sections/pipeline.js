import {
  deletePipeline,
  getPipeline,
  getPipelines,
  newPipelineDraft,
  savePipeline,
  validatePipeline,
} from "../api.js?v=20260910-1";

const state = {
  index: null,
  config: null,
  original: null,
  loadedName: "",
  dirty: false,
  protected: false,
  activeSelection: {step: "prealignment", operation: ""},
};

const variantCategoryTargets = {
  short_variants: "variantcalling",
  cnv_calling: "cnvcalling",
  sv_calling: "svcalling",
  methylation: "methylation",
};

const byId = id => document.querySelector(`#${id}`);

export function initPipeline() {
  byId("pipeline-select").addEventListener("change", changePipeline);
  byId("pipeline-new").addEventListener("click", () => createDraft(false));
  byId("pipeline-duplicate").addEventListener("click", () => createDraft(true));
  byId("pipeline-save").addEventListener("click", saveDraft);
  byId("pipeline-delete").addEventListener("click", removeDraft);

  for (const id of ["pipeline-name", "pipeline-analysis", "pipeline-design", "pipeline-reference"]) {
    byId(id).addEventListener("input", updateMetadata);
    byId(id).addEventListener("change", updateMetadata);
  }

  window.addEventListener("beforeunload", event => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });

  window.addEventListener("helper:tools-updated", () => {
    if (state.dirty) {
      setStatus("Tools were updated. Save or discard this pipeline draft before refreshing its catalog.");
      return;
    }
    reloadIndex(state.loadedName).catch(showError);
  });

  document.addEventListener("click", event => {
    const navigation = event.target.closest(".nav-item");
    if (!navigation || navigation.dataset.section === "pipeline" || !state.dirty) return;
    if (!window.confirm("Discard unsaved pipeline changes?")) {
      event.preventDefault();
      event.stopImmediatePropagation();
    } else {
      discardChanges();
    }
  }, true);

  reloadIndex().catch(showError);
}

async function reloadIndex(preferredName = "") {
  state.index = await getPipelines();
  populateOptions("pipeline-analysis", state.index.analysis_types);
  populateOptions("pipeline-design", state.index.designs);
  populateOptions("pipeline-reference", state.index.references, true);
  renderPipelineSelect(preferredName);

  const selected = preferredName || state.index.pipelines[0]?.name || "";
  if (selected) {
    byId("pipeline-select").value = selected;
    await loadSelected(selected);
  } else {
    await createDraft(false, false);
  }
}

function populateOptions(id, values, allowEmpty = false) {
  const select = byId(id);
  select.replaceChildren();
  if (allowEmpty) select.add(new Option("Select reference...", ""));
  for (const value of values) select.add(new Option(value, value));
}

function renderPipelineSelect(selected = "") {
  const select = byId("pipeline-select");
  select.replaceChildren(new Option("Select a pipeline...", ""));
  for (const pipeline of state.index.pipelines) {
    select.add(new Option(pipeline.name, pipeline.name));
  }
  select.value = selected;
}

async function changePipeline(event) {
  const nextName = event.target.value;
  if (state.dirty && !window.confirm("Discard unsaved pipeline changes?")) {
    event.target.value = state.loadedName;
    return;
  }
  if (!nextName) return;
  await loadSelected(nextName).catch(showError);
}

async function loadSelected(name) {
  setStatus("Loading pipeline...");
  const result = await getPipeline(name);
  state.original = JSON.parse(JSON.stringify(result.config));
  state.config = JSON.parse(JSON.stringify(result.config));
  state.loadedName = result.name;
  state.protected = result.protected;
  byId("pipeline-name").value = result.name;
  renderEditor();
  setDirty(false);
  showValidation(result.errors, result.warnings);
}

async function createDraft(duplicate, askForName = true) {
  if (state.dirty && !window.confirm("Discard unsaved pipeline changes?")) return;
  const template = duplicate && state.config ? state.config : null;
  const result = await newPipelineDraft(template);
  const suggested = duplicate && state.loadedName ? `${state.loadedName}_copy` : "new_pipeline";
  const name = askForName ? window.prompt("Pipeline file name", suggested) : suggested;
  if (name === null) return;

  state.config = result.config;
  state.original = null;
  state.loadedName = "";
  state.protected = false;
  byId("pipeline-select").value = "";
  byId("pipeline-name").value = name.trim();
  renderEditor();
  setDirty(true);
  setStatus(duplicate ? "Duplicated draft. Save it with a new name." : "New draft created.");
}

function renderEditor() {
  byId("pipeline-editor").hidden = false;
  byId("pipeline-analysis").value = state.config.analysis || "";
  ensureOption("pipeline-analysis", state.config.analysis);
  byId("pipeline-design").value = state.config.design || "";
  ensureOption("pipeline-design", state.config.design);
  byId("pipeline-reference").value = state.config.reference_version || "";
  ensureOption("pipeline-reference", state.config.reference_version);
  renderWorkflow();
  renderSettings();
  renderSummary();
  updateActions();
}

function ensureOption(id, value) {
  if (!value) return;
  const select = byId(id);
  if (![...select.options].some(option => option.value === value)) {
    select.add(new Option(value, value));
  }
  select.value = value;
}

function renderWorkflow() {
  const tree = byId("pipeline-workflow-tree");
  tree.replaceChildren();
  const workflow = Array.isArray(state.config.workflow) ? state.config.workflow : [];

  for (const step of state.index.catalog) {
    const group = document.createElement("section");
    group.className = "pipeline-step";
    group.classList.toggle("selected", state.activeSelection?.step === step.id && !state.activeSelection.operation);
    const enabled = workflow.includes(step.id);
    const header = document.createElement("div");
    header.className = "pipeline-step-toggle";
    header.innerHTML = `<label><input type="checkbox" data-step="${step.id}" ${enabled ? "checked" : ""}><strong>${step.label}</strong><code>${step.id}</code></label><button class="compact-button" type="button" data-configure-step="${step.id}">Configure</button>`;
    header.querySelector("input").addEventListener("change", toggleStep);
    header.querySelector("button").addEventListener("click", selectSettings);
    group.appendChild(header);

    if (step.operations.length) {
      const operations = document.createElement("div");
      operations.className = "pipeline-operations";
      const selected = configuredOperations(step.id);
      for (const operation of step.operations) {
        const row = document.createElement("div");
        row.className = "pipeline-operation-row";
        row.classList.toggle("selected", state.activeSelection?.step === step.id && state.activeSelection.operation === operation.id);
        row.innerHTML = `<label><input type="checkbox" data-step="${step.id}" data-operation="${operation.id}" ${selected.includes(operation.id) ? "checked" : ""} ${enabled ? "" : "disabled"}><span>${operation.label}</span><code>${operation.id}</code></label>`;
        const actions = document.createElement("div");
        actions.className = "pipeline-operation-actions";
        for (const toolLabel of selectedToolLabels(step.id, operation.id)) {
          const badge = document.createElement("span");
          badge.className = "pipeline-selected-tool";
          badge.textContent = toolLabel;
          actions.appendChild(badge);
        }
        const configure = document.createElement("button");
        configure.className = "compact-button";
        configure.type = "button";
        configure.dataset.configureStep = step.id;
        configure.dataset.configureOperation = operation.id;
        configure.textContent = "Configure";
        actions.appendChild(configure);
        row.appendChild(actions);
        row.querySelector("input").addEventListener("change", toggleOperation);
        configure.addEventListener("click", selectSettings);
        operations.appendChild(row);
      }
      group.appendChild(operations);
    }
    tree.appendChild(group);
  }
}

function toggleStep(event) {
  const stepId = event.target.dataset.step;
  const workflow = Array.isArray(state.config.workflow) ? state.config.workflow : [];
  if (event.target.checked) {
    if (!state.config[stepId]) state.config[stepId] = {workflow: []};
    const selected = new Set([...workflow, stepId]);
    const known = new Set(state.index.catalog.map(step => step.id));
    const legacy = workflow.filter(id => !known.has(id));
    state.config.workflow = [...state.index.catalog.map(step => step.id).filter(id => selected.has(id)), ...legacy];
  } else {
    state.config.workflow = workflow.filter(id => id !== stepId);
  }
  changed();
}

function selectSettings(event) {
  state.activeSelection = {
    step: event.currentTarget.dataset.configureStep,
    operation: event.currentTarget.dataset.configureOperation || "",
  };
  renderWorkflow();
  renderSettings();
}

function toggleOperation(event) {
  const {step, operation} = event.target.dataset;
  if (!state.config[step]) state.config[step] = {workflow: []};
  const operations = configuredOperations(step);
  const selected = new Set(event.target.checked ? [...operations, operation] : operations.filter(id => id !== operation));
  const catalogStep = state.index.catalog.find(item => item.id === step);
  const known = new Set(catalogStep.operations.map(item => item.id));
  const legacy = operations.filter(id => !known.has(id));
  state.config[step].workflow = [...catalogStep.operations.map(item => item.id).filter(id => selected.has(id)), ...legacy];
  if (!Array.isArray(state.config.workflow)) state.config.workflow = [];
  if (event.target.checked && !state.config.workflow.includes(step)) state.config.workflow.push(step);
  changed();
}

function updateMetadata() {
  if (!state.config) return;
  state.config.analysis = byId("pipeline-analysis").value;
  state.config.design = byId("pipeline-design").value;
  state.config.reference_version = byId("pipeline-reference").value;
  changed(false);
}

function changed(renderTree = true) {
  setDirty(true);
  if (renderTree) renderWorkflow();
  renderSettings();
  renderSummary();
  validatePipeline(state.config).then(result => showValidation(result.errors, result.warnings)).catch(showError);
}

function renderSummary() {
  const workflow = Array.isArray(state.config.workflow) ? state.config.workflow : [];
  const known = new Map(state.index.catalog.map(step => [step.id, step.label]));
  const summary = byId("pipeline-summary");
  summary.replaceChildren();
  if (!workflow.length) summary.textContent = "No steps selected";
  for (const step of workflow) {
    const row = document.createElement("div");
    const operations = configuredOperations(step);
    row.innerHTML = `<strong>${known.get(step) || step}</strong><span>${Array.isArray(operations) && operations.length ? operations.join(" → ") : "Step enabled"}</span>`;
    summary.appendChild(row);
  }
  byId("pipeline-json").textContent = JSON.stringify(state.config, null, 2);
}

function configuredOperations(step) {
  const stepConfig = state.config?.[step] || {};
  if (step === "variantcalling") {
    if (Array.isArray(stepConfig.workflow)) return stepConfig.workflow;
    const selected = [];
    if (Array.isArray(stepConfig.tools) && stepConfig.tools.length) selected.push("short_variants");
    if (Array.isArray(state.config?.workflow) && state.config.workflow.includes("cnvcalling")) selected.push("cnv_calling");
    return selected;
  }
  if (Array.isArray(stepConfig.workflow)) return stepConfig.workflow;
  return [];
}

function renderSettings() {
  const panel = byId("pipeline-settings");
  panel.replaceChildren();
  if (!state.config || !state.activeSelection) {
    panel.textContent = "Select a phase or operation to configure it.";
    return;
  }

  const {step, operation} = state.activeSelection;
  const stepDefinition = state.index.catalog.find(item => item.id === step);
  const operationDefinition = stepDefinition?.operations.find(item => item.id === operation);
  const title = document.createElement("div");
  title.className = "pipeline-settings-heading";
  title.innerHTML = `<p class="eyebrow">${stepDefinition?.label || step}</p><h4>${operationDefinition?.label || "Phase settings"}</h4>`;
  panel.appendChild(title);

  const targetInfo = configurationTarget(step, operation, false);
  const resourceInfo = operation && variantCategoryTargets[operation]
    ? targetInfo
    : configurationTarget(step, "", false);
  renderResources(panel, resourceInfo.value, resourceInfo.ensure);

  if (!operation) {
    const help = document.createElement("p");
    help.className = "muted";
    help.textContent = "Select Configure on an operation to choose its tools and parameters.";
    panel.appendChild(help);
    return;
  }

  renderToolSelector(panel, operation, targetInfo);
  const target = targetInfo.value;
  const selectedTools = selectedToolNames(target, targetInfo.multiple);
  const knownTools = new Set(
    Object.values(state.index.tool_catalog || {}).flat().map(tool => tool.name),
  );
  const excluded = new Set(["tool", "tools", "workflow", "threads", "ram", "resolved", ...knownTools, ...selectedTools]);
  renderParameterGroup(panel, "Operation parameters", target, excluded, () => targetInfo.ensure());

  for (const toolName of selectedTools) {
    const toolConfig = target[toolName] && typeof target[toolName] === "object" && !Array.isArray(target[toolName])
      ? target[toolName]
      : {args: []};
    const ensureToolConfig = () => {
      const currentTarget = targetInfo.ensure();
      if (!currentTarget[toolName] || typeof currentTarget[toolName] !== "object" || Array.isArray(currentTarget[toolName])) {
        currentTarget[toolName] = {args: []};
      }
      return currentTarget[toolName];
    };
    renderParameterGroup(panel, `${toolName} parameters`, toolConfig, new Set(), ensureToolConfig);
  }
}

function configurationTarget(step, operation, create) {
  if (!operation) {
    const ensure = () => {
      if (!state.config[step] || typeof state.config[step] !== "object") state.config[step] = {workflow: []};
      return state.config[step];
    };
    return {value: create ? ensure() : (state.config[step] || {}), ensure, multiple: false};
  }

  if (variantCategoryTargets[operation]) {
    const key = variantCategoryTargets[operation];
    const ensure = () => {
      if (!state.config[key] || typeof state.config[key] !== "object") {
        state.config[key] = {tools: [], threads: "2", ram: "8g"};
      }
      return state.config[key];
    };
    return {value: create ? ensure() : (state.config[key] || {}), ensure, multiple: true};
  }

  const stepTarget = configurationTarget(step, "", create);
  const ensure = () => {
    const parent = stepTarget.ensure();
    if (!parent[operation] || typeof parent[operation] !== "object") parent[operation] = {tool: ""};
    return parent[operation];
  };
  return {value: create ? ensure() : (stepTarget.value[operation] || {}), ensure, multiple: false};
}

function renderResources(panel, resourceTarget, ensureTarget) {
  const fieldset = document.createElement("div");
  fieldset.className = "pipeline-setting-grid";
  for (const [key, label] of [["threads", "Threads"], ["ram", "RAM"]]) {
    const field = document.createElement("label");
    field.textContent = label;
    const input = document.createElement("input");
    if (key === "threads") {
      input.type = "number";
      input.min = "1";
      input.step = "1";
    }
    input.value = resourceTarget[key] ?? "";
    input.placeholder = key === "threads" ? "e.g. 4" : "e.g. 8g";
    input.addEventListener("input", () => {
      ensureTarget()[key] = input.value;
      draftChangedWithoutRerender();
    });
    field.appendChild(input);
    fieldset.appendChild(field);
  }
  panel.appendChild(fieldset);
}

function renderToolSelector(panel, operation, targetInfo) {
  const section = document.createElement("section");
  section.className = "pipeline-tool-selector";
  const heading = document.createElement("div");
  heading.className = "pipeline-subheading";
  heading.innerHTML = `<h5>${targetInfo.multiple ? "Tools" : "Tool"}</h5><span>${targetInfo.multiple ? "Multiple selection allowed" : "Select one tool"}</span>`;
  section.appendChild(heading);

  const target = targetInfo.value;
  const current = selectedToolNames(target, targetInfo.multiple);
  const available = [...(state.index.tool_catalog?.[operation] || [])];
  for (const name of current) {
    if (!available.some(tool => tool.name === name)) available.push({name, configured: false, version: "", path: "", container: ""});
  }

  if (targetInfo.multiple) {
    const options = document.createElement("div");
    options.className = "pipeline-tool-options";
    for (const tool of available) {
      const label = document.createElement("label");
      label.className = "pipeline-tool-option";
      const checked = current.includes(tool.name);
      label.innerHTML = `<input type="checkbox" ${checked ? "checked" : ""}><span><strong>${tool.name}</strong><small>${toolDescription(tool)}</small></span>`;
      label.querySelector("input").addEventListener("change", event => {
        const editable = targetInfo.ensure();
        const tools = new Set(selectedToolNames(editable, true));
        event.target.checked ? tools.add(tool.name) : tools.delete(tool.name);
        editable.tools = [...tools];
        if (event.target.checked && !editable[tool.name]) editable[tool.name] = {args: []};
        renderWorkflow();
        changed(false);
      });
      options.appendChild(label);
    }
    section.appendChild(options);
  } else {
    const label = document.createElement("label");
    label.textContent = "Compatible tool";
    const select = document.createElement("select");
    select.add(new Option("No tool selected", ""));
    for (const tool of available) select.add(new Option(`${tool.name} — ${toolDescription(tool)}`, tool.name));
    select.value = current[0] || "";
    select.addEventListener("change", () => {
      const editable = targetInfo.ensure();
      editable.tool = select.value;
      if (select.value && !editable[select.value]) editable[select.value] = {args: []};
      renderWorkflow();
      changed(false);
    });
    label.appendChild(select);
    section.appendChild(label);
  }

  const customRow = document.createElement("div");
  customRow.className = "pipeline-custom-tool";
  customRow.innerHTML = `<input type="text" placeholder="Custom tool name"><button type="button">Add custom tool</button>`;
  customRow.querySelector("button").addEventListener("click", () => {
    const name = customRow.querySelector("input").value.trim();
    if (!name) return;
    const editable = targetInfo.ensure();
    if (targetInfo.multiple) {
      editable.tools = [...new Set([...selectedToolNames(editable, true), name])];
    } else {
      editable.tool = name;
    }
    if (!editable[name]) editable[name] = {args: []};
    renderWorkflow();
    changed(false);
  });
  section.appendChild(customRow);
  panel.appendChild(section);
}

function selectedToolNames(target, multiple) {
  if (multiple) return Array.isArray(target.tools) ? target.tools.filter(Boolean) : [];
  return target.tool ? [target.tool] : [];
}

function selectedToolLabels(step, operation) {
  const targetInfo = configurationTarget(step, operation, false);
  const selected = selectedToolNames(targetInfo.value, targetInfo.multiple);
  const available = state.index.tool_catalog?.[operation] || [];
  return selected.map(name => {
    const tool = available.find(item => item.name === name);
    const version = tool?.version?.trim();
    if (!version || name.toLowerCase().includes(version.toLowerCase())) return name;
    return `${name} v${version}`;
  });
}

function toolDescription(tool) {
  const source = tool.container || tool.path;
  const details = [tool.version && `v${tool.version}`, source].filter(Boolean).join(" · ");
  return tool.configured ? (details || "configured") : "not configured in tools.cfg";
}

function renderParameterGroup(panel, title, object, excluded, ensureObject) {
  const section = document.createElement("section");
  section.className = "pipeline-parameter-group";
  const header = document.createElement("div");
  header.className = "pipeline-subheading";
  header.innerHTML = `<h5>${title}</h5>`;
  const add = document.createElement("button");
  add.type = "button";
  add.className = "compact-button";
  add.textContent = "Add parameter";
  add.addEventListener("click", () => {
    const name = window.prompt("Parameter name", "");
    if (!name?.trim()) return;
    const editable = ensureObject();
    if (!(name.trim() in editable)) editable[name.trim()] = "";
    changed(false);
  });
  header.appendChild(add);
  section.appendChild(header);

  const entries = Object.entries(object || {}).filter(([key]) => !excluded.has(key));
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No parameters configured.";
    section.appendChild(empty);
  }
  for (const [key, value] of entries) {
    const row = document.createElement("div");
    row.className = "pipeline-parameter-row";
    const label = document.createElement("label");
    label.textContent = key;
    const input = Array.isArray(value) || (value && typeof value === "object")
      ? document.createElement("textarea")
      : document.createElement("input");
    input.className = "pipeline-parameter-input";
    if (typeof value === "boolean") {
      input.type = "checkbox";
      input.checked = value;
    } else {
      if (typeof value === "number") input.type = "number";
      input.value = Array.isArray(value) ? value.join("\n") : (value && typeof value === "object" ? JSON.stringify(value, null, 2) : String(value ?? ""));
    }
    const eventName = value && typeof value === "object" ? "change" : "input";
    input.addEventListener(eventName, () => {
      const editable = ensureObject();
      if (Array.isArray(value)) {
        editable[key] = input.value.split("\n").map(item => item.trim()).filter(Boolean);
      } else if (value && typeof value === "object") {
        try {
          editable[key] = JSON.parse(input.value || "{}");
          input.classList.remove("invalid");
        } catch {
          input.classList.add("invalid");
          return setStatus(`${key}: invalid JSON`, true);
        }
      } else if (typeof value === "boolean") {
        editable[key] = input.checked;
      } else if (typeof value === "number") {
        editable[key] = input.value === "" ? "" : Number(input.value);
      } else {
        editable[key] = input.value;
      }
      draftChangedWithoutRerender();
    });
    label.appendChild(input);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "compact-button danger-action";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => {
      delete ensureObject()[key];
      changed(false);
    });
    row.append(label, remove);
    section.appendChild(row);
  }
  panel.appendChild(section);
}

function draftChangedWithoutRerender() {
  setDirty(true);
  renderSummary();
  validatePipeline(state.config).then(result => showValidation(result.errors, result.warnings)).catch(showError);
}

async function saveDraft() {
  const name = byId("pipeline-name").value.trim();
  if (!name) return setStatus("Enter a pipeline file name.", true);
  const validation = await validatePipeline(state.config).catch(showError);
  if (!validation || !validation.valid) return showValidation(validation?.errors || [], validation?.warnings || []);

  const existing = state.index.pipelines.some(item => item.name === name);
  const overwrite = existing && name === state.loadedName
    ? true
    : existing && window.confirm(`Overwrite ${name}.pipeline?`);
  if (existing && !overwrite) return;

  setStatus("Saving pipeline...");
  const result = await savePipeline(name, state.config, overwrite).catch(showError);
  if (!result) return;
  await reloadIndex(result.name);
  setStatus(`${result.filename} saved.`);
}

async function removeDraft() {
  if (!state.loadedName) return setStatus("This draft has not been saved yet.", true);
  if (state.protected) return setStatus("The default pipeline cannot be deleted.", true);
  if (!window.confirm(`Delete ${state.loadedName}.pipeline? This cannot be undone.`)) return;
  const result = await deletePipeline(state.loadedName).catch(showError);
  if (!result) return;
  state.config = null;
  state.original = null;
  state.loadedName = "";
  setDirty(false);
  await reloadIndex();
  setStatus(`${result.deleted} deleted.`);
}

function setDirty(dirty) {
  state.dirty = dirty;
  byId("pipeline-dirty-state").textContent = state.config ? (dirty ? "Unsaved changes" : "Saved") : "No pipeline loaded";
  byId("pipeline-dirty-state").classList.toggle("dirty", dirty);
  updateActions();
}

function discardChanges() {
  if (state.original) {
    state.config = JSON.parse(JSON.stringify(state.original));
    renderEditor();
  } else {
    state.config = null;
    state.loadedName = "";
    state.protected = false;
    byId("pipeline-select").value = "";
    byId("pipeline-name").value = "";
    byId("pipeline-editor").hidden = true;
  }
  setDirty(false);
}

function updateActions() {
  byId("pipeline-save").disabled = !state.config;
  byId("pipeline-duplicate").disabled = !state.config;
  byId("pipeline-delete").disabled = !state.loadedName || state.protected;
}

function showValidation(errors = [], warnings = []) {
  const messages = [...errors.map(value => `Error: ${value}`), ...warnings.map(value => `Warning: ${value}`)];
  setStatus(messages.join("\n"), errors.length > 0);
}

function setStatus(message, error = false) {
  const node = byId("pipeline-status");
  node.textContent = message || "Pipeline structure is valid.";
  node.classList.toggle("error", error);
}

function showError(error) {
  setStatus(error.message || String(error), true);
}
