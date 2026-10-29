/* Presentation of recorded Engine decisions. No strength or eligibility calculation. */
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
const show = value => value === undefined || value === null ? "NOT_RECORDED" : typeof value === "object" ? JSON.stringify(value) : String(value);
const parsed = value => { try { return JSON.parse(value); } catch { return value ?? null; } };
const details = (label, value) => {
  const box = el("details"); box.append(el("summary", label), el("pre", JSON.stringify(value ?? null, null, 2))); return box;
};

export function mechanismPolicy(profile) {
  return profile?.criteria?.find(c => c.code === "PVS1")?.rules?.find(r => r.pvs1_policy)?.pvs1_policy?.mechanism_confidence_policy || "STANDARD";
}

export function mechanismPolicySelect() {
  const select = el("select"); select.setAttribute("aria-label", "Mechanism policy");
  ["STANDARD", "HELPER_EXPERIMENTAL_1.0"].forEach(value => { const option = el("option", value); option.value = value; select.append(option); });
  return select;
}

export function pvs1Result(criterion = {}) {
  criterion = criterion || {};
  const evaluation = criterion.pvs1_evaluation;
  return {status: evaluation?.status ?? criterion.activation_status ?? criterion.status,
    strength: evaluation ? evaluation.applied_strength : criterion.assigned_strength ?? criterion.strength,
    reason: evaluation?.reason ?? criterion.rationale ?? criterion.explanation,
    warnings: [...(criterion.warnings || []), ...(evaluation?.warnings || [])]};
}

export function appendPvs1Summary(host, evaluation, assessment, criterion = {}) {
  if (!evaluation && !assessment) return;
  const box = el("div", undefined, "acmg-pvs1-summary");
  if (evaluation) {
    const result = pvs1Result({...criterion, pvs1_evaluation: evaluation});
    box.append(el("p", `PVS1 ${show(result.status)} · strength ${result.strength === null ? "none" : show(result.strength)}`,
      result.status === "EXPLORATORY" ? "acmg-warning pvs1-exploratory" : "acmg-pvs1-state"));
    box.append(el("p", show(result.reason)));
    result.warnings.forEach(warning => box.append(el("p", show(warning), "acmg-warning")));
    if (evaluation.requires_review === true) box.append(el("p", "Review requested by Engine", "acmg-warning"));
    box.append(details("PVS1 source evidence and provenance", {sources: parsed(evaluation.source_evidence_json), provenance: parsed(evaluation.provenance_json)}),
      details("PVS1 thresholds, observed values and decision trace", {compared_values: criterion.compared_values,
        applied_thresholds: criterion.applied_thresholds, rules: criterion.rules, decision_trace: evaluation.decision_trace}),
      details("Full PVS1 Engine decision", evaluation));
  } else box.append(el("p", "PVS1 Engine decision: NOT_RECORDED"));
  if (assessment) {
    box.append(details("HELPER biological assessment, supporting/conflicting sources and provenance (automatic)", assessment));
  }
  host.append(box);
}
