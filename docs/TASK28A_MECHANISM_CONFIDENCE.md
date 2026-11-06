# Task 28A — Mechanism Assessment

> Nota 2026-10-29: documento storico. La cache pubblica dei meccanismi e il relativo assessment locale sono conservati; Workbench, Coordinator/Assembler, contratti e valutazioni del servizio esterno descritti qui sono stati rimossi. Stato operativo: [HELPER_STRUCTURAL_CLEANUP.md](HELPER_STRUCTURAL_CLEANUP.md).

Data: 2026-10-28. Stato: **PARTIALLY_IMPLEMENTED**. Solo analisi statica;
nessuna attestazione di validazione funzionale o clinica.

## Implementazione HELPER

`helper_next/src/helper_next/core/acmg_mechanism_assessment.py` riusa la matrice
della Mechanism Evidence Cache e separa stato dell'associazione, requisito
allelico, meccanismo, confidence e scope. Restano distinti DEFINITIVE, INFERRED,
DISPUTED e UNKNOWN. Sono conservati assertions, fonti favorevoli e contrastanti,
incertezze di mapping, snapshot e provenance. La versione delle regole biologiche
è ora `helper-mechanism-assessment-rules-1.1`; lo schema locale resta 1.0.

Lo scope richiede identità del gene, malattia o alias riconciliato, applicabilità
EXACT/MAPPED e requisito allelico noto e coincidente. Una malattia o ereditarietà
diversa non genera conflitto. GenCC validity non diventa mechanism confidence.
DEFINITIVE richiede un'assertion molecolare esplicita da una fonte curata ammessa;
non equivale ad approvazione clinica della valutazione HELPER.

## Priorità VCEP

La selezione dà precedenza a un'assertion normalizzata `clingen_vcep` pertinente,
esplicita e approvata, anche per GoF, DN e OTHER. Un solo meccanismo VCEP qualificato
diventa DEFINITIVE; assertions VCEP incompatibili rimangono DISPUTED. Le evidenze
generiche contrastanti restano nelle assertions e nelle conflicting evidence e
producono una limitazione che richiede revisione. L'assessment non viene mutato
per applicare la precedenza.

Il confine accetta soltanto record con categoria DIRECT_MECHANISM_ASSERTION,
directness DIRECT, identificativo/versione della specifica, stato APPROVED,
statement molecolare originale archiviato, riferimenti al record, URL HTTPS
`clinicalgenome.org` o sottodominio e hash coerente dell'assertion originale.
Nel record normalizzato lo statement è conservato in
`raw_assertion.molecular_mechanism_statement` e coincide con `original_mechanism`.
Identificativo, versione, URL, hash e data di acquisizione vengono esposti nella
provenance dell'assessment. Queste condizioni sono un controllo di provenienza
del record archiviato, non una nuova verifica remota dell'approvazione.

**Limite aperto:** gli adapter esistenti non producono attualmente tali assertions
VCEP. La regola è implementata sul confine della matrice normalizzata; il percorso
di acquisizione VCEP reale resta **BLOCKED** dall'assenza di un'origine verificabile.
I profili e gli override dell'Engine sono riferimenti a regole: non vengono
trasformati in assertions biologiche. Nessuna fonte o assertion è stata inventata.
Le fixture VCEP aggiunte nei test sono sintetiche. Nessun albero PVS1 VCEP è stato
copiato in HELPER.

G2P rimane l'origine diretta disponibile. L'assessment riconosce record diretti
qualificati di ClinGen, Orphanet/Orphadata e GenCC, ma non aggiunge parser né
popolamenti: l'indice GenCC attuale fornisce validity e Orphadata è usato dal
registry per il mapping. Non si dichiara una copertura di assertions molecolari
che gli adapter non forniscono.

## Inferenze e limiti

- ClinGen HI 3 con identità del gene qualificata può sostenere INFERRED; senza
  malattia/ereditarietà qualificate resta GENE_LEVEL.
- Un valore LOEUF basso o una variante ClinVar P/LP isolata non producono LoF.
- L'adapter ClinVar disponibile è allele-specific e non fornisce distribuzioni
  LoF gene–malattia indipendenti da PVS1; non sono state costruite distribuzioni.
- Il constraint gnomAD rimane contestuale. Molte identità Dosage/constraint non
  hanno un crosswalk HGNC verificato; HELPER mantiene l'incertezza.
- Evidenze insufficienti restano UNKNOWN. Nessun voto, punteggio ACMG o calcolo
  Tavtigian viene effettuato dal Coordinator.

## File e verifiche successive

Modificati per l'assessment: `core/acmg_mechanism_assessment.py`,
`core/acmg_evidence.py` e `tests/test_acmg_mechanism_assessment.py` sotto
`helper_next/` con i rispettivi prefissi `src/helper_next/` e `tests/`.
Il dettaglio dell'integrazione è in [TASK28C_HELPER_INTEGRATION.md](TASK28C_HELPER_INTEGRATION.md).

Predisposti test sintetici per precedenza GoF/DN/OTHER, provenance mancante,
stato non approvato, scope diverso, conflitti tra VCEP e conservazione dell'input.
**Non eseguiti.** Dopo autorizzazione serviranno verifiche mirate su questi nuovi
casi e su una fonte VCEP reale, quando disponibile, senza ripetere automaticamente
le suite già superate o bloccate. Il parsing statico non dimostra il comportamento
di un'origine VCEP reale né la compatibilità con l'Engine installato.
