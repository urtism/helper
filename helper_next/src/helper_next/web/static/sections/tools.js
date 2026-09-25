import {getTools, saveTools, testTool, validateTools} from "../api.js?v=20260910-2";

const TYPE_LABELS = {tool: "Tools", database: "Databases", reference: "References"};
const RESERVED_FIELDS = new Set(["path", "version", "versione", "tags", "fasta", "dict", "container"]);

const state = {
  filename: "tools_cfg/tools.cfg",
  revision: "",
  config: null,
  original: null,
  type: "tool",
  selected: "",
  originalName: "",
  dependencies: {},
  categoryNames: [],
  dirty: false,
  formDirty: false,
};

const node = (selector) => document.querySelector(selector);

export function initTools() {
  window.addEventListener("helper:project-loaded", ({detail}) => configureFiles(detail.tool_config_files || []));
  document.querySelectorAll("[data-tools-type]").forEach((button) => {
    button.addEventListener("click", () => selectType(button.dataset.toolsType));
  });
  node("#tools-config-file").addEventListener("change", changeFile);
  node("#tools-search").addEventListener("input", renderList);
  node("#tools-status-filter").addEventListener("change", renderList);
  node("#tools-add").addEventListener("click", addResource);
  node("#tools-delete").addEventListener("click", deleteResource);
  node("#tools-editor").addEventListener("submit", (event) => {
    event.preventDefault();
    applyEditor();
  });
  node("#tools-editor").addEventListener("input", markFormDirty);
  node("#tools-field-mode").addEventListener("change", updateModeFields);
  node("#tools-test").addEventListener("click", runTest);
  node("#tools-audit").addEventListener("click", runAudit);
  node("#tools-save").addEventListener("click", saveDraft);
  node("#tools-discard").addEventListener("click", discardDraft);
  window.addEventListener("beforeunload", (event) => {
    if (!state.dirty && !state.formDirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
  document.addEventListener("click", (event) => {
    const navigation = event.target.closest(".nav-item");
    if (!navigation || navigation.dataset.section === "tools" || (!state.dirty && !state.formDirty)) return;
    if (!window.confirm("Discard unsaved tool configuration changes?")) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    state.config = clone(state.original);
    state.dirty = false;
    state.formDirty = false;
    state.selected = "";
    state.originalName = "";
    renderAll();
  }, true);
}

function configureFiles(files) {
  const select = node("#tools-config-file");
  const choices = files.length ? files : ["tools_cfg/tools.cfg"];
  select.replaceChildren(...choices.map((filename) => option(filename, filename)));
  const preferred = choices.includes(state.filename) ? state.filename : choices[0];
  select.value = preferred;
  loadFile(preferred);
}

async function changeFile(event) {
  const previous = state.filename;
  if ((state.dirty || state.formDirty) && !window.confirm("Discard unsaved tool configuration changes?")) {
    event.target.value = previous;
    return;
  }
  await loadFile(event.target.value);
}

async function loadFile(filename) {
  setStatus("Loading tool configuration...");
  try {
    const payload = await getTools(filename);
    state.filename = payload.filename;
    state.revision = payload.revision;
    state.config = clone(payload.config);
    state.original = clone(payload.config);
    state.dependencies = dependencyMap(payload.resources);
    state.categoryNames = payload.categories || [];
    state.selected = "";
    state.originalName = "";
    state.dirty = false;
    state.formDirty = false;
    renderAll();
    renderAudit(payload.audit);
    setStatus("");
  } catch (error) {
    state.config = null;
    renderAll();
    setStatus(error.message, true);
  }
}

function selectType(type) {
  if (state.formDirty && !window.confirm("Discard changes in the current resource form?")) return;
  state.type = type;
  state.selected = "";
  state.originalName = "";
  state.formDirty = false;
  renderAll();
}

function renderAll() {
  document.querySelectorAll("[data-tools-type]").forEach((button) => {
    button.classList.toggle("active", button.dataset.toolsType === state.type);
  });
  node("#tools-list-title").textContent = TYPE_LABELS[state.type];
  renderList();
  renderEditor();
  renderSaveState();
}

function renderList() {
  const list = node("#tools-resource-list");
  list.replaceChildren();
  if (!state.config) return;
  const search = node("#tools-search").value.trim().toLowerCase();
  const filter = node("#tools-status-filter").value;
  const names = resourceNames(state.type);
  const matches = names.filter((name) => {
    const entry = resourceEntry(name);
    const capabilities = capabilitiesFor(name).join(" ");
    const used = Boolean((state.dependencies[name] || []).length);
    const status = resourceStatus(state.type, entry);
    const text = `${name} ${entry.version || entry.versione || ""} ${capabilities}`.toLowerCase();
    return (!search || text.includes(search)) && (!filter || filter === status || (filter === "used" && used) || (filter === "unused" && !used));
  });
  if (!matches.length) {
    const empty = document.createElement("li");
    empty.className = "tools-empty-item";
    empty.textContent = "No matching resources";
    list.appendChild(empty);
    return;
  }
  for (const name of matches) {
    const entry = resourceEntry(name);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tools-resource-item";
    button.classList.toggle("selected", name === state.selected);
    const title = document.createElement("strong");
    title.textContent = name;
    const detail = document.createElement("span");
    const used = (state.dependencies[name] || []).length;
    detail.textContent = [entry.version || entry.versione, resourceStatus(state.type, entry), used ? `${used} pipeline${used === 1 ? "" : "s"}` : "unused"].filter(Boolean).join(" · ");
    button.append(title, detail);
    button.addEventListener("click", () => selectResource(name));
    const item = document.createElement("li");
    item.appendChild(button);
    list.appendChild(item);
  }
}

function selectResource(name) {
  if (state.formDirty && name !== state.selected && !window.confirm("Discard changes in the current resource form?")) return;
  state.selected = name;
  state.originalName = name;
  state.formDirty = false;
  renderList();
  renderEditor();
  renderSaveState();
}

function addResource() {
  if (!state.config) return;
  if (state.formDirty && !window.confirm("Discard changes in the current resource form?")) return;
  state.selected = "";
  state.originalName = "";
  state.formDirty = false;
  showEditor("", {});
  node("#tools-field-name").focus();
}

function renderEditor() {
  if (!state.config || !state.selected) {
    node("#tools-editor").hidden = true;
    node("#tools-editor-empty").hidden = false;
    return;
  }
  showEditor(state.selected, resourceEntry(state.selected));
}

function showEditor(name, entry) {
  node("#tools-editor-empty").hidden = true;
  node("#tools-editor").hidden = false;
  node("#tools-editor-title").textContent = name || `New ${TYPE_LABELS[state.type].slice(0, -1).toLowerCase()}`;
  node("#tools-field-name").value = name;
  node("#tools-field-version").value = entry.version ?? entry.versione ?? "";
  node("#tools-field-path").value = entry.path || "";
  node("#tools-field-fasta").value = entry.fasta || "";
  node("#tools-field-dict").value = entry.dict || "";
  const container = containerValue(entry.container);
  node("#tools-field-mode").value = container.engine || "local";
  node("#tools-field-image").value = container.image || "";
  const advanced = Object.fromEntries(Object.entries(entry).filter(([key]) => !RESERVED_FIELDS.has(key)));
  node("#tools-field-advanced").value = JSON.stringify(advanced, null, 2);
  document.querySelectorAll(".tools-reference-field").forEach((field) => { field.hidden = state.type !== "reference"; });
  document.querySelectorAll(".tools-local-field").forEach((field) => { field.hidden = state.type === "reference"; });
  document.querySelectorAll(".tools-container-field").forEach((field) => { field.hidden = state.type !== "tool"; });
  node("#tools-capabilities").hidden = state.type !== "tool";
  renderCapabilities(name);
  renderDependencies(name);
  node("#tools-resource-status").textContent = resourceStatus(state.type, entry);
  node("#tools-test-result").replaceChildren();
  node("#tools-delete").disabled = !name;
  updateModeFields();
}

function renderCapabilities(name) {
  const wrapper = node("#tools-capability-grid");
  wrapper.replaceChildren();
  if (!state.config || state.type !== "tool") return;
  const selected = new Set(capabilitiesFor(name));
  for (const capability of categories()) {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = capability;
    input.checked = selected.has(capability);
    label.append(input, document.createTextNode(humanize(capability)));
    wrapper.appendChild(label);
  }
}

function updateModeFields() {
  const local = node("#tools-field-mode").value === "local";
  node("#tools-field-image").disabled = local;
  node("#tools-field-path").disabled = !local && state.type === "tool";
}

function markFormDirty() {
  state.formDirty = true;
  renderSaveState();
}

function applyEditor({quiet = false} = {}) {
  if (node("#tools-editor").hidden) return true;
  const name = node("#tools-field-name").value.trim();
  if (!name || name.includes("/") || name.includes("\\")) {
    setStatus("Enter a unique resource name without path separators.", true);
    return false;
  }
  const collision = allNames().find((candidate) => candidate === name && candidate !== state.originalName);
  if (collision) {
    setStatus(`A resource named '${name}' already exists.`, true);
    return false;
  }
  let advanced;
  try {
    advanced = JSON.parse(node("#tools-field-advanced").value || "{}");
  } catch (error) {
    setStatus(`Advanced metadata is not valid JSON: ${error.message}`, true);
    return false;
  }
  if (!advanced || Array.isArray(advanced) || typeof advanced !== "object") {
    setStatus("Advanced metadata must be a JSON object.", true);
    return false;
  }
  const entry = {...advanced};
  const version = node("#tools-field-version").value.trim();
  if (version) entry.version = version;
  if (state.type === "reference") {
    entry.fasta = node("#tools-field-fasta").value.trim();
    const dictionary = node("#tools-field-dict").value.trim();
    if (dictionary) entry.dict = dictionary;
    entry.tags = "reference";
  } else {
    const path = node("#tools-field-path").value.trim();
    if (path) entry.path = path;
    if (state.type === "database") {
      entry.tags = "database";
    } else {
      const capabilities = checkedCapabilities();
      entry.tags = capabilities.join(",");
      const mode = node("#tools-field-mode").value;
      const image = node("#tools-field-image").value.trim();
      if (mode !== "local" && image) entry.container = {engine: mode, image};
      syncCapabilities(state.originalName, name, capabilities);
    }
  }
  const names = resourceNames(state.type);
  if (state.originalName) {
    const index = names.indexOf(state.originalName);
    if (index >= 0) names[index] = name;
    if (state.originalName !== name) delete state.config[state.originalName];
  } else {
    names.push(name);
  }
  state.config[name] = entry;
  if (state.originalName && state.originalName !== name) {
    state.dependencies[name] = state.dependencies[state.originalName] || [];
    delete state.dependencies[state.originalName];
  }
  state.selected = name;
  state.originalName = name;
  state.dirty = true;
  state.formDirty = false;
  renderAll();
  if (!quiet) setStatus("Changes applied to the draft. Save the configuration to write them to disk.");
  return true;
}

function deleteResource() {
  const name = state.originalName;
  if (!name) return;
  const dependencies = state.dependencies[name] || [];
  if (dependencies.length) {
    setStatus(`Cannot delete '${name}'; used by ${dependencies.join(", ")}.`, true);
    return;
  }
  if (!window.confirm(`Delete '${name}' from the draft?`)) return;
  const names = resourceNames(state.type);
  names.splice(names.indexOf(name), 1);
  delete state.config[name];
  if (state.type === "tool") syncCapabilities(name, "", []);
  state.selected = "";
  state.originalName = "";
  state.dirty = true;
  state.formDirty = false;
  renderAll();
  setStatus("Resource removed from the draft.");
}

async function runAudit() {
  if (!state.config) return;
  if (state.formDirty && !applyEditor({quiet: true})) return;
  setStatus("Validating configuration...");
  try {
    const result = await validateTools(state.config);
    renderAudit(result);
    setStatus(result.valid ? "Audit complete." : "Audit found blocking errors.", !result.valid);
  } catch (error) {
    setStatus(error.message, true);
  }
}

function renderAudit(audit) {
  const errors = audit?.errors || [];
  const warnings = audit?.warnings || [];
  node("#tools-audit-summary").textContent = errors.length || warnings.length
    ? `${errors.length} error(s), ${warnings.length} warning(s)`
    : "Configuration is internally consistent.";
  const list = node("#tools-audit-list");
  list.replaceChildren();
  for (const [kind, messages] of [["error", errors], ["warning", warnings]]) {
    for (const message of messages) {
      const item = document.createElement("li");
      item.className = kind;
      item.textContent = message;
      list.appendChild(item);
    }
  }
}

async function runTest() {
  if (!applyEditor({quiet: true})) return;
  const resultNode = node("#tools-test-result");
  resultNode.textContent = "Testing...";
  try {
    const result = await testTool(state.type, state.selected, resourceEntry(state.selected));
    resultNode.className = `tools-test-result ${result.ok ? "success" : "error"}`;
    resultNode.replaceChildren();
    const preview = document.createElement("code");
    preview.textContent = result.preview || "No command preview";
    const list = document.createElement("ul");
    for (const check of result.checks || []) {
      const item = document.createElement("li");
      item.textContent = `${check.ok ? "OK" : "FAIL"} — ${check.label}: ${check.detail}`;
      list.appendChild(item);
    }
    resultNode.append(preview, list);
  } catch (error) {
    resultNode.className = "tools-test-result error";
    resultNode.textContent = error.message;
  }
}

async function saveDraft() {
  if (!state.config) return;
  if (state.formDirty && !applyEditor({quiet: true})) return;
  setStatus("Validating and saving configuration...");
  node("#tools-save").disabled = true;
  try {
    const payload = await saveTools(state.filename, state.config, state.revision);
    finishSave(payload);
  } catch (error) {
    if (error.message.toLowerCase().includes("changed on disk")) {
      await reconcileAndSave();
      return;
    }
    setStatus(error.message, true);
    renderSaveState();
  }
}

async function reconcileAndSave() {
  try {
    const latest = await getTools(state.filename);
    const {value, conflicts} = mergeDraft(state.original, state.config, latest.config);
    state.config = value;
    state.original = clone(latest.config);
    state.revision = latest.revision;
    state.dependencies = dependencyMap(latest.resources);
    state.dirty = true;
    state.formDirty = false;
    if (conflicts.length) {
      renderAll();
      renderAudit(latest.audit);
      setStatus(`The file changed on disk. External changes were merged, but ${conflicts.length} conflicting field(s) keep your draft value. Review the draft and Save again to confirm.`, true);
      return;
    }
    const payload = await saveTools(state.filename, state.config, state.revision);
    finishSave(payload, "Configuration updated with external changes and saved. The previous version is available as a .bak file.");
  } catch (error) {
    setStatus(error.message, true);
    renderSaveState();
  }
}

function finishSave(payload, message = "Configuration saved. The previous version is available as a .bak file.") {
  state.config = clone(payload.config);
  state.original = clone(payload.config);
  state.revision = payload.revision;
  state.dependencies = dependencyMap(payload.resources);
  state.dirty = false;
  state.formDirty = false;
  renderAll();
  renderAudit(payload.audit);
  setStatus(message);
  window.dispatchEvent(new CustomEvent("helper:tools-updated"));
}

function mergeDraft(base, local, remote) {
  const missing = Symbol("missing");
  const conflicts = [];
  const equal = (left, right) => left === missing || right === missing
    ? left === right
    : JSON.stringify(left) === JSON.stringify(right);
  const merge = (baseValue, localValue, remoteValue, path) => {
    if (equal(localValue, baseValue)) return remoteValue === missing ? missing : clone(remoteValue);
    if (equal(remoteValue, baseValue) || equal(localValue, remoteValue)) return localValue === missing ? missing : clone(localValue);
    const setLikeList = path === "refGenomes_list" || path.startsWith("tools.") || path.startsWith("databases.");
    if (setLikeList && [baseValue, localValue, remoteValue].every((value) => Array.isArray(value) && value.every((item) => typeof item === "string"))) {
      const baseSet = new Set(baseValue);
      const localSet = new Set(localValue);
      const remoteSet = new Set(remoteValue);
      const retained = baseValue.filter((item) => localSet.has(item) && remoteSet.has(item));
      const additions = [...localValue, ...remoteValue].filter((item) => !baseSet.has(item));
      return [...new Set([...retained, ...additions])];
    }
    const objects = [baseValue, localValue, remoteValue].every((value) => value === missing || (value && typeof value === "object" && !Array.isArray(value)));
    if (objects) {
      const result = {};
      const keys = new Set([
        ...Object.keys(baseValue === missing ? {} : baseValue),
        ...Object.keys(localValue === missing ? {} : localValue),
        ...Object.keys(remoteValue === missing ? {} : remoteValue),
      ]);
      for (const key of keys) {
        const merged = merge(
          baseValue !== missing && Object.hasOwn(baseValue, key) ? baseValue[key] : missing,
          localValue !== missing && Object.hasOwn(localValue, key) ? localValue[key] : missing,
          remoteValue !== missing && Object.hasOwn(remoteValue, key) ? remoteValue[key] : missing,
          path ? `${path}.${key}` : key,
        );
        if (merged !== missing) result[key] = merged;
      }
      return result;
    }
    conflicts.push(path || "configuration");
    return localValue === missing ? missing : clone(localValue);
  };
  return {value: merge(base, local, remote, ""), conflicts};
}

function discardDraft() {
  if (!state.dirty && !state.formDirty) return;
  if (!window.confirm("Discard all unsaved tool configuration changes?")) return;
  loadFile(state.filename);
}

function renderSaveState() {
  const changed = state.dirty || state.formDirty;
  const status = node("#tools-save-state");
  status.textContent = state.formDirty ? "Resource form not applied" : state.dirty ? "Unsaved changes" : state.config ? "Saved" : "No configuration loaded";
  status.classList.toggle("dirty", changed);
  node("#tools-save").disabled = !state.config || !changed;
  node("#tools-discard").disabled = !state.config || !changed;
}

function renderDependencies(name) {
  const target = node("#tools-dependencies");
  const dependencies = state.dependencies[name] || [];
  target.textContent = dependencies.length ? `Used by: ${dependencies.join(", ")}` : "Not referenced by saved pipelines.";
}

function syncCapabilities(oldName, newName, selected) {
  const selectedSet = new Set(selected);
  for (const category of categories()) {
    const values = state.config.tools[category] || [];
    const cleaned = values.filter((item) => item !== oldName && item !== newName);
    if (newName && selectedSet.has(category)) cleaned.push(newName);
    state.config.tools[category] = cleaned;
  }
}

function checkedCapabilities() {
  return [...node("#tools-capability-grid").querySelectorAll("input:checked")].map((input) => input.value);
}

function resourceNames(type) {
  if (type === "tool") return state.config.tools.list;
  if (type === "database") return state.config.databases.list;
  return state.config.refGenomes_list;
}

function allNames() {
  return ["tool", "database", "reference"].flatMap(resourceNames);
}

function resourceEntry(name) {
  const entry = state.config?.[name];
  return entry && typeof entry === "object" && !Array.isArray(entry) ? entry : {};
}

function categories() {
  return state.categoryNames;
}

function capabilitiesFor(name) {
  if (!name || !state.config) return [];
  return categories().filter((category) => (state.config.tools[category] || []).includes(name));
}

function resourceStatus(type, entry) {
  if (type === "reference") return entry.fasta ? "ready" : "incomplete";
  const container = containerValue(entry.container);
  return entry.path || container.image || entry.path_optional ? "ready" : "incomplete";
}

function containerValue(value) {
  if (typeof value === "string") return {engine: value ? "docker" : "local", image: value};
  if (value && typeof value === "object") return {engine: value.engine || "docker", image: value.image || ""};
  return {engine: "local", image: ""};
}

function dependencyMap(resources) {
  const result = {};
  for (const items of Object.values(resources || {})) {
    for (const item of items) result[item.name] = item.dependencies || [];
  }
  return result;
}

function humanize(value) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function option(value, label) {
  const item = document.createElement("option");
  item.value = value;
  item.textContent = label;
  return item;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function setStatus(message, error = false) {
  const status = node("#tools-status");
  status.textContent = message;
  status.classList.toggle("error", error);
}
