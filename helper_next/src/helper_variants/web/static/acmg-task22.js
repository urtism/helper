/* Task 22 renderer: all scientific results, paths and comparisons originate in the engine. */
import {schemaField} from "./acmg-schema-field.js";
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
const show = v => v == null ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v);
const opt = (v, label = v) => { const n = el("option", label); n.value = v; return n; };
const details = (label, value) => { const n = el("details"); n.append(el("summary", label), el("pre", JSON.stringify(value, null, 2))); return n; };
async function api(path, payload) {
  const r = await fetch(`/api/acmg${path}`, payload === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
  const value = await r.json();
  if (!r.ok) throw new Error(typeof value.detail === "string" ? value.detail : JSON.stringify(value.detail || value));
  return value;
}

export function decisionGraph(bundle, inspect) {
  const host = el("div", undefined, "acmg-decision-graph");
  const toolbar = el("div", undefined, "acmg-actions");
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg"); svg.setAttribute("role", "group"); svg.setAttribute("aria-label", `${bundle.tree.criterion} decision tree`);
  const nodes = bundle.tree.nodes, records = new Map(bundle.trace.records.map(r => [r.node_id, r]));
  // Graph layout only; path/outcome and terminal identity come from the trace.
  const depth = new Map([[bundle.tree.root_node, 0]]), pending = [bundle.tree.root_node];
  while (pending.length) {
    const id = pending.shift(), n = nodes.find(n => n.node_id === id);
    for (const edge of n.next_nodes) if (!depth.has(edge.next_node)) { depth.set(edge.next_node, depth.get(id) + 1); pending.push(edge.next_node); }
  }
  const columns = new Map(), positions = new Map();
  nodes.forEach(n => { const d = depth.get(n.node_id) || 0; const row = columns.get(d) || 0; columns.set(d, row + 1); positions.set(n.node_id, {x: d * 290 + 20, y: row * 95 + 20}); });
  const width = (Math.max(...columns.keys()) + 1) * 290, height = Math.max(...columns.values()) * 95 + 30;
  let view = [0, 0, width, height];
  const apply = () => svg.setAttribute("viewBox", view.join(" "));
  const button = (label, action) => { const b = el("button", label); b.type = "button"; b.onclick = action; toolbar.append(b); };
  button("Zoom +", () => { view[2] *= .8; view[3] *= .8; apply(); });
  button("Zoom −", () => { view[2] /= .8; view[3] /= .8; apply(); });
  button("Fit to view", () => { view = [0, 0, width, height]; apply(); });
  let drag = null;
  svg.onpointerdown = e => { if (e.target === svg || e.target.tagName === "path") { drag = {x: e.clientX, y: e.clientY, view: [...view]}; svg.setPointerCapture(e.pointerId); } };
  svg.onpointermove = e => { if (drag) { const scale = Math.max(view[2] / svg.clientWidth, view[3] / svg.clientHeight); view[0] = drag.view[0] - (e.clientX - drag.x) * scale; view[1] = drag.view[1] - (e.clientY - drag.y) * scale; apply(); } };
  svg.onpointerup = svg.onpointercancel = () => { drag = null; };
  for (const node of nodes) for (const edge of node.next_nodes) {
    const a = positions.get(node.node_id), b = positions.get(edge.next_node), p = document.createElementNS(ns, "path");
    p.setAttribute("d", `M${a.x + 250},${a.y + 35} C${a.x + 275},${a.y + 35} ${b.x - 25},${b.y + 35} ${b.x},${b.y + 35}`);
    p.setAttribute("class", records.get(node.node_id)?.selected_next_node === edge.next_node && records.get(node.node_id)?.outcome === edge.outcome ? "executed-edge" : "skipped-edge");
    const title = document.createElementNS(ns, "title"); title.textContent = `${node.node_id} → ${edge.next_node}: ${edge.outcome}`; p.append(title); svg.append(p);
  }
  for (const node of nodes) {
    const record = records.get(node.node_id), pos = positions.get(node.node_id), g = document.createElementNS(ns, "g");
    g.setAttribute("transform", `translate(${pos.x} ${pos.y})`); g.setAttribute("role", "button"); g.setAttribute("tabindex", "0");
    g.setAttribute("aria-label", `${node.node_id} ${record?.outcome || "NOT_RECORDED"}`);
    g.setAttribute("class", `decision-node ${record?.executed ? "executed" : "skipped"} ${["UNKNOWN", "INVALID", "ERROR", "CONFLICT"].includes(record?.outcome) ? "problem" : ""} ${node.node_id === bundle.trace.terminal_node ? "terminal" : ""}`);
    const rect = document.createElementNS(ns, "rect"); rect.setAttribute("width", "250"); rect.setAttribute("height", "70"); rect.setAttribute("rx", "6"); g.append(rect);
    [node.node_id, `${node.node_type} · ${record?.outcome || "NOT_RECORDED"}`].forEach((line, i) => { const text = document.createElementNS(ns, "text"); text.setAttribute("x", "8"); text.setAttribute("y", String(23 + i * 24)); text.textContent = line.length > 35 ? line.slice(0, 32) + "…" : line; g.append(text); });
    const title = document.createElementNS(ns, "title"); title.textContent = node.description; g.append(title);
    g.onclick = () => inspect(node.node_id); g.onkeydown = e => { if (["Enter", " "].includes(e.key)) { e.preventDefault(); inspect(node.node_id); } }; svg.append(g);
  }
  apply(); host.append(toolbar, el("p", "Green: executed · Grey: skipped · Amber: unresolved/error · Blue border: terminal. Drag the background to pan; select a node for its recorded values."), svg); return host;
}

export async function mountTask22(host, workspace, discovery, status) {
  host.replaceChildren(el("h4", "2. ACMG criteria review · Task 22"));
  const config = el("div", undefined, "acmg-config"), protocol = el("select"); protocol.setAttribute("aria-label", "Criteria protocol");
  discovery.protocols.forEach((m, i) => protocol.append(opt(String(i), `${m.selection.protocol} · ${m.selection.version} · EXPERIMENTAL_NOT_CLINICALLY_APPROVED`)));
  const metadata = el("div"); let resetOverride = () => {};
  const metadataChanged = () => { metadata.replaceChildren(details("Protocol sources, approval and limitations", discovery.protocols[Number(protocol.value)])); resetOverride(); };
  protocol.onchange = metadataChanged; metadataChanged(); config.append(protocol); host.append(config, metadata);
  host.append(details("Original VCF annotations and ClinVar source evidence", workspace.document.original_vcf_evidence),
              details("Adapted snapshot and missing prerequisites", workspace.document.normalized_evidence));
  const warning = el("p", "Task 22 returns criterion status and strength. No final classification is produced.", "acmg-warning"); host.append(warning);
  const override = el("select"); override.setAttribute("aria-label", "Explicit VCEP tree override"); override.append(opt("", "No VCEP tree override"));
  const ctx = workspace.document.normalized_evidence.snapshot.context, same = (a, b) => a && b && a.namespace === b.namespace && a.identifier === b.identifier;
  (discovery.tree_overrides || []).forEach((record, i) => {
    const d = record.definition, scope = d.scope, gd = ctx.gene_disease;
    const compatible = same(ctx.gene, scope.gene) && same(ctx.disease, scope.disease) && gd?.inheritance_modes.includes(scope.inheritance) && same(gd?.mechanism?.term, scope.mechanism) && scope.transcripts.every(t => ctx.transcripts.some(c => JSON.stringify(c) === JSON.stringify(t)));
    const o = opt(String(i), `${d.profile_id}@${d.version} · ${d.release_status}${compatible ? "" : " · incompatible context"}`); o.disabled = !compatible || d.release_status === "RETIRED"; override.append(o);
  });
  resetOverride = () => { override.value = ""; override.disabled = discovery.protocols[Number(protocol.value)].selection.protocol !== "CLINGEN_GENERAL"; };
  resetOverride(); config.append(override);
  if (discovery.tree_override_discovery?.status === "UNAVAILABLE") host.append(el("p", `VCEP catalog unavailable: ${discovery.tree_override_discovery.code}. Available VCEP profiles could not be verified.`, "acmg-warning"));
  else if (!(discovery.tree_overrides || []).length) host.append(el("p", "No VCEP tree overrides are registered by this engine. A legacy gene profile is not an observable Task 22 override."));
  else host.append(details("VCEP scope, source and approval records", discovery.tree_overrides));
  const editor = el("details"), editChoice = el("select"), editHost = el("div"), pendingHost = el("div"), corrections = [];
  editor.append(el("summary", "Add or correct structured evidence")); editChoice.setAttribute("aria-label", "Evidence to edit");
  editChoice.append(opt("", "Select evidence"), opt("new:POPULATION", "New population observation"), opt("new:COMPUTATIONAL", "New computational prediction"));
  workspace.document.normalized_evidence.snapshot.evidence.forEach((e, i) => { if (["POPULATION", "COMPUTATIONAL"].includes(e.kind)) editChoice.append(opt(String(i), `Correct ${e.id} (${e.kind})`)); });
  editor.append(el("p", "Typed controls use the live Task 22 schema. This initial editor supports population and computational observations; other evidence families require a complete validated provider envelope through the API. Source versions and a reason are required; quality and verification are not promoted."), editChoice, editHost, pendingHost); host.append(editor);
  const showPending = () => {
    pendingHost.replaceChildren(details("Pending evidence changes (applied to the next execution)", corrections));
    corrections.forEach((c, i) => { const b = el("button", `Remove ${c.value.id}`); b.type = "button"; b.onclick = () => { corrections.splice(i, 1); showPending(); }; pendingHost.append(b); });
  };
  editChoice.onchange = () => {
    editHost.replaceChildren(); if (!editChoice.value) return;
    const original = editChoice.value.startsWith("new:") ? null : workspace.document.normalized_evidence.snapshot.evidence[Number(editChoice.value)];
    const kind = original?.kind || editChoice.value.split(":")[1];
    const initial = original ? structuredClone(original) : {kind, provenance: {acquired_at: new Date().toISOString(), extraction_method: "MANUAL", verification_status: "UNVERIFIED", software_version: "helper-task23-1.0"}};
    initial.provenance.extraction_method = "MANUAL"; initial.provenance.verification_status = "UNVERIFIED"; initial.provenance.acquired_at = new Date().toISOString(); initial.provenance.software_version = "helper-task23-1.0"; delete initial.provenance.verification;
    const definition = discovery.contract_schema.$defs[kind === "POPULATION" ? "PopulationEvidence" : "ComputationalEvidence"];
    const field = schemaField(definition, discovery.contract_schema, initial, `${kind} evidence`), comment = el("textarea"), add = el("button", "Stage evidence change");
    comment.placeholder = "Reason for this correction or additional evidence"; comment.setAttribute("aria-label", "Evidence correction reason"); add.type = "button";
    add.onclick = () => { try { if (!comment.value.trim()) throw new Error("Record a reason for this change"); const change = {value: field.read(), replaces: original?.id || null, comment: comment.value}; const index = corrections.findIndex(c => (change.replaces && c.replaces === change.replaces) || c.value.id === change.value.id); if (index < 0) corrections.push(change); else corrections[index] = change; showPending(); editHost.replaceChildren(); editChoice.value = ""; } catch (e) { status.textContent = e.message; } };
    editHost.append(field.host, comment, add);
  };
  const actions = el("div", undefined, "acmg-actions"), preflight = el("button", "Inspect evidence requirements"), run = el("button", "Evaluate selected variant"), compare = el("button", "Compare ACMG 2015 / ClinGen");
  run.className = "acmg-primary"; actions.append(preflight, run, compare); host.append(actions);
  const readiness = el("div"), results = el("div"), history = el("div"); host.append(readiness, results, history);
  let selected = null, savedHistory = [], updateMatrix = () => {};
  const request = () => ({protocol: discovery.protocols[Number(protocol.value)].selection, parent_id: selected?.kind === "criteria_evaluation" ? selected.id : "", corrections, node_specializations: override.value === "" ? [] : [discovery.tree_overrides[Number(override.value)].reference]});
  let working = false;
  const busy = async fn => { if (working) return; working = true; preflight.disabled = run.disabled = compare.disabled = true; status.textContent = "Working on the selected variant…"; try { await fn(); status.textContent = "Ready · research only"; } catch (e) { status.textContent = e.message; } finally { working = false; preflight.disabled = false; run.disabled = compare.disabled = !discovery.capabilities.research_execution_enabled; } };
  preflight.onclick = () => busy(async () => { const value = await api(`/workspaces/${workspace.id}/criteria/preflight`, request()); readiness.replaceChildren(details("Engine evidence assessments", value.validated.assessments), details("Evidence requirements and branch readiness", value.requirements)); readiness.firstChild.open = true; });
  run.disabled = compare.disabled = !discovery.capabilities.research_execution_enabled;
  if (run.disabled) host.append(el("p", "Enable ACMG_ENABLE_RESEARCH_INTERPRETATION on the engine to evaluate this variant.", "acmg-warning"));
  run.onclick = () => busy(async () => { const result = await api(`/workspaces/${workspace.id}/criteria/evaluate`, request()); await renderResult(result); await refreshHistory(); });
  compare.onclick = () => busy(async () => { const result = await api(`/workspaces/${workspace.id}/criteria/compare`, request()); renderComparison(result); await refreshHistory(); });
  async function renderResult(result) {
    selected = result;
    corrections.splice(0, corrections.length, ...(result.document.corrections || [])); showPending();
    const matrix = result.document.engine_result;
    results.replaceChildren(el("h4", `${matrix.protocol.protocol} ${matrix.protocol.version} · attempt ${result.id}`), el("p", matrix.limitations.join(" ")));
    const downloads = el("div", undefined, "acmg-actions");
    ["engine", "audit", "csv"].forEach(format => { const a = el("a", `Export ${format}`); a.href = `/api/acmg/results/${result.id}/criteria/export/${format}`; a.download = ""; downloads.append(a); }); results.append(downloads);
    const filters = el("div", undefined, "acmg-actions"), statusFilter = el("select"), strengthFilter = el("select"), typeFilter = el("select");
    statusFilter.setAttribute("aria-label", "Filter criterion status"); strengthFilter.setAttribute("aria-label", "Filter strength"); typeFilter.setAttribute("aria-label", "Filter criterion type");
    statusFilter.append(opt("", "All statuses")); [...new Set(matrix.criteria.map(c => c.activation_status))].forEach(s => statusFilter.append(opt(s)));
    strengthFilter.append(opt("", "All strengths"), opt("NONE", "No assigned strength")); [...new Set(matrix.criteria.map(c => c.assigned_strength?.level).filter(Boolean))].forEach(s => strengthFilter.append(opt(s)));
    typeFilter.append(opt("", "All criteria"), opt("P", "Pathogenic"), opt("B", "Benign")); filters.append(statusFilter, strengthFilter, typeFilter); results.append(filters);
    const tableHost = el("div", undefined, "acmg-table-scroll"), inspector = el("div", undefined, "acmg-inspector"); results.append(tableHost, inspector);
    const renderTable = () => {
      const table = el("table"), head = el("tr"); ["Criterion", "Status", "Strength", "Protocol / rule version", "Evidence used", "Observed", "Threshold", "Rationale", "Warnings / review"].forEach(s => head.append(el("th", s))); table.append(head);
      matrix.criteria.filter(c => (!statusFilter.value || c.activation_status === statusFilter.value) && (!strengthFilter.value || (c.assigned_strength?.level || "NONE") === strengthFilter.value) && (!typeFilter.value || c.criterion_id.startsWith(typeFilter.value))).forEach(c => {
        const row = el("tr"), td = el("td"), button = el("button", c.criterion_id); button.onclick = () => busy(() => inspect(c, result, inspector)); td.append(button); row.append(td);
        const review = savedHistory.filter(e => e.kind === "criteria_review" && e.document.result_id === result.id && e.document.criterion === c.criterion_id).at(-1);
        [c.activation_status, c.assigned_strength, `${c.rule.protocol.protocol} / ${c.rule.version}${c.rule.scientific_basis === "RETIRED" ? " · RETIRED" : ""}`, c.input_evidence_used, c.compared_values, c.applied_thresholds, c.rationale, {warnings: c.warnings, missing: c.missing_evidence, exclusions: c.exclusion_reasons, manual_review: review?.document.decision || "UNREVIEWED"}].forEach(v => row.append(el("td", show(v)))); table.append(row);
      }); tableHost.replaceChildren(table);
    }; updateMatrix = renderTable; statusFilter.onchange = strengthFilter.onchange = typeFilter.onchange = renderTable; renderTable();
    results.append(details("Engine requirements and availability", matrix.requirements));
  }
  async function inspect(criterion, result, target) {
    const bundles = await api(`/results/${result.id}/criteria/artifacts`), bundle = bundles[criterion.criterion_id];
    target.replaceChildren(el("h4", `${criterion.criterion_id} · ${criterion.activation_status}`), el("p", criterion.rule.original_definition),
      details("Rule, thresholds, used evidence and scientific references", criterion));
    if (!bundle) { const retry = el("button", "Save replay bundles"); retry.onclick = () => busy(async () => { await api(`/results/${result.id}/criteria/archive`, {}); await inspect(criterion, result, target); }); target.append(el("p", "Actual tree is not archived. The engine must still have this execution in memory."), retry); return; }
    const nodeHost = el("div", undefined, "acmg-node-inspector");
    const inspectNode = id => busy(async () => {
      const value = await api(`/results/${result.id}/criteria/${criterion.criterion_id}/nodes/${encodeURIComponent(id)}`);
      nodeHost.replaceChildren(el("h5", `Node ${id} · ${value.execution.executed ? value.execution.outcome : "SKIPPED · not executed"}`),
        details("Scientific definition, condition, operator and reference", value.definition),
        details("Recorded observation, formula, threshold, result and selected branch", value.execution),
        details("Original and normalized evidence with source provenance", value.evidence_values));
      [...nodeHost.children].filter(n => n.tagName === "DETAILS").forEach(n => { n.open = true; });
    });
    const trace = el("ol"); bundle.trace.execution_path.forEach(id => { const row = el("li"), b = el("button", `${id} · ${bundle.trace.records.find(r => r.node_id === id).outcome}`); b.onclick = () => inspectNode(id); row.append(b); trace.append(row); });
    target.append(decisionGraph(bundle, inspectNode), nodeHost, el("h5", `Execution order · ${bundle.trace.execution_id} · ${bundle.trace.stage}`), trace,
      details("Dependency executions", bundle.dependency_traces), details("Full engine trace including skipped nodes", bundle.trace));
    const firstDemand = bundle.trace.records.find(r => r.executed && r.missing_evidence.length);
    if (firstDemand) target.append(details(`First executed node reporting missing evidence: ${firstDemand.node_id}`, firstDemand));
    const review = el("form", undefined, "acmg-review"), decision = el("select"), revisedStatus = el("select"), strength = el("select"), reviewer = el("input"), rationale = el("textarea");
    decision.setAttribute("aria-label", "Manual review action"); ["CONFIRM", "REQUEST_REVIEW", "CONTEST", "MANUAL_DECISION"].forEach(s => decision.append(opt(s)));
    revisedStatus.setAttribute("aria-label", "Reviewed criterion status"); ["ACTIVE", "INACTIVE", "NOT_EVALUABLE", "NOT_APPLICABLE", "CONFLICTING_EVIDENCE", "REQUIRES_REVIEW"].forEach(s => revisedStatus.append(opt(s)));
    strength.setAttribute("aria-label", "Reviewed strength"); criterion.rule.permitted_strengths.forEach(s => strength.append(opt(s)));
    const updateReview = () => { revisedStatus.hidden = decision.value !== "MANUAL_DECISION"; strength.hidden = revisedStatus.hidden || revisedStatus.value !== "ACTIVE"; }; decision.onchange = revisedStatus.onchange = updateReview; updateReview();
    reviewer.placeholder = "Reviewer identifier (local attribution)"; reviewer.required = true; reviewer.setAttribute("aria-label", "Reviewer identifier"); rationale.placeholder = "Reason for review"; rationale.required = true; rationale.setAttribute("aria-label", "Review rationale");
    const save = el("button", "Save separate manual review"); save.type = "submit"; review.append(decision, revisedStatus, strength, reviewer, rationale, save);
    review.onsubmit = event => { event.preventDefault(); busy(async () => { await api(`/results/${result.id}/criteria/reviews`, {criterion: criterion.criterion_id, decision: decision.value, reviewer_id: reviewer.value, rationale: rationale.value,
      revised_status: decision.value === "MANUAL_DECISION" ? revisedStatus.value : null,
      revised_strength: decision.value === "MANUAL_DECISION" && revisedStatus.value === "ACTIVE" ? {direction: criterion.criterion_id.startsWith("B") ? "BENIGN" : "PATHOGENIC", level: strength.value} : null}); await inspect(criterion, result, target); await refreshHistory(); }); };
    const reviews = (await api(`/workspaces/${workspace.id}`)).history.filter(e => e.kind === "criteria_review" && e.document.result_id === result.id && e.document.criterion === criterion.criterion_id);
    target.append(review, details("Manual reviews (automatic result unchanged)", reviews));
  }
  function renderComparison(result) {
    selected = result; updateMatrix = () => {}; const comparison = result.document.engine_result;
    results.replaceChildren(el("h4", "Same validated evidence · ACMG 2015 / ClinGen"));
    ["engine", "audit", "csv"].forEach(format => { const a = el("a", `Export ${format}`); a.href = `/api/acmg/results/${result.id}/criteria/export/${format}`; a.download = ""; results.append(a); });
    const table = el("table"), header = el("tr"); ["Criterion", "Protocol A", "Protocol B", "Engine differences / first divergence"].forEach(s => header.append(el("th", s))); table.append(header);
    comparison.differences.forEach(d => {
      const row = el("tr"); row.append(el("th", d.criterion));
      comparison.results.forEach(matrix => { const c = matrix.criteria.find(c => c.criterion_id === d.criterion), td = el("td"); td.append(details(`${matrix.protocol.protocol} · ${c.activation_status} · ${show(c.assigned_strength)}`, {status: c.activation_status, strength: c.assigned_strength, rule: c.rule.rule_id, rule_version: c.rule.version, thresholds: c.applied_thresholds, observed: c.compared_values, tree_id: c.execution.tree_id, tree_version: c.execution.tree_version, rationale: c.rationale, requirements: matrix.requirements.requirements.find(r => r.criterion === d.criterion), trace: c.execution})); row.append(td); });
      const td = el("td"); td.append(details(d.activation_differs || d.strength_differs || d.thresholds_differ || d.requirements_differ ? "Different" : "Inspect rule/path differences", d)); row.append(td); table.append(row);
    }); const scroll = el("div", undefined, "acmg-table-scroll"); scroll.append(table); results.append(scroll);
  }
  async function refreshHistory() {
    const value = await api(`/workspaces/${workspace.id}`); savedHistory = value.history; updateMatrix(); history.replaceChildren(el("h4", "Saved criterion evaluations"));
    value.history.filter(e => ["criteria_evaluation", "criteria_comparison"].includes(e.kind)).forEach(e => {
      const b = el("button", `${e.created_at} · ${e.document.engine_result.protocol?.protocol || "Protocol comparison"} · ${e.id.slice(0, 12)}`); b.onclick = () => busy(async () => { if (e.kind === "criteria_comparison") renderComparison(e); else await renderResult(e); await refreshHistory(); }); history.append(b);
      if (selected?.kind === "criteria_evaluation" && e.kind === "criteria_evaluation" && selected.id !== e.id) {
        const diff = el("button", "Compare evidence and results"); diff.onclick = () => busy(async () => {
          const value = await api(`/results/${selected.id}/criteria/diff/${e.id}`), box = details("Before / after (engine results preserved)", value); box.open = true; results.append(box);
          const criterion = el("select"); value.criteria.forEach(c => criterion.append(opt(c.criterion))); const trace = el("button", "Ask engine for first trace divergence");
          trace.onclick = () => busy(async () => { const comparison = await api(`/results/${selected.id}/criteria/trace-compare/${e.id}/${criterion.value}`, {}); results.append(details("Engine trace comparison (requires executions in engine memory)", comparison.document.engine_result)); }); results.append(criterion, trace);
        }); history.append(diff);
      }
    });
  }
  await refreshHistory();
}
