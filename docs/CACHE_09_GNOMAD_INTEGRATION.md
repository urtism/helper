# CACHE-09 — gnomAD v4.1.1 / v4.1.2

## Audit prima dell'implementazione (2026-11-03)

Consultati CACHE-01/02/03, CACHE-06A/06B, CACHE-07/08 e i riferimenti
ClinVar CACHE-04/05/05.1/05.2. Il checkout contiene lavoro precedente non
committato: CACHE-09 ne conserva le modifiche.

| Dominio | Implementazione riutilizzata | Risultato dell'audit |
|---|---|---|
| Frequenze | `helper_variants.gnomad_frequency`, SQLite `frequencies` | Solo genomes; GRCh37 → 2.1.1, GRCh38 → etichetta 4.1. Release nella riga ma non nella chiave. Popolazioni XX/XY scartate. Nessun FAF. |
| Constraint | `gene_phenotype.gnomad_constraints` | Una riga per simbolo/canonical transcript; query GraphQL senza release verificata. Etichetta UI 4.1.2 ingiustificata; CI inferiori/syn/rank/flags scartati. |
| Source Manager | `core.acmg_sources.SourceManager` | Delega alle due cache; lista/prioritizzazione leggono frequenze locali in batch. Nessun bisogno di un nuovo manager. |
| Registry/amministrazione | `source_registry`, `api/data_sources`, sezione Database | Lettori locali; registry browser dichiara release hardcoded, amministrazione distingue release archiviate/configurate. |
| Identità | `core.biological_identity.allele_refs_batch` (ga2) | Normalizzazione/REF tramite FASTA; indel senza reference non risolti. Riutilizzare il contratto, non duplicare il normalizzatore. |
| Liftover | `helper_variants.liftover` | Proiezioni alleliche NCBI memorizzate nello SQLite esistente; errore/ambiguità espliciti. Nessuna equivalenza per sola posizione. |
| Indexer | `indexer.index_run`, `store.variants/calls` | Identità variante unica condivisa dai campioni; import VCF streaming; enrichment remoto assente. Annotazioni VCF originali mantenute separate. |
| Dettaglio/browser | `query.variant_detail`, endpoint `gnomad-frequency`, `variant-browser.js` | Cache nel dettaglio ma frontend richiede sempre l'endpoint; visualizzazione genomes verticale e popolazioni estese. |
| Gene-Phenotype | `query_gene`, `mechanism_source_records` | Constraint come contesto statistico, distinto da G2P/GenCC/Dosage. Nessun cambiamento alle decisioni LoF/GoF/DN. |
| gene_struct | `TranscriptReferenceProvider` / cache Ensembl | Strutture/sequenze qualificate assembly/accession/release, già riutilizzabili; non copiarle nel constraint. |

Inventario locale in sola lettura: 86 frequenze (tutte 2.1.1), 52 righe
constraint, 95 proiezioni assembly. Sono quantità osservate in questa sessione,
non garanzie sul contenuto futuro. Nessun VCF/HT v4 qualificato configurato nel
client esistente. Le frequenze VEP/VCF sono annotazioni storiche, non una fonte
v4.1.1 verificata. I packet mechanism sono derivati, non un secondo archivio
da alimentare con download paralleli.

## Verifica ufficiale

- [Release 4.1.2](https://gnomad.broadinstitute.org/news/2026-09-gnomad-v4-1-2/):
  modifica rank/bin del constraint; metriche incluso LOEUF e frequenze invariate.
- [Download ufficiali](https://gnomad.broadinstitute.org/downloads): VCF exomes e
  genomes 4.1.1; HT browser combinato; risorse AN all-sites ancora 4.1;
  constraint TSV BGZF/HT 4.1.2.
- [Schema API](https://github.com/broadinstitute/gnomad-browser/blob/main/graphql-api/src/graphql/types/variant.graphql):
  `VariantDetails` espone exome/genome/joint, FAF popmax, conteggi, filtri,
  flags, statistiche di confronto e metriche di sito. `VariantPopulation`
  NON espone FAF95/99; `meta` non espone la release gnomAD.
- [Adapter ufficiale](https://github.com/broadinstitute/gnomad-browser/blob/main/graphql-api/src/queries/variant-datasets/gnomad-v4-variant-queries.ts):
  `faf95.popmax` nel dettaglio corrisponde al massimo FAF fra gruppi eleggibili,
  non alla massima AF osservata. Non ricostruire il gruppo da AF.
- Schema TSV verificato con lettura limitata ai primi 65.536 byte del file
  ufficiale: `gene`, `gene_id`, `transcript`, `transcript_version`, `canonical`,
  `mane_select`, `constraint_flags`, `gene_flags`, `lof/mis/syn.obs/exp/oe`,
  `*.oe_ci.lower/upper`, `lof.oe_ci.upper_rank/upper_bin_decile`.
  Nessun download completo effettuato durante l'audit.

Le sezioni seguenti documentano implementazione e verifiche al completamento.
