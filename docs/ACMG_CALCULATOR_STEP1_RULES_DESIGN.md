# ACMG Calculator — STEP 1.1: Final Rules Simplification

Design basato sullo [STEP 0](ACMG_CALCULATOR_STEP0_PVS1_MODEL.md), sezioni C–F. Aggiorna lo STEP 1; descrive soltanto la futura implementazione.
Il modello generale PVS1 sarà logica Python esplicita. Le 48 condizioni dello STEP 0 sono riferimenti scientifici, senza corrispondenza obbligatoria con 48 oggetti o funzioni.

Struttura target proposta, da non creare in questo step:

| Componente | Responsabilità |
|---|---|
| `pvs1/models.py` | Rappresentazione minima di dati biologici, contesto gene–malattia–ereditarietà, policy ed esito con provenance. |
| `pvs1/calculator.py` | Unico Calculator: flusso PVS1 generale in Python, applicazione degli override pertinenti e della policy indipendente. |
| `pvs1/rules.py` | Identità/versione e parametri generali; lettura, verifica e selezione del JSON VCEP; soli punti di modifica esplicitamente supportati. |
| `pvs1/vcep/*.json` | Metadati della specifica e soli override necessari; nessuna copia integrale delle regole generali o condizione eseguibile. |

Versionamento e provenance:

- Il generale ha identità `PVS1_GENERAL` e versione locale iniziale proposta `1.0.0`, dichiarate in `rules.py`; conserva fonti A18/W23/F24 e limiti dello STEP 0. Ogni revisione scientifica richiede una nuova versione; le versioni pubblicate restano immutabili. Non serve un JSON del generale.
- Ogni JSON identifica profilo/versione, versione generale compatibile esatta, ente VCEP, gene, malattia, ereditarietà e fonte ufficiale con versione/data/URL. Versione locale del profilo e versione della specifica restano distinte; una revisione genera una nuova versione, senza sostituzioni silenziose.
- Ogni override ha identificativo, punto modificato, valore, riferimento scientifico dello STEP 0, sezione/figura della specifica e motivazione. Eredita la fonte ufficiale del profilo; eventuali fonti aggiuntive devono essere esplicite per quella modifica.
- L'esito dovrà riportare versione del generale, profilo/versione se usato, override applicati con fonti e policy selezionata; dati mancanti, Not applicable e revisione esperta restano esiti distinti.

Esempio JSON sintetico interamente fittizio, non selezionabile; identificativi e trascritto sono segnaposto:

```json
{
  "profile_id": "DEMO_PVS1", "version": "0.1.0", "status": "example_only",
  "issuer": "DEMO_VCEP", "general_version": "1.0.0",
  "gene": "DEMO_GENE", "disease": "DEMO_DISEASE", "inheritance": "AD",
  "source": {"url": "https://example.invalid/spec", "version": "0.1", "date": "2026-10-28"},
  "overrides": [{
    "id": "DEMO_O1", "point": "reference_transcript", "value": "DEMO_TRANSCRIPT.1",
    "step0_ref": "P06", "locator": "PVS1, sezione 1",
    "rationale": "Trascritto indicato dalla specifica fittizia per questa associazione."
  }]
}
```

Override semplici ammessi, solo se previsti dalla specifica e supportati dal generale:

- Riferimenti biologici: trascritto/versione, esoni rilevanti e start alternativi documentati (P06–P07, P19–P22).
- Confini NMD o regioni/esclusioni esplicite: coordinate, riferimento di sequenza e inclusività definiti (P07–P11, P36–P39).
- Soglie di quantità già previste: valore, unità, denominatore e operatori espliciti; nessuna formula nuova (P02–P04, P12–P14, P37, P42–P43).
- Strength o Not applicable di un ramo già definito, identificato senza ambiguità; nessuna strength complessiva imposta indipendentemente dalle condizioni.

Un punto omesso eredita il generale. Un override sostituisce il solo punto indicato, incluse eventuali liste; niente unioni implicite, percorsi arbitrari, predicati JSON o interpretazione di espressioni. Punti sconosciuti, duplicati o modifiche contraddittorie rendono il profilo non utilizzabile fino a revisione. L'assenza di dati biologici non è un override e non prova un'esclusione.

Selezione e precedenza:

1. Identificare gene, malattia ed ereditarietà con valori non ambigui; selezionare un solo profilo pubblicato pertinente all'intera combinazione, con versione esplicita e generale compatibile. Se necessario, `profile_id` distingue specifiche concorrenti; nessun “latest” implicito o scelta per solo gene.
2. Usare il generale quando non è selezionata una VCEP pertinente, dichiarandolo. Un profilo richiesto ma assente, ambiguo, incompatibile o incompleto richiede chiarimento/revisione, senza ripiego silenzioso o fusione di più VCEP.
3. I punti documentati del VCEP prevalgono sui corrispondenti valori generali; tutto il resto rimane ereditato. Le esclusioni VCEP applicabili restano prioritarie in entrambe le policy.
4. `STANDARD`/`EXPERIMENTAL` è un parametro indipendente: il medesimo profilo può essere selezionato con entrambe le policy. La policy non seleziona, sostituisce o riscrive la VCEP e non riabilita un caso escluso dalla specifica.
5. L'eventuale trattamento sperimentale di meccanismi `INFERRED`/`DISPUTED` appartiene alla policy, non agli override ufficiali. Rimane dichiarato sperimentale e non equivale a LoF dimostrato; le condizioni operative non sono definite in questo step.

Limiti dei semplici override:

Nuovi predicati o un diverso ordine decisionale, eccezioni NMD dipendenti da più fattori, aggregazioni gene-specifiche di trascritti/rescue/splicing leaky e nuovi trattamenti di riarrangiamenti possono richiedere logica dedicata. Una soglia basta soltanto se quantità e percorso esistono già nel generale.
Quando una specifica richiede tale logica, documentare qui o nella descrizione del profilo la condizione, la fonte puntuale e il limite: nei casi coinvolti serve revisione, senza dichiarare la specifica interamente supportata o ignorarne le esclusioni. Non introdurre un sistema di branch per risolverlo ora.
Nessuna directory per policy o branch, registro duplicato, plugin o motore generico. Le incertezze scientifiche dello STEP 0 restano esplicite. Questo step modifica soltanto il documento: nessun codice, test, modifica a HELPER/vecchio Engine, commit o avvio dello STEP 2.
