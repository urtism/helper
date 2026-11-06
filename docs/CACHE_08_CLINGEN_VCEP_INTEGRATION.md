# CACHE-08 — Integrazione ClinGen VCEP in HELPER

Data: **2 novembre 2026**. Le assertion dello snapshot ERepo installato in
CACHE-07 sono consultabili nel dettaglio variante del Variant Browser.
Sono evidenze esterne informative; non modificano priority, classificazione,
criteri o strength calcolati da HELPER.

## Audit e architettura effettiva

Letti `CACHE_07_CLINGEN_VCEP_LOCAL.md`, reader/importatore CACHE-07,
SourceManager/registry, identità biologiche, query/API/browser, schema e
indicizzazione delle run, percorso del Calculator PVS1. Il working tree
contiene modifiche di task precedenti: sono conservate. Nessun database
operativo è stato costruito, aggiornato o migrato in CACHE-08.

| Componente verificato | Utilizzo effettivo |
| --- | --- |
| `SourceManager` in `core/acmg_sources.py` | Nuove deleghe `vcep` e `vcep_batch`; database CACHE-07 configurato con lo stesso default/override, opzionalmente selezionabile nel costruttore. Nessun fetch. Gli altri metodi del manager non cambiano. |
| `source_registry.administrative_catalog` | La voce `clingen_vcep_variants` esiste già da CACHE-06A/07; non viene duplicata o modificata. |
| Evidence Coordinator | Nessun modulo/classe autonomo presente nel codice attivo. La route `api.variants._sample_variant_detail` coordina già le evidenze e ora aggiunge VCEP, separatamente dal calcolo di priority e dal catalogo del contesto ACMG. Nessun nuovo coordinatore creato. |
| Evidence Assembler | Nessun assembler generico verificato nel codice attivo. Il Calculator usa bridge e modelli PVS1 tipizzati; non vengono estesi e non ricevono VCEP. I moduli Workbench rimossi non sono riattivati. |
| Identità biologica | `biological_identity.allele_refs_batch` qualifica le SNV con il contratto ga2 esistente, senza normalizzatori aggiuntivi. Il ga2 già prodotto dal dettaglio viene riutilizzato soltanto quando contratto e input originale corrispondono alla variante richiesta. |
| ClinVar | `query.variant_detail`, `LocalEvidence` e il calcolo corrente di priority restano invariati. Solo un Variation ID da un risultato ClinVar `FOUND` costituisce un ulteriore segnale identificativo; non vengono importate conclusioni ClinVar nel pacchetto VCEP. |
| VCF/run store | `indexer.index_run/index_vcf/index_tsv` indicizzano alleli, call e annotazioni originali nello schema 2. I metadata variante conservano l'origine; `get_or_create_variant` non è uno store mutabile di binding a fonti esterne. Nessuna scrittura VCEP nelle run. |

Cache varianti realmente presenti: ClinVar locale a snapshot, vecchia cache
puntuale E-utilities mantenuta ma non usata dal browser corrente, frequenze
gnomAD per allele/release e cache delle proiezioni assembly. ERepo ha il suo
snapshot CACHE-07. Non esiste una cache persistente generica delle varianti
nonstatiche adatta a registrare UUID/snapshot VCEP. Le cache Gene2P e dei
trascritti hanno scope differenti e non vengono riutilizzate come contenitori
di classificazioni variante–malattia–panel.

Flusso implementato:

```text
GET dettaglio variante esistente
  -> lettura variante/annotazioni + ClinVar locale + priority esistenti
  -> identità ga2 esistente
  -> estrazione identificativi di origine associati all'allele
  -> SourceManager.vcep_batch
  -> adapter VCEP + reader CACHE-07 fissato allo snapshot
  -> clingen_vcep_evidence nel dettaglio
  -> disclosure VCEP separata nel Variant Browser
```

Il catalogo `interpretation_context` continua a usare soltanto i suoi input
precedenti. Il pacchetto VCEP non alimenta il Calculator, il motore PVS1 o
`helper_prioritization`.

## Moduli modificati

- `helper_next/core/acmg_sources.py`: deleghe locali puntuali/batch e riuso ga2.
- `helper_variants/clingen_vcep_adapter.py`: nuovo adapter specifico per la
  fonte; matching, riconciliazione dei segnali e riferimenti UUID in memoria.
- `helper_variants/clingen_vcep_local.py`: aggiunto `assertions_by_ids`;
  le query riutilizzano `_records` per caricare i figli in batch. Nessuna
  modifica a schema, builder, pubblicazione, rollback o aggiornamenti.
- `helper_next/api/variants.py`: aggiunto il pacchetto al dettaglio esistente,
  dopo il calcolo invariato di ClinVar/priority e dell'identità biologica.
- `helper_variants/web/static/variant-browser.js`: disclosure VCEP nel
  dettaglio; rendering con i componenti `detailDisclosure`/`detailCard` esistenti.
- `helper_next/web/static/index.html`: versione URL del modulo browser aggiornata.
- Test nuovi `test_clingen_vcep_integration.py`, `test_clingen_vcep_browser.py`
  e questo report. I test riusano header/fixture/cache builder già verificati.

Percorsi dei moduli relativi a `helper_next/src/` e dei test a `helper_next/tests/`.
Nessun nuovo servizio, framework, database operativo, downloader, endpoint o
modifica al Source Registry; nessun commit automatico.

## Matching e provenienza degli identificativi

Il Source Manager accetta un'identità genomica e array espliciti di
`variation_ids`, `caids`, `hgvs`. Il browser li ricava dai campi indicizzati,
senza affidarsi al blocco degli ID preparato per la sola presentazione.

- Variation ID: valore numerico positivo completo in campi con namespace
  ClinVar esplicito, oppure risultato `FOUND` del reader ClinVar corrente.
  Non si estraggono numeri da SCV/RCV, testo descrittivo o rsID.
- CAid: valore completo `CA...`, con zeri originali conservati, in campi
  tipizzati o nell'ID VCF di un sito non multiallelico.
- HGVS: espressione nucleotide esatta con accession/versione già presente.
  Il qualificatore gene fra parentesi può essere conservato se fa parte
  dell'espressione originale. Non si compongono accession e `c.` parziali,
  non si traducono nomenclature, non si usano HGVS proteici come identità
  dell'allele nucleotidico.
- Genomico: ga2 `RESOLVED`, assembly GRCh37/GRCh38, accession nucleare primaria
  e REF/ALT di una sola base. Si cerca l'espressione genomica esatta nello
  stesso indice HGVS usato da CACHE-07, senza liftover o conversione di indel.

Le INFO di sito e l'ID VCF non vengono attribuiti a un singolo ALT quando il
record originale è multiallelico. Le annotazioni usate sono quelle già
associate all'allele dall'indexer. Il solo gene non produce mai un match.
Indel/MNV/varianti complesse richiedono ID attendibili o HGVS esatti; non vengono
trasformati in SNV o normalizzati da un secondo sistema.

Segnali concordanti restituiscono l'unione delle assertion: panel, malattie,
MOI, versioni e ritiri restano separati. Più ID distinti dello stesso tipo,
identificativi sorgente incompatibili o HGVS discordanti sulla stessa
accession/versione producono `AMBIGUOUS`. L'omissione di un alias nella fonte
non è da sola una prova di discordanza; un'espressione differente sulla
stessa accession/versione lo è. Non viene scelto un risultato per gene,
classificazione, forza del criterio o presunta pertinenza clinica.

| Stato | Significato |
| --- | --- |
| `FOUND` | Assertion corrispondenti a segnali esatti concordanti nello snapshot fissato. |
| `NOT_FOUND` | Query supportata eseguita nello snapshot valido, senza risultati; oppure riuso della stessa query negativa già eseguita sullo stesso snapshot immutabile. Nessuna conclusione clinica negativa. |
| `UNSUPPORTED` | Nessun ID/HGVS supportato né SNV primaria qualificata. Non equivale ad assenza in ERepo. |
| `ERROR` | Database assente/corrotto/incompatibile o errore di lettura. Il resto del dettaglio rimane disponibile. |
| `AMBIGUOUS` | Segnali discordanti: `assertions=[]`, candidati separati in `candidate_assertions`, senza classificazione assegnata alla variante. |

`reference_status=UNVERIFIED` rimane esplicito per il matching genomico ERepo,
anche quando ga2 dispone di verifica FASTA positiva. Il risultato ga2 e la sua
provenance sono separati: un eventuale REF mismatch impedisce la ricerca
genomica e non diventa `NOT_FOUND`. Gli altri identificativi esatti possono
essere consultati indipendentemente, con il limite genomico visibile.

## Contratto delle evidenze

Campo di dettaglio: `clingen_vcep_evidence`.

```python
{
    "source_id": "clingen_vcep_variants",
    "status": "FOUND",                 # anche matching_status
    "availability": "AVAILABLE",
    "snapshot_id": "erepo-sha256:...",
    "provenance": {...},                # manifest CACHE-07
    "freshness": "SNAPSHOT",            # non una verifica live
    "match_methods": [...],
    "match_attempts": [
        {"kind": "variation_id", "value": 123, "assertion_ids": ["uuid..."]}
    ],
    "reference_status": "UNVERIFIED",   # o NOT_APPLICABLE
    "allele_identity": {...},            # ga2, quando disponibile
    "application": "INFORMATION_ONLY",
    "clinical_context_status": "NOT_SELECTED",
    "assertions": [...],
    "candidate_assertions": [],
    "reason": None,
}
```

Ciascuna assertion trasporta UUID, versione/disponibilità, CAid/Variation ID,
gene/ID, malattia/MONDO/MOI, panel/affiliation, classificazione originale,
approval/published date, `retracted` booleano o `null`, testo interpretativo,
PMID, link ufficiale/originale, guideline e versioni note.
`classification_origin=EXTERNAL_VCEP_ASSERTION` identifica la conclusione esterna.

`criteria` mantiene `code`, `status` e ordinalità originali. Il campo `strength`
è soltanto il suffisso testuale dopo il primo underscore, se presente:
`PS3_Strong` → `Strong`; `PVS1` → `None`. Non sono calcolate strength predefinite
dal prefisso ACMG, né normalizzati suffissi non standard. `met_codes` e
`not_met_codes` preservano i codici originali. `Met`/`Not Met` non attivano,
escludono o modificano alcun criterio HELPER.

Gli originali completi e le lunghe liste di alias restano nel dataset ERepo:
il dettaglio non li duplica nel database delle run o nella cache. Valori
assenti rimangono `None`/array originali; `versionsList` non ricostruisce i
contenuti storici. Per i record ritirati privi di versione in CACHE-07, la
versione rimane sconosciuta.

## Batch, cache e indicizzazione

I lookup raggruppano alias unici in SELECT indicizzate da 500 valori per tipo.
Seguono SELECT batch sui soli UUID trovati e sui relativi criteri/HGVS.
Un reader è condiviso per operazione, chiuso alla fine; nessuna connessione o
lease entra in cache. Nessun caricamento anticipato dell'intero ERepo.

Una LRU specifica di processo, limitata a 4.096 chiavi, conserva esclusivamente
gli alias interrogati e i riferimenti UUID. La chiave comprende snapshot e
insieme degli alias esatti, senza run, campione o dati clinici. I contenuti
delle assertion si rileggono dallo snapshot fissato. Un nuovo snapshot non
riusa riferimenti precedenti, inclusi i negativi; eventuali UUID mancanti dal
database selezionato sono un errore, senza fallback a dati vecchi o rete.

Non è implementata indicizzazione anticipata persistente. Nell'architettura
attuale richiederebbe binding mutabili per fonte/snapshot, migrazione del run
store e invalidazione distinta dalle annotazioni originali. Salvare UUID nei
metadata di origine della variante non fornirebbe questi requisiti e potrebbe
perdere il legame con la sorgente. Come previsto dal task, l'integrazione resta
read-only con batch efficienti; nessuna pipeline parallela o nuovo database.

La schermata già aperta non interroga periodicamente ERepo o il manifest.
Ogni riapertura richiede il dettaglio con `no-store`, apre il CURRENT locale
e sostituisce il contenuto precedente. I punteggi e la cache dell'ordine delle
varianti non dipendono da VCEP e non vengono invalidati da un suo cambiamento.

## Variant Browser

Disclosure **ClinGen VCEP — Expert Panel Classifications**, distinta da
ClinVar, nella schermata già esistente. Ogni assertion ha una propria scheda
con classificazione, panel, malattia/MONDO/MOI, gene, date, UUID/versione,
ritiro, Met/Not Met e suffissi originali, interpretazione e link ufficiali.
Matching, affidabilità del riferimento e snapshot sono espliciti.

Il ritiro `true` è marcato `RETRACTED`; `null` indica che lo stato attivo non è
stabilito. `false` è presentato come flag sorgente, non come certificazione
clinica. L'ambiguità mostra soltanto candidati non confermati e spiega che
nessuno è selezionato. Non ci sono controlli di attivazione ACMG o selezione
automatica di panel/malattia. Il testo sorgente viene inserito con `textContent`;
i link sono HTTPS e si aprono solo su azione esplicita dell'utente.

## Test e benchmark

Suite estesa: **298 passati, 1 saltato, 1 deselezionato; 27 subtest passati**.
Saltato: Chrome opt-in del Calculator PVS1. Deselezionato: controllo
architetturale del viewer già non allineato dai task precedenti, che vieta
cinque import del registry introdotti da CACHE-06A. CACHE-08 non aggiunge
import diretti `helper_next` a `helper_variants` e non modifica quel test.
Warning preesistente di deprecazione `python_multipart`.

```bash
HELPER_TEST_CLINVAR_BROWSER=1 python -m pytest -q -o faulthandler_timeout=20 \
  helper_next/tests/test_clingen_vcep_local.py \
  helper_next/tests/test_clingen_vcep_integration.py \
  helper_next/tests/test_clingen_vcep_browser.py \
  helper_next/tests/test_clinvar_integration.py \
  helper_next/tests/test_clinvar_browser.py \
  helper_next/tests/test_variant_query.py helper_next/tests/test_variants_api.py \
  helper_next/tests/test_variant_viewer.py helper_next/tests/test_acmg_context.py \
  helper_next/tests/test_acmg_pvs1.py helper_next/tests/test_acmg_mechanisms.py \
  tests/test_pvs1_calculator.py tests/test_pvs1_models.py \
  -k 'not test_variant_package_limits_helper_runtime_imports_to_existing_ga2_reader' \
  --tb=short
```

Le limitazioni AnyIO della sandbox hanno bloccato una prima esecuzione API;
la suite estesa è passata fuori sandbox, con fonti locali/simulate. I test
VCEP specifici e Chrome passano anche nel rilancio mirato in sandbox:
**20 test passati**, compreso l'ultimo controllo HGVS con qualificatore gene.
Controlli Python/JavaScript e whitespace completati.

La copertura comprende ID, HGVS, SNV/ga2 e reference non verificato anche con
FASTA verificato, REF mismatch, indel senza equivalenza inventata, assenza,
discordanza, panel/malattie multipli, ritiro/null, criteri e strength originali,
errori DB, cambio snapshot e riferimenti obsoleti, estrazione allele-specifica,
batch distinti e deduplicati, input immutati e nessuna scrittura nelle run.
Il confronto prima/dopo l'installazione della fixture VCEP mantiene identici
ClinVar, priority, identità e contesto ACMG. Le regressioni scientifiche
verificano i vettori esistenti PVS1 senza cambiare i moduli del motore.

Chrome esegue il vero componente con payload prodotti dalla route locale:
tre assertion, malattie/panel distinti, ritirata/sconosciuta, interpretazione
HTML resa come testo, criteri senza controlli di attivazione, link, stati
assente/non supportato/errore/ambiguo e sostituzione dei vecchi UUID dopo
cambio snapshot. Nessuna dipendenza da servizi online.

Benchmark sul dataset installato, in sola lettura, campionando Variation ID
**distinti** dall'indice; tempi a cache filesystem calda:

| Varianti | Primo accesso | Mediana di 3 accessi con riferimenti in cache | SQL primo / successivi |
| ---: | ---: | ---: | ---: |
| 1 | 0,717 ms | 0,568 ms | 4 / 3 |
| 100 | 10,635 ms | 9,879 ms | 4 / 3 |
| 1.000 | 117,119 ms | 112,169 ms | 11 / 9 |

Conteggi SQL relativi a matching/dettaglio, esclusa l'apertura e validazione
del reader; i tempi includono l'operazione completa. Tutti i 1.000 input hanno
restituito `FOUND`, con 1.001 assertion totali. Snapshot
`erepo-sha256:611c8dcc5900ee69f385fbe7961e5c943d4ccdc6f6872dbc95c40ea84675951f`;
dimensione e mtime del database invariati, zero rete. Ricevuta:
`/tmp/cache08/benchmark.json`. Misure locali, non una garanzia di latenza.

Il test batch su 600 SNV distinte esegue cinque SELECT complessive nella
fixture; 1.100 input duplicati richiedono sei SELECT alla prima operazione,
tre alle successive. Nessun costo proporzionale al numero di duplicati per
le interrogazioni SQL e nessun preload di tutte le assertion.

## Limiti residui e prossimi contratti

- La cache dei riferimenti è di processo e si ricrea dopo riavvio. Non è un
  archivio storico o una preindicizzazione persistente delle run.
- Gli alias accettati devono già essere associati all'allele. Sono conservativi
  il matching di HGVS, i conflitti tra namespace e l'esclusione di indel dal
  percorso genomico. Le assertion candidate non diventano risultati certi.
- Non c'è una nuova policy di aggiornamento né download VCEP durante le
  consultazioni. La pubblicazione CACHE-07 rimane invariata.
- Un futuro collegamento a un assembler/engine dovrà aggiungere un contenitore
  separato di riferimenti esterni con fonte, snapshot, UUID/versione e scope
  gene–malattia–MOI–panel. Occorrono selezione clinica esplicita e verifica
  indipendente dell'applicabilità; tali riferimenti non dovranno impostare
  automaticamente criterio, strength o conclusione HELPER.
- Un futuro task CSpec dovrà acquisire e verificare la specifica/versione
  corretta con propria provenance e vincoli di scope. Il link guideline e
  `versionsList` delle assertion non bastano a ricostruire quella specifica.

Nessun database ClinVar/Gene2P, meccanismo, regola ACMG/PVS1, pipeline VCF o
Nextflow, punteggio o politica snapshot modificati. Non eseguiti Nextflow,
suite integrale estranea al perimetro o nuovi download ERepo.
