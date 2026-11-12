// New PVS1-only Calculator. No legacy engine/workbench API is called here.
const element = (tag, text, className = "") => {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
};

const frameLabel = value => ({IN_FRAME: "In frame", OUT_OF_FRAME: "Out of frame"})[value] || "Non determinato";
const nmdLabel = value => value == null ? "Non determinabile" : value ? "Previsto" : "Non previsto";
const inheritanceLabel = value => ({AUTOSOMAL_DOMINANT: "Dominante (AD)", AUTOSOMAL_RECESSIVE: "Recessiva (AR)",
  X_LINKED: "Legata all'X", Y_LINKED: "Legata all'Y", MITOCHONDRIAL: "Mitocondriale"})[value] || value;
const indicatorLabel = value => ({NO_EVIDENCE: "Nessuna evidenza", LITTLE_EVIDENCE: "Evidenze limitate",
  SOME_EVIDENCE: "Evidenze parziali", SUFFICIENT_EVIDENCE: "Evidenze sufficienti", RECESSIVE_DISEASE: "Malattia recessiva",
  DOSAGE_UNLIKELY: "Sensibilità al dosaggio improbabile", HIGH_LOF_INTOLERANCE: "Intolleranza LoF predetta",
  NO_HIGH_LOF_INTOLERANCE: "Intolleranza LoF elevata non rilevata", UNAVAILABLE: "Non disponibile"})[value] || value;
const indicatorValue = item => item.value == null ? "Non disponibile" : item.metric === "HI" ? String(item.value)
  : Number(item.value.toPrecision(4)).toString();
const indicatorIssueLabel = value => ({UNRESOLVED_GENE_MAPPING: "Collegamento al gene non verificato",
  MISSING_OR_INVALID_VALUE: "Valore assente o non valido", UNVERIFIED_RELEASE: "Release non documentata",
  UNAVAILABLE_CONSTRAINT: "Constraint non disponibile", MISSING_TRANSCRIPT: "Trascritto assente",
  TRANSCRIPT_NOT_SELECTED: "Isoforma non selezionata per la sintesi del gene", AMBIGUOUS_TRANSCRIPT: "Scelta del trascritto ambigua",
  UNVERIFIED_QUALITY: "Qualità non documentata", QUALITY_FLAGS: "Flag di qualità presenti",
  MISSING_OR_ZERO_EXPECTED_LOF: "Numero atteso di LoF assente o nullo"})[value] || value;

const summaryPercent = value => `${value.toFixed(2).replace(".", ",")}%`;
const strengthLabels = {VERY_STRONG: "Very Strong", STRONG: "Strong", MODERATE: "Moderate", SUPPORTING: "Supporting"};
const strengthLabel = value => strengthLabels[value] || "Non applicata";

function mechanismSummary(payload) {
  const context = payload.input.disease_context;
  const report = payload.mechanism_assessment || {};
  const mechanism = context.molecular_mechanism;
  const known = mechanism && mechanism !== "UNKNOWN";
  const status = context.confidence === "DISPUTED" ? "DISCORDANT"
    : known && context.confidence === "DEFINITIVE" ? "PROVEN"
      : known && context.confidence === "INFERRED" ? "INFERRED" : "UNKNOWN";
  const labels = {PROVEN: "Provato", INFERRED: "Inferito", DISCORDANT: "Discordante", UNKNOWN: "Unknown"};
  const scope = context.mechanism_scope || report.mechanism_scope || context.scope;
  const wrapper = element("span", undefined, "pvs1-mechanism");
  wrapper.dataset.mechanismStatus = status;
  wrapper.append(element("span", `${known ? `${mechanism} · ` : ""}${labels[status]}`));
  const information = element("span", undefined, "gene-association-summary");
  const button = element("button", ({PROVEN: "i", INFERRED: "⚠", DISCORDANT: "⚠", UNKNOWN: "?"})[status],
    "constraint-metric-information-button pvs1-mechanism-information");
  button.type = "button";
  button.setAttribute("aria-label", `Meccanismo ${labels[status]}: fonti`);
  button.setAttribute("aria-describedby", "pvs1-mechanism-tooltip");
  const tooltip = element("span", undefined, "gene-association-summary-tooltip");
  tooltip.id = "pvs1-mechanism-tooltip";
  tooltip.setAttribute("role", "tooltip");
  const primaryRefs = new Set((report.assertions || []).filter(assertion =>
    assertion.mechanism === report.mechanism && assertion.scope === scope,
  ).flatMap(assertion => assertion.supporting_evidence_refs || []));
  let evidence = (report.supporting_evidence || []).filter(item => primaryRefs.has(item.evidence_id));
  if (status === "DISCORDANT") evidence = [...evidence, ...(report.conflicting_evidence || [])];
  evidence = [...new Map(evidence.map(item => [item.evidence_id, item])).values()];
  const sources = {g2p: "G2P", gencc: "GenCC", clingen: "ClinGen", clingen_dosage: "ClinGen Dosage", gnomad: "gnomAD", clingen_vcep: "ClinGen VCEP"};
  evidence.forEach(item => {
    const raw = item.raw_assertion || {};
    const detail = raw.assessment === "haploinsufficiency" ? `HI=${raw.hi_score}`
      : item.source === "gnomad" ? `pLI=${raw.pli}` : item.source_record_id;
    const citation = [sources[item.source] || item.source, detail].filter(Boolean).join(" · ");
    const source = element("span");
    const url = raw.record_url || raw.report_url || raw.public_report_url || raw.source_url;
    if (url && /^https?:\/\//i.test(url)) {
      const link = element("a", citation);
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      source.append(link);
    } else source.append(element("span", citation));
    tooltip.append(source);
  });
  if (!evidence.length) {
    const citations = context.source_refs?.molecular_mechanism || [];
    citations.forEach(citation => {
      const prefix = "HELPER mechanism assessment ";
      if (citation.startsWith(prefix)) {
        try {
          const item = JSON.parse(citation.slice(prefix.length)).evidence;
          tooltip.append(element("span", `${sources[item.source] || item.source} · ${item.source_record_id}`));
        } catch { /* Unreadable citations remain available in the advanced trace. */ }
      } else tooltip.append(element("span", citation));
    });
    if (!tooltip.childElementCount) tooltip.append(element("span", "Nessuna fonte disponibile."));
  }
  information.append(button, tooltip);
  wrapper.append(information);
  return wrapper;
}

function exonSummary(payload, row, event, annotation) {
  const exons = row?.reference?.exons;
  const total = exons?.length || payload.input.transcript?.exon_genomic_intervals?.length;
  let involved = event?.involved_exons;
  const interval = row?.calculation?.mapping?.mrna_edit_interval;
  if (!involved?.length && exons && interval) {
    const [start, end] = interval;
    involved = exons.flatMap((exon, index) => (start === end
      ? exon.mrna_start - 1 < start && start < exon.mrna_end
      : exon.mrna_start - 1 < end && start < exon.mrna_end) ? [index + 1] : []);
  }
  if (involved?.length && involved.every(index => Number.isInteger(index) && index > 0 && (!total || index <= total))) {
    return `${involved.join(", ")} di ${total || "totale non disponibile"}`;
  }
  const annotated = String(annotation.metadata?.fields?.EXON || "").match(/^(\d+(?:-\d+)?)\/(\d+)$/);
  if (annotated && (!total || total === Number(annotated[2]))) return `${annotated[1].replace("-", "–")} di ${annotated[2]}`;
  return total ? `Non determinati · ${total} totali` : "Non determinati";
}

function lazyDisclosure(host, title, render, options = {}) {
  const body = element("div", undefined, "detail-content");
  const disclosure = host.detailDisclosure(title, body, options);
  disclosure.addEventListener("toggle", () => {
    if (disclosure.open && !body.childNodes.length) body.append(render());
  });
  return disclosure;
}

function molecularSummary(host, payload, annotation) {
  const row = payload.molecular_impact?.transcripts?.find(item => item.selected);
  const products = payload.input.molecular_effect?.products || [];
  const product = products.length === 1 ? products[0] : undefined;
  const scenarios = row?.splice_analysis?.scenarios || [];
  const scenario = scenarios.length === 1 ? scenarios[0] : undefined;
  const trace = (payload.result.decision_trace || []).map(raw => JSON.parse(raw));
  const nmd = row?.nmd_predicted ?? trace.find(item => item.id === "nmd")?.value?.predicted_nmd;
  const frame = product?.frame_effect || scenario?.frame_effect || row?.calculation?.frame?.frame_effect;
  const event = scenario?.event || product;
  const effect = payload.input.molecular_effect || {};
  const terms = (annotation.consequence || payload.input.variant.consequence || "").split("&");
  const consequences = {frameshift_variant: "Frameshift", stop_gained: "Stop prematuro", start_lost: "Perdita del codone di inizio",
    stop_lost: "Perdita del codone di stop", inframe_deletion: "Delezione in frame", inframe_insertion: "Inserzione in frame",
    missense_variant: "Missenso", synonymous_variant: "Sinonima"};
  const site = row?.splice_analysis?.site;
  const siteType = site?.type || effect.splice_site_type;
  const offsets = site?.affected_offsets || [effect.splice_site_offset];
  const nativeMotif = site?.native_motif || effect.native_splice_motif;
  const canonical = (siteType === "DONOR" && nativeMotif === "GT" && offsets.some(offset => offset === 1 || offset === 2))
    || (siteType === "ACCEPTOR" && nativeMotif === "AG" && offsets.some(offset => offset === -1 || offset === -2));
  const splice = siteType || terms.some(term => term.startsWith("splice_"));
  const codingType = consequences[terms.find(term => consequences[term])];
  const spliceType = `${canonical ? "Splice canonica" : "Splice"}${siteType ? ` · ${siteType === "DONOR" ? "donatore" : "accettore"}` : ""}`;
  const variantType = canonical ? spliceType : codingType ? `${codingType}${splice ? " · regione splice" : ""}`
    : splice ? spliceType : (annotation.consequence || "Non determinato").replaceAll("_", " ").replaceAll("&", " · ");
  let eventLabel = "Non determinato";
  if (products.length > 1 || scenarios.length > 1) eventLabel = "Prodotti multipli · vedi avanzate";
  else if (event?.event_type) eventLabel = ({EXON_SKIPPING: "Exon skipping", CRYPTIC_SITE: "Utilizzo di sito criptico", INTRON_RETENTION: "Ritenzione intronica"})[event.event_type] || "Non determinato";
  else if (product) eventLabel = product.ptc_start != null ? "Stop prematuro" : codingType || "Non determinato";
  const referenceLength = row?.reference_protein_length;
  const predictedLength = row?.predicted_protein_length;
  const shortening = referenceLength > 0 && predictedLength != null ? 100 * (referenceLength - predictedLength) / referenceLength : null;
  const proteinLabel = referenceLength != null || predictedLength != null
    ? `${referenceLength ?? "—"} / ${predictedLength ?? "—"} aa${shortening == null ? "" : ` (${summaryPercent(Math.abs(shortening))} ${shortening < 0 ? "in più" : "in meno"})`}` : "Non determinata";
  const cdsLength = row?.cds_length_nt;
  let cdsRemoved = scenario?.coding_deleted_nt;
  if (cdsRemoved == null && event?.event_type === "EXON_SKIPPING" && row?.reference?.exons && event.involved_exons?.length) {
    const ref = row.reference;
    cdsRemoved = event.involved_exons.reduce((sum, index) => {
      const exon = ref.exons[index - 1];
      return exon ? sum + Math.max(0, Math.min(exon.mrna_end, ref.cds_end) - Math.max(exon.mrna_start, ref.cds_start) + 1) : NaN;
    }, 0);
  } else if (cdsRemoved == null && !event?.event_type && (!splice || row?.calculation?.mapping)) cdsRemoved = row?.physical_deleted_nt;
  const cdsLabel = Number.isFinite(cdsRemoved) ? `${cdsRemoved}${cdsLength > 0 ? ` / ${cdsLength}` : ""} nt${cdsLength > 0 ? ` (${summaryPercent(100 * cdsRemoved / cdsLength)})` : " · percentuale non determinata"}` : "Non determinata";
  const summary = element("section", undefined, "pvs1-molecular-summary");
  summary.id = "new-acmg-molecular-summary";
  summary.append(element("h5", "Sintesi molecolare"));
  const cards = element("div", undefined, "detail-cards pvs1-summary-grid");
  cards.append(host.detailCard([
    ["Variante sul trascritto", (annotation.hgvsc || "—").replace(/^[^:]+:/, "")],
    ["Tipo di variante", variantType],
    [product?.basis === "PREDICTED" || scenario?.event?.basis === "PREDICTED" ? "Evento predetto" : "Evento", eventLabel],
    ["Esoni", exonSummary(payload, row, event, annotation)],
    ["Frame", frameLabel(frame)],
  ]));
  cards.append(host.detailCard([
    ["NMD", trace.find(item => item.id === "nmd")?.status === "NOT_APPLICABLE" ? "Non applicabile" : nmdLabel(nmd)],
    ["Meccanismo", mechanismSummary(payload)],
    ["Proteina reference / predetta", proteinLabel], ["CDS rimossa", cdsLabel],
  ]));
  summary.append(cards);
  if (row?.splice_analysis?.prediction?.selection_status === "EXPLORATORY_LOW_DELTA") {
    summary.append(element("p", "Scenario esplorativo: delta SpliceAI sotto soglia. Il prodotto prevalente non è determinato.", "detail-note"));
  }
  return summary;
}

export function renderTranscriptMolecularImpact(host, analysis) {
  const section = element("section", undefined, "transcript-molecular-impact");
  section.id = "transcript-molecular-impact";
  section.append(element("h4", "Transcript Molecular Impact"));
  const scope = analysis.scope === "SELECTED" ? "Trascritto selezionato" : `Catalogo ${analysis.catalog_complete ? "completo" : "incompleto"}`;
  section.append(element("p", `Gene ${analysis.gene || "—"} · ${analysis.assembly || "—"} · Ensembl ${analysis.release || "non documentata"} · ${scope}`, "detail-note"));
  section.append(element("p", "Analisi molecolare indipendente dalla decisione PVS1. Le percentuali descrivono la sequenza reference; NMD e prodotti proteici sono predetti.", "detail-note"));
  (analysis.warnings || []).forEach(warning => section.append(element("p", warning, "detail-note")));
  const viewport = element("div", undefined, "molecular-impact-viewport");
  const table = element("table");
  const head = element("thead"), headings = element("tr");
  ["Transcript", "Annotation", "CDS nt", "Position", "Frame", "CDS affected %", "Protein impact %", "NMD"].forEach(label => headings.append(element("th", label)));
  head.append(headings);
  const body = element("tbody");
  const percent = value => value == null ? "—" : `${value.toFixed(2)}%`;
  (analysis.transcripts || []).forEach((row, index) => {
    const tr = element("tr");
    tr.dataset.transcript = row.transcript;
    tr.dataset.status = row.status;
    if (row.selected) tr.setAttribute("aria-current", "true");
    const transcriptCell = element("td");
    const expand = element("button", `${row.transcript}${row.selected ? " · selezionato" : ""}`);
    expand.type = "button";
    expand.setAttribute("aria-expanded", "false");
    expand.setAttribute("aria-controls", `molecular-impact-detail-${index}`);
    transcriptCell.append(expand);
    const flags = [row.mane === "SELECT" ? "MANE Select" : row.mane === "PLUS_CLINICAL" ? "MANE Plus Clinical" : "", row.canonical ? "Canonical" : "", row.appris ? `APPRIS ${row.appris}` : ""].filter(Boolean);
    if (flags.length) transcriptCell.append(element("small", flags.join(" · ")));
    const affected = row.reference_cds_untranslated_percent != null ? `${percent(row.reference_cds_untranslated_percent)} non tradotta`
      : row.reference_cds_disrupted_percent != null ? `${percent(row.reference_cds_disrupted_percent)} frame alterato` : "—";
    const frames = [...new Set((row.splice_analysis?.scenarios || []).map(scenario => scenario.frame_effect).filter(Boolean))];
    const frame = row.splice_analysis ? (frames.length === 1 ? frames[0] : undefined) : row.calculation?.frame?.frame_effect;
    tr.append(transcriptCell, element("td", `${row.consequence || "—"} · ${row.status}${row.conditional ? " · condizionale" : ""}`),
      element("td", row.cds_length_nt ?? "—"), element("td", row.cds_position == null ? "—" : `c.${row.cds_position} · codone ${row.first_affected_reference_codon}`),
      element("td", frameLabel(frame)),
      element("td", affected), element("td", `${percent(row.protein_impact_percent)}${row.protein_impact_percent == null ? "" : " reference persa/alterata"}`),
      element("td", nmdLabel(row.nmd_predicted)));
    const details = element("tr"), detailCell = element("td");
    details.id = `molecular-impact-detail-${index}`;
    details.hidden = true;
    detailCell.colSpan = 8;
    details.append(detailCell);
    expand.addEventListener("click", () => {
      details.hidden = !details.hidden;
      expand.setAttribute("aria-expanded", String(!details.hidden));
      if (!details.hidden && !detailCell.childNodes.length) {
        const content = element("div", undefined, "detail-content");
        detailCell.append(content);
        content.append(host.detailCard([
          ["Prodotto molecolare", ({DETERMINED: "Determinato dalla sequenza", CONDITIONAL: "Condizionale", UNRESOLVED: "Non determinato", NOT_APPLICABLE: "Non applicabile"})[row.product_resolution?.status] || "—"],
          ["Ricostruzione", ({CODON_VERIFICATION: "Verifica dei codoni modificati", ALTERED_FRAME_TRANSLATION: "Traduzione dal codone modificato", CANONICAL_SPLICE_SCENARIO: "Scenario predetto di salto esonico", SPLICEAI_CRYPTIC_SCENARIO: "Scenario predetto da sito criptico SpliceAI"})[row.product_resolution?.method] || "—"],
          ["Biotype / strand", `${row.biotype || "—"} / ${row.strand || "—"}`],
          ["CDS tradotta reference (stop naturale escluso)", row.translated_cds_length_nt ?? "—"],
          ["Nucleotidi eliminati / inseriti", `${row.physical_deleted_nt ?? "—"} / ${row.physical_inserted_nt ?? "—"}`],
          ["CDS fisicamente eliminata", percent(row.physical_cds_deleted_percent)],
          ["Lunghezza proteina reference / predetta", `${row.reference_protein_length ?? "—"} / ${row.predicted_protein_length ?? "—"} aa`],
          ["Primo residuo divergente", row.first_divergent_aa ?? "—"],
          ["Residui reference persi / sostituiti", `${row.reference_amino_acids_lost ?? "—"} / ${row.reference_amino_acids_replaced ?? "—"}`],
          ["Accorciamento proteico predetto", row.predicted_protein_shortening_aa == null ? "—" : `${row.predicted_protein_shortening_aa} aa`],
          ["Nuovo stop / PTC", `codone ${row.termination_codon ?? "—"} · mRNA ${row.termination_mrna_position ?? "—"} · PTC ${row.ptc_mrna_position ?? "—"}`],
          ["Estensione nella 3′ UTR", row.extends_into_utr == null ? "—" : row.extends_into_utr ? "Sì" : "No"],
          ["Distanza stop–ultima giunzione", row.nmd_distance_nt == null ? "—" : `${row.nmd_distance_nt} nt`],
        ]));
        if (row.splice_analysis) {
          const site = row.splice_analysis.site;
          content.append(element("h4", "Scenario splice condizionale"));
          if (site) content.append(host.detailCard([
            ["Sito interessato", `${site.type === "DONOR" ? "Donatore" : "Accettore"} · esone ${site.exon}`],
            ["Dinucleotide reference / variante", `${site.native_motif || "—"} / ${site.altered_motif || "—"}`],
          ]));
          row.splice_analysis.scenarios.forEach(scenario => content.append(host.detailCard([
            ["Evento ipotizzato", `${scenario.event.event_type === "CRYPTIC_SITE" ? "Sito criptico · esone" : "Salto dell'esone"} ${scenario.event.involved_exons.join(", ")} · predetto, non osservato`],
            ["Frame del prodotto", frameLabel(scenario.frame_effect)],
            ["Nucleotidi rimossi dall'RNA / dalla CDS", `${scenario.rna_deleted_nt ?? "—"} / ${scenario.coding_deleted_nt ?? "—"}`],
            ["NMD del prodotto ipotizzato", nmdLabel(scenario.nmd_predicted)],
            ["Distanza PTC–ultima giunzione", scenario.nmd_distance_nt == null ? "—" : `${scenario.nmd_distance_nt} nt`],
            ...(scenario.rna_inserted_nt ? [["Nucleotidi inclusi nell'RNA / nella CDS", `${scenario.rna_inserted_nt} / ${scenario.coding_inserted_nt ?? "—"}`]] : []),
          ])));
          const prediction = row.splice_analysis.prediction;
          if (prediction) {
            const predicted = prediction.records?.[0];
            content.append(host.detailCard([
              ["Predittore", "SpliceAI"], ["Soglia dello scenario", prediction.threshold],
              ["Donatore: score perdita / guadagno", predicted ? `${predicted.DS_DL} / ${predicted.DS_DG}` : "Non disponibili"],
              ["Accettore: score perdita / guadagno", predicted ? `${predicted.DS_AL} / ${predicted.DS_AG}` : "Non disponibili"],
              ["Nuovo sito genomico", prediction.gained_site?.genomic_position ?? "Non determinato"],
              ["Motivo del nuovo sito", prediction.gained_site?.motif || "—"],
              ["Limiti della predizione", prediction.issues?.join("; ") || "—"],
              ["Scenario", prediction.selection_status === "EXPLORATORY_LOW_DELTA" ? "Esplorativo · delta sotto soglia" : "Predetto"],
            ]));
          }
          const cryptic = row.splice_analysis.scenarios.some(scenario => scenario.event.event_type === "CRYPTIC_SITE");
          content.append(element("p", `${cryptic ? "Exon skipping e altri prodotti alternativi" : "Siti criptici, ritenzione intronica e splicing residuo"} non valutati. L'esito PVS1 è riferito allo scenario predetto.`, "detail-note"));
        }
        [...(row.warnings || []), ...(row.missing_data || [])].forEach(message => content.append(element("p", message, "detail-note")));
        content.append(host.detailDisclosure("Formule", element("pre", JSON.stringify(row.formulas || {}, null, 2))));
        content.append(host.detailDisclosure("Provenance", element("pre", JSON.stringify(row.provenance || {}, null, 2))));
        content.append(host.detailDisclosure("CDS e proteina reference", element("pre", JSON.stringify(row.reference || {}, null, 2))));
        content.append(host.detailDisclosure("Dati molecolari e sequenze", element("pre", JSON.stringify(row.calculation || {}, null, 2))));
      }
    });
    body.append(tr, details);
  });
  table.append(head, body);
  viewport.append(table);
  section.append(viewport);
  return section;
}

export function openAcmgCalculator(host, workspace, options = {}) {
  const detail = workspace.detail;
  if (!detail || detail.loading || detail.error) return;
  const opener = host.shadowRoot.activeElement;
  const embedded = Boolean(options.container);
  const layer = options.container || host.shadowRoot.querySelector("#dialog-layer");
  const backdrop = element("div", undefined, embedded ? "pvs1-embedded" : "dialog-backdrop");
  const dialog = element("section", undefined, embedded ? "pvs1-dialog" : "source-registry-dialog pvs1-dialog");
  dialog.id = "new-acmg-calculator";
  if (!embedded) { dialog.setAttribute("role", "dialog"); dialog.setAttribute("aria-modal", "true"); }
  dialog.setAttribute("aria-labelledby", "new-acmg-calculator-title");
  const heading = element("div", undefined, "dialog-heading");
  const title = element("h4", "PVS1");
  title.id = "new-acmg-calculator-title";
  const close = element("button", "×", "dialog-close");
  close.setAttribute("aria-label", "Chiudi PVS1");
  close.hidden = embedded;
  heading.append(title, close);
  const identity = element("div", undefined, "detail-identity-row pvs1-identity");
  identity.append(element("span", detail.reference_build, "detail-build-badge"),
    element("strong", `${detail.chromosome}:${detail.position}`, "detail-locus"),
    element("span", `${detail.reference}>${detail.alternate}`, "detail-annotation"));
  dialog.append(heading, identity);
  const controls = element("div", undefined, "pvs1-controls");
  const transcriptLabel = element("label", "Trascritto");
  const transcript = element("select");
  transcript.id = "new-acmg-transcript";
  transcript.append(new Option("Seleziona un'annotazione trascrizionale", ""));
  const annotations = detail.annotations || [];
  annotations.forEach(annotation => {
    const option = new Option(`${annotation.transcript || "Trascritto assente"} · ${annotation.gene || "Gene assente"}${annotation.canonical ? " · Canonico" : ""}`, String(annotation.id));
    option.title = [annotation.consequence, annotation.hgvsc].filter(Boolean).join(" · ");
    transcript.append(option);
  });
  const prior = workspace.items?.find(item => String(item.variant_id) === String(detail.variant_id));
  const matches = annotations.filter(annotation => annotation.transcript === prior?.transcript);
  const saved = annotations.find(annotation => String(annotation.id) === workspace.pvs1AnnotationId);
  if (saved || matches.length === 1 || annotations.length === 1) transcript.value = String((saved || matches[0] || annotations[0]).id);
  transcriptLabel.append(transcript);
  const diseaseLabel = element("label", "Contesto gene–malattia");
  const disease = element("select");
  disease.id = "new-acmg-context";
  diseaseLabel.append(disease);
  const evaluate = element("button", "Valuta PVS1", "primary");
  evaluate.type = "button";
  controls.append(transcriptLabel, diseaseLabel, evaluate);
  const apply = options.onApply ? element("button", "Usa nella classificazione") : null;
  if (apply) { apply.type = "button"; apply.id = "new-acmg-apply"; apply.disabled = true; controls.append(apply); }
  const resultHost = element("div");
  resultHost.id = "new-acmg-result";
  resultHost.setAttribute("aria-live", "polite");
  dialog.append(controls, resultHost);
  backdrop.append(dialog);
  let request, closed = false;
  const comparisons = new Map();
  const savedChoices = new Map(), noteDrafts = new Map();
  const strengthOverrides = workspace.pvs1StrengthOverrides ||= {};
  const selectedAnnotation = () => annotations.find(annotation => String(annotation.id) === transcript.value);
  const contextChoices = () => (detail.interpretation_context?.annotations || []).find(
    item => item.annotation_id === selectedAnnotation()?.id && item.transcript === selectedAnnotation()?.transcript,
  )?.contexts || [];
  const updateContexts = () => {
    disease.replaceChildren(new Option("Non documentato / nessuna selezione", ""));
    const choices = contextChoices();
    choices.forEach(choice => disease.append(new Option(
      `${choice.context.disease.label || choice.context.disease.identifier} · ${choice.context.inheritance_modes?.map(inheritanceLabel).join(", ") || "ereditarietà mancante"}`,
      choice.id,
    )));
    if (choices.length === 1) disease.value = choices[0].id;
    disease.disabled = !choices.length;
    evaluate.disabled = !selectedAnnotation()?.transcript;
  };
  const run = async ({restoreStrengthFocus = false} = {}) => {
    request?.abort();
    if (apply) apply.disabled = true;
    const annotation = selectedAnnotation();
    if (!annotation?.transcript) {
      resultHost.replaceChildren(element("p", "Seleziona il trascritto già annotato da HELPER. Nessun altro trascritto viene cercato."));
      return;
    }
    workspace.pvs1AnnotationId = String(annotation.id);
    const choice = contextChoices().find(item => item.id === disease.value);
    const strengthKey = JSON.stringify([workspace.runId, workspace.sample.sample_id, detail.variant_id,
      annotation.id, annotation.transcript, disease.value, choice?.fingerprint?.value, ...(options.inheritance ? [options.inheritance] : [])]);
    const selection = {run_id: workspace.runId, sample_id: workspace.sample.sample_id,
      variant_id: detail.variant_id, annotation_id: annotation.id, transcript: annotation.transcript,
      context_id: disease.value || null, interpretation_context: choice?.context || null};
    if (options.inheritance) selection.inheritance = options.inheritance;
    const advancedWasOpen = Boolean(resultHost.querySelector("#new-acmg-advanced")?.open);
    const current = new AbortController();
    request = current;
    delete resultHost.dataset.status;
    resultHost.replaceChildren(element("p", "Analisi del trascritto selezionato e valutazione PVS1…", "loading"));
    try {
      let storageError = "";
      if (!savedChoices.has(strengthKey)) {
        try {
          const response = await fetch("/api/acmg-calculator/pvs1/saved", {
            method: "POST", headers: {"Content-Type": "application/json"}, signal: current.signal,
            body: JSON.stringify(selection),
          });
          const saved = await response.json();
          if (!response.ok) throw new Error(typeof saved.detail === "string" ? saved.detail : "Salvataggi non disponibili");
          if (closed || current !== request) return;
          savedChoices.set(strengthKey, saved);
          const override = saved.saved?.snapshot?.strength_override;
          if (override && !saved.needs_review && !Object.hasOwn(strengthOverrides, strengthKey)) {
            strengthOverrides[strengthKey] = override.strength;
          }
        } catch (error) {
          if (closed || current !== request || error.name === "AbortError") return;
          storageError = error.message;
        }
      }
      const strengthOverride = strengthOverrides[strengthKey] || null;
      const response = await fetch("/api/acmg-calculator/pvs1", {
        method: "POST", headers: {"Content-Type": "application/json"}, signal: current.signal,
        body: JSON.stringify({...selection, policy: "STANDARD", strength_override: strengthOverride, prepare_save: true}),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Richiesta Calculator non valida.");
      if (closed || current !== request) return;
      if (apply) { apply.disabled = false; apply.onclick = () => options.onApply(payload); }
      const result = payload.result;
      const manual = payload.strength_override;
      let saved = savedChoices.get(strengthKey);
      if (saved?.saved && payload.evaluation_signature && saved.saved.signature !== payload.evaluation_signature) saved.needs_review = true;
      const products = payload.input.molecular_effect?.products || [];
      const basis = products.length === 1 ? products[0].basis : undefined;
      const status = ({ACTIVE: ["Applicato", "complete"], INACTIVE: ["Non applicabile", ""],
        NOT_EVALUABLE: ["Dati mancanti", "pending"], REQUIRES_REVIEW: ["Da rivedere", "indexing"]})[result.status] || [result.status, ""];
      const report = element("section", undefined, "pvs1-result-summary");
      report.id = "new-acmg-summary";
      const reportHeading = element("div", undefined, "pvs1-result-heading");
      reportHeading.append(element("h5", "Esito PVS1"), element("span", manual
        ? result.applied_strength ? "Applicato manualmente" : "Non applicato manualmente" : status[0],
      `badge pvs1-status ${manual ? "pending" : status[1]}`));
      if (result.applied_strength) reportHeading.append(element("strong",
        strengthLabel(result.applied_strength), "pvs1-strength"));
      const basisBadge = element("span", ({PREDICTED: "Prodotto predetto", OBSERVED: "RNA osservato"})[basis] || (products.length > 1 ? "Prodotti multipli" : "Prodotto non determinato"), "gene-evidence-badge");
      basisBadge.dataset.basis = basis || "UNKNOWN";
      reportHeading.append(basisBadge);
      report.append(reportHeading, element("p", result.status === "ACTIVE"
        ? "Esito riferito al prodotto e al contesto selezionati." : result.reason, "detail-note"));
      const strengthControl = element("label", "Strength applicata", "pvs1-strength-control");
      const strengthSelect = element("select");
      strengthSelect.id = "new-acmg-strength";
      strengthSelect.append(new Option(`Automatico (${strengthLabel(manual ? manual.automatic_applied_strength : result.applied_strength)})`, ""));
      Object.entries(strengthLabels).forEach(([value, label]) => strengthSelect.append(new Option(label, value)));
      strengthSelect.append(new Option("Non applicare", "NONE"));
      strengthSelect.value = manual?.strength || "";
      strengthSelect.addEventListener("change", () => {
        if (strengthSelect.value) strengthOverrides[strengthKey] = strengthSelect.value;
        else delete strengthOverrides[strengthKey];
        run({restoreStrengthFocus: true});
      });
      strengthControl.append(strengthSelect);
      report.append(strengthControl);
      if (manual) report.append(element("p", `Automatico: ${status[0]} · Calcolata: ${strengthLabel(result.calculated_strength)} · Applicata: ${strengthLabel(result.applied_strength)} (manuale)`, "detail-note"));
      const saveControls = element("div", undefined, "pvs1-save-controls");
      const note = element("input");
      note.type = "text";
      note.maxLength = 1000;
      note.placeholder = "Nota (facoltativa)";
      note.setAttribute("aria-label", "Nota della valutazione PVS1");
      note.value = noteDrafts.get(strengthKey) ?? saved?.saved?.note ?? "";
      note.addEventListener("input", () => { noteDrafts.set(strengthKey, note.value); showSaved(); });
      const save = element("button", "Salva valutazione");
      save.type = "button";
      save.id = "new-acmg-save";
      save.disabled = !payload.evaluation_id;
      const saveStatus = element("span", undefined, "detail-note");
      saveStatus.id = "new-acmg-save-status";
      saveStatus.setAttribute("role", "status");
      const showSaved = () => {
        const previous = saved?.saved;
        if (!previous) return;
        const changed = previous.snapshot.result.applied_strength !== result.applied_strength
          || (previous.snapshot.strength_override?.strength || null) !== (manual?.strength || null)
          || previous.note.trim() !== note.value.trim();
        saveStatus.textContent = saved.needs_review
          ? `Salvata rev. ${previous.revision}: ${strengthLabel(previous.snapshot.result.applied_strength)}${previous.snapshot.strength_override ? " (manuale)" : ""} · dati aggiornati: valutazione da ricontrollare`
          : `Salvata rev. ${previous.revision}${changed ? " · modifiche non salvate" : ""}`;
        saveStatus.dataset.saveStatus = saved.needs_review ? "NEEDS_REVIEW" : changed ? "CHANGED" : "SAVED";
      };
      showSaved();
      if (storageError || payload.persistence_error) saveStatus.textContent = storageError || payload.persistence_error;
      save.addEventListener("click", async () => {
        save.disabled = true;
        saveStatus.textContent = "Salvataggio…";
        try {
          const response = await fetch("/api/acmg-calculator/pvs1/save", {
            method: "POST", headers: {"Content-Type": "application/json"}, signal: current.signal,
            body: JSON.stringify({run_id: workspace.runId, evaluation_id: payload.evaluation_id, note: note.value}),
          });
          const record = await response.json();
          if (!response.ok) throw new Error(typeof record.detail === "string" ? record.detail : "Salvataggio non riuscito");
          if (closed || current !== request) return;
          saved = record;
          savedChoices.set(strengthKey, record);
          noteDrafts.set(strengthKey, note.value);
          showSaved();
          workspace.classificationCache?.delete(detail.variant_id);
          if (workspace.detail === detail) host.loadClassifications?.(workspace, detail.variant_id, {refresh: true});
        } catch (error) {
          if (closed || current !== request || error.name === "AbortError") return;
          saveStatus.textContent = error.message;
          saveStatus.dataset.saveStatus = "ERROR";
        } finally {
          save.disabled = false;
        }
      });
      saveControls.append(note, save, saveStatus);
      report.append(saveControls);
      resultHost.replaceChildren(report, molecularSummary(host, payload, annotation));
      const molecularHost = element("div");
      molecularHost.setAttribute("aria-live", "polite");
      const showImpact = analysis => {
        molecularHost.replaceChildren();
        if (analysis) molecularHost.append(renderTranscriptMolecularImpact(host, analysis));
        if (analysis && analysis.scope !== "SELECTED") return;
        const compare = element("button", "Analizza tutti i trascritti");
        compare.type = "button";
        compare.addEventListener("click", async () => {
          compare.disabled = true;
          molecularHost.setAttribute("aria-busy", "true");
          try {
            const response = await fetch("/api/acmg-calculator/molecular-impact", {
              method: "POST", headers: {"Content-Type": "application/json"}, signal: current.signal,
              body: JSON.stringify({run_id: workspace.runId, sample_id: workspace.sample.sample_id,
                variant_id: detail.variant_id, annotation_id: annotation.id, transcript: annotation.transcript}),
            });
            const analysis = await response.json();
            if (!response.ok) throw new Error(typeof analysis.detail === "string" ? analysis.detail : "Analisi dei trascritti non disponibile.");
            if (closed || current !== request) return;
            comparisons.set(annotation.id, analysis);
            showImpact(analysis);
            molecularHost.querySelector('tr[aria-current="true"] button')?.focus();
          } catch (error) {
            if (closed || current !== request || error.name === "AbortError") return;
            const message = element("p", error.message, "inline-error");
            message.setAttribute("role", "alert");
            molecularHost.append(message);
            compare.disabled = false;
          } finally {
            molecularHost.setAttribute("aria-busy", "false");
          }
        });
        molecularHost.append(compare);
      };
      if (contextChoices().length > 1 && !disease.value) resultHost.append(element("p", "Seleziona un contesto gene–malattia per la decisione PVS1. L'analisi molecolare dei trascritti è indipendente dal contesto.", "detail-note"));
      resultHost.dataset.status = result.status;
      resultHost.dataset.strengthMode = manual ? "MANUAL" : "AUTO";
      resultHost.dataset.appliedStrength = result.applied_strength || "NONE";
      if (result.missing_data?.length) {
        const missing = element("section", undefined, "pvs1-missing");
        missing.append(element("h5", "Informazioni necessarie mancanti"));
        const list = element("ul");
        [...new Set(result.missing_data)].forEach(value => list.append(element("li", value)));
        missing.append(list);
        resultHost.append(missing);
      }
      const warnings = [...new Set(result.warnings || [])];
      const advanced = lazyDisclosure(host, "Informazioni avanzate", () => {
        const content = element("div", undefined, "pvs1-advanced-content");
        content.append(lazyDisclosure(host, "Valutazioni salvate", () => {
          const history = element("div", undefined, "detail-content");
          const load = element("button", "Carica storico");
          load.type = "button";
          let before;
          load.addEventListener("click", async () => {
            load.disabled = true;
            try {
              const response = await fetch("/api/acmg-calculator/pvs1/history", {
                method: "POST", headers: {"Content-Type": "application/json"}, signal: current.signal,
                body: JSON.stringify({...selection, before_revision: before}),
              });
              const page = await response.json();
              if (!response.ok) throw new Error(typeof page.detail === "string" ? page.detail : "Storico non disponibile");
              if (closed || current !== request) return;
              page.items.forEach(item => history.insertBefore(host.detailCard([
                ["Revisione", item.revision], ["Salvata", new Date(item.saved_at).toLocaleString()],
                ["Calcolata", strengthLabel(item.snapshot.result.calculated_strength)],
                ["Applicata", `${strengthLabel(item.snapshot.result.applied_strength)} · ${item.snapshot.strength_override ? "manuale" : "automatica"}`],
                ["Nota", item.note || "—"],
              ]), load));
              if (!page.items.length) history.insertBefore(element("p", "Nessuna valutazione salvata.", "detail-note"), load);
              before = page.next_before_revision;
              load.hidden = !before;
              load.textContent = "Carica precedenti";
            } catch (error) {
              if (closed || current !== request || error.name === "AbortError") return;
              history.insertBefore(element("p", error.message, "inline-error"), load);
            } finally { load.disabled = false; }
          });
          history.append(load);
          return history;
        }));
        content.append(lazyDisclosure(host, "Requisiti PVS1 e fonti", () => {
          const requirements = element("div");
          requirements.id = "new-acmg-requirements";
          (result.decision_trace || []).forEach(raw => {
            const requirement = JSON.parse(raw);
            const format = value => value == null ? "—" : typeof value === "string" ? value : JSON.stringify(value);
            const row = lazyDisclosure(host, requirement.description, () => host.detailCard([
              ["Stato", requirement.status], ["Valore", format(requirement.value)],
              ["Soglia", format(requirement.threshold)], ["Fonte", requirement.source?.join("; ") || "Non disponibile"],
              ["Regola", requirement.rule], ["Motivazione", requirement.reason],
            ]), {status: requirement.status});
            row.dataset.requirementId = requirement.id;
            row.dataset.status = requirement.status;
            requirements.append(row);
          });
          return requirements;
        }, {status: `${result.decision_trace?.length || 0} controlli`}));
        content.append(lazyDisclosure(host, "Trascritti e calcoli molecolari", () => {
          showImpact(comparisons.get(annotation.id) || payload.molecular_impact);
          return molecularHost;
        }));
        if (warnings.length) content.append(lazyDisclosure(host, "Avvisi e limiti", () => {
          const list = element("ul", undefined, "pvs1-warning-list");
          warnings.forEach(value => list.append(element("li", value)));
          return list;
        }, {status: String(warnings.length)}));
        content.append(lazyDisclosure(host, "Dati della valutazione", () => host.detailCard([
          ["Gene", payload.input.disease_context.gene], ["Malattia", payload.input.disease_context.disease || "Non disponibile"],
          ["Ereditarietà", payload.input.disease_context.inheritance || "Non disponibile"],
          ["Trascritto", payload.input.transcript?.accession], ["Modello", `${result.ruleset_id} ${result.ruleset_version}`],
          ["Policy", "STANDARD"], ["Stato automatico", result.status], ["Base del prodotto", basis || "UNKNOWN"],
          ["Scelta strength", manual ? "Manuale" : "Automatica"],
          ["Strength calcolata", result.calculated_strength || "—"], ["Strength applicata", result.applied_strength || "—"],
          ["Motivazione completa", result.reason], ["Origine dati molecolari", payload.molecular_origin],
        ])));
        const indicators = payload.mechanism_assessment?.gene_level_indicators || [];
        if (indicators.length) content.append(lazyDisclosure(host, "ClinGen HI e gnomAD pLI", () => {
          const details = element("div");
          details.append(element("p", "Supporto a livello del gene. Un pLI basso non esclude LoF nelle malattie recessive; questi indici non stabiliscono da soli il meccanismo della malattia selezionata.", "detail-note"));
          indicators.forEach(item => details.append(host.detailCard([
            ["Indice", item.metric === "HI" ? "ClinGen HI" : "gnomAD pLI"], ["Valore", indicatorValue(item)],
            ["Interpretazione", indicatorLabel(item.interpretation)], ["Supporto LoF utilizzabile", item.supports_lof ? "Sì · ambito gene" : "No"],
            ["Trascritto gnomAD", item.transcript || "—"], ["Release", item.release || "Non documentata"],
            ["Limiti", item.issues?.map(indicatorIssueLabel).join("; ") || "—"], ["Fonte", item.source_url || "Non disponibile"],
          ])));
          return details;
        }));
        if (payload.mechanism_assessment) content.append(lazyDisclosure(host, "Evidenze del meccanismo", () =>
          element("pre", JSON.stringify(payload.mechanism_assessment, null, 2))));
        return content;
      }, {open: advancedWasOpen, status: warnings.length ? `${warnings.length} avvisi e limiti` : "Requisiti, fonti e calcoli"});
      advanced.id = "new-acmg-advanced";
      resultHost.append(advanced);
      if (restoreStrengthFocus) strengthSelect.focus();
    } catch (error) {
      if (closed || current !== request || error.name === "AbortError") return;
      const message = element("p", error.message, "inline-error");
      message.setAttribute("role", "alert");
      resultHost.replaceChildren(message);
    }
  };
  const closeDialog = () => {
    closed = true;
    request?.abort();
    document.removeEventListener("keydown", onKeydown);
    layer.replaceChildren();
    if (!embedded) opener?.focus();
  };
  const onKeydown = event => {
    if (event.key === "Escape") { event.preventDefault(); closeDialog(); }
    if (event.key === "Tab") {
      const focusable = [...dialog.querySelectorAll("button,select,input,summary")].filter(item => !item.disabled && item.getClientRects().length);
      const first = focusable[0], last = focusable[focusable.length - 1], active = host.shadowRoot.activeElement;
      if (event.shiftKey && active === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
    }
  };
  close.addEventListener("click", closeDialog);
  backdrop.addEventListener("click", event => { if (event.target === backdrop) closeDialog(); });
  evaluate.addEventListener("click", run);
  transcript.addEventListener("change", () => { updateContexts(); run(); });
  disease.addEventListener("change", run);
  if (!embedded) document.addEventListener("keydown", onKeydown);
  layer.replaceChildren(backdrop);
  updateContexts();
  if (embedded) { transcript.disabled = true; disease.disabled = true; }
  else close.focus();
  run();
  return {close: closeDialog};
}
