# Priority: massimo AF e flag gnomAD

Verifica e modifica del 6 novembre 2026.

Nel profilo corrente, il componente frequenza usa il massimo fra le AF gnomAD
utilizzabili e la frequenza massima VEP/VCF conservata nell'annotazione. La scala
AF e i suoi limiti inclusivi restano invariati. I profili storici conservano la
precedente selezione delle fonti.

## Selezione della frequenza

- Per gnomAD si confrontano Joint, Exomes e Genomes, includendo le frequenze dei
  gruppi di ascendenza ammessi dalla policy con conteggi validi e AN sufficiente.
  Joint non ha più una preferenza che nasconde una frequenza superiore negli
  altri dataset. Restano i controlli esistenti di coerenza AF/AC/AN e callability.
- Il massimo così ottenuto si confronta con `vep_max_af`, passato dalla query a
  partire dal campo di frequenza dell'annotazione VEP/VCF. Per i client diretti
  del motore, `population_af` resta il valore di ripiego quando manca il campo
  esplicito. Si conserva la provenienza della fonte vincente.
- Il risultato espone `vep_max_af`, `gnomad_observed_af`, `observed_af` e
  `observed_af_source`. La colonna AF_max della tabella viene allineata alla
  frequenza usata dal componente quando questa è disponibile.
- FAF95 resta informativa: nel profilo AF corrente non sostituisce AF e non
  modifica il punteggio in base a MCAF.
- Una frequenza VEP positiva può essere usata quando gnomAD manca o ha un errore
  tecnico. Non si trasforma un VEP AF=0 in assenza verificata. Un VEP AF positivo
  impedisce il bonus di assenza anche quando gnomAD non osserva l'allele.
- Un fallimento QC esplicito non viene aggirato usando una frequenza VEP più
  favorevole: se non resta un dataset gnomAD utilizzabile, il componente rimane
  neutro. Questa protezione è distinta dalla gestione della sola discordanza.

Esempi: VEP 0,02 e gnomAD 0,00001 → AF 0,02; VEP 0,00001 e gnomAD 0,02 →
AF 0,02. Entrambi producono −10 nella scala corrente. Se Exomes ha AF 0,005,
Genomes 0,002 e Joint 0,00001, si usa almeno 0,005, prima del confronto con VEP
e con le AF dei gruppi ammessi.

## `discrepant_frequencies`

La flag viene mantenuta nella fonte e riportata negli avvisi, ma non esclude la
frequenza. La stessa eccezione vale quando la flag compare nei filtri Joint,
nelle flag del dataset o della variante, o quando la discordanza è rilevata dai
test statistici già letti dal motore. Una discordanza non produce una penalità
aggiuntiva indipendente: si applica la scala alla AF massima selezionata.

È una scelta di ranking richiesta per questa applicazione. La documentazione
gnomAD spiega che la differenza fra exomi e genomi può dipendere da popolazioni,
tecnologie e artefatti: non stabilisce una fonte universalmente migliore.
Fonte: [gnomAD v4.1](https://gnomad.broadinstitute.org/news/2024-04-gnomad-v4-1).

## Altre flag effettivamente presenti

Ispezione in sola lettura della cache locale: 1.896 record. Le occorrenze sotto
non sono gruppi disgiunti e non rappresentano altrettante varianti uniche del
campione. La cache non è stata modificata. Ex = Exomes, Gen = Genomes.

| Flag | Occorrenze | Problema e valutazione |
| --- | ---: | --- |
| `discrepant_frequencies` | 853 Joint | Frequenze discordanti tra tecnologie: ora avviso, senza esclusione automatica. |
| `AS_VQSR` | 61 Ex / 49 Gen | Fallimento del controllo di qualità della chiamata: possibile artefatto. Il dataset interessato resta escluso; un altro dataset valido può essere usato. |
| `InbreedingCoeff` | 75 Ex / 34 Gen | Eccesso di eterozigoti rispetto alle attese: possibile problema del sito, non equivale a una frequenza biologica affidabile. Resta il filtro QC. |
| `AC0` | 36 Ex / 4 Gen | Nessun genotipo alternativo ha superato i controlli richiesti. Non significa assenza biologica e non deve generare un bonus di rarità. |
| `lcr` | 175 | Regione a bassa complessità: rischio di allineamento/chiamata. Il blocco conservativo esistente resta; non è però una prova automatica di AF errata. |
| `segdup` | 131 | Duplicazione segmentale: rischio di mapping ambiguo e falsa frequenza. Il blocco conservativo esistente resta. |
| `not_called_in_exomes` | 3 Joint | Dato esomico non disponibile; non è un'assenza verificata. Il motore può usare Genomes se passa i suoi controlli. |
| `lc_lof` | 5 | Bassa confidenza dell'annotazione pLoF. Riguarda l'interpretazione della conseguenza, non dimostra un errore dei conteggi AF. |
| `lof_flag` | 2 | Avviso LOFTEE sulla conseguenza pLoF; stesso problema di separazione fra confidenza dell'effetto e affidabilità della frequenza. |

I filtri AS_VQSR, AC0 e InbreedingCoeff sono descritti nella sezione Variant QC
di [gnomAD v4.0](https://gnomad.broadinstitute.org/news/2023-11-gnomad-v4-0/).
Per le flag regionali e LoF sono stati verificati anche il
[codice del browser ufficiale](https://github.com/broadinstitute/gnomad-browser/blob/main/browser/src/VariantList/VariantFlag.tsx)
e la [documentazione QC](https://github.com/broadinstitute/gnomad-browser/blob/main/browser/help/topics/variant-qc.md).

Valutazione per un successivo cambiamento: `lc_lof` e `lof_flag` dovrebbero
agire sulla confidenza della conseguenza/PVS1, senza azzerare automaticamente
AF quando i conteggi superano il QC. Attualmente, come le altre flag diverse da
`discrepant_frequencies`, mantengono il blocco preesistente; questa modifica non
ha allentato quei controlli. Lo stesso principio vale per flag di annotazione
come `nc_transcript`, `os_lof` e `mnv`, non presenti nella cache ispezionata.

## Verifica

`helper_next/tests/test_population_max_af.py` copre entrambe le fonti vincenti,
massimo fra dataset e gruppi, provenienza, non sostituzione con FAF95, posizioni
diverse della flag di discordanza, fallback VEP, veto del bonus di assenza e
mantenimento dei veri blocchi QC. Le regressioni coprono inoltre lettura delle
cache esistenti senza riscriverle, profili storici, query della tabella e filtri.
