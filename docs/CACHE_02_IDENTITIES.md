# CACHE-02 / CACHE-02.1 — Identità biologiche condivise

Data: **29 ottobre 2026**. Implementazione additiva rispetto al working tree
descritto in [CACHE_01_ARCHITECTURE.md](CACHE_01_ARCHITECTURE.md) e
[HELPER_STRUCTURAL_CLEANUP.md](HELPER_STRUCTURAL_CLEANUP.md).
Aggiornamento CACHE-02.1: identità degli alleli indipendente dal file FASTA;
contratti di trascritti e associazioni invariati.

## 1. File e perimetro

File introdotti da CACHE-02 e modificati da CACHE-02.1:

- [biological_identity.py](../helper_next/src/helper_next/core/biological_identity.py):
  unico modulo applicativo interessato; modifica limitata alla generazione e
  al contratto degli alleli, con qualificazione privata del contig.
- [test_biological_identity.py](../helper_next/tests/test_biological_identity.py):
  test con reference e dati sintetici, senza servizi remoti.
- `docs/CACHE_02_IDENTITIES.md`: questo report.

Nessun altro file applicativo modificato da CACHE-02.1. Nessuna variazione a cache,
schemi, colonne, ID SQLite, API, frontend, Source Manager, inferenze/confidence,
catalogo dei trascritti o PVS1. I database operativi sono stati consultati
esclusivamente in sola lettura per verificare l'assenza di riferimenti persistiti.
Gli eventuali SQLite delle fixture sono isolati nelle directory temporanee di
pytest. Nessuna dipendenza nuova, servizio, adapter PostgreSQL o migrazione.
Le altre modifiche di cleanup già presenti nel repository non fanno parte di
CACHE-02. CACHE-03 non è stato iniziato.

## 2. Funzioni esistenti riutilizzate

La ricognizione è stata effettuata prima di implementare il modulo.

| Funzione / componente | Riutilizzo o ragione per conservarla |
|---|---|
| `helper_variants.indexer.normalize_allele` | Trimming e left alignment; nessun secondo normalizzatore di alleli |
| `indexer.open_reference`, `IndexedFasta.sequence/_contig` | Apertura FASTA/.fai, accesso casuale, alias risolti contro i contig effettivamente presenti |
| `acmg_reference.reference_record/verify` | Stessa configurazione reference e verifica REF/normalizzazione/checksum già usata da HELPER |
| `helper_variants.liftover._assembly/_chromosome/ASSEMBLY_ACCESSIONS` | Vocabolario di assembly/alias e accession versionate dei cromosomi principali già presenti, senza effettuare liftover o fetch |
| `acmg_digest.digest` | JSON canonico e SHA-256 esistenti, invariati |
| `acmg_transcripts.qualify` | Verifica offline accession/versione, assembly, release, struttura e sequenze di un bundle già acquisito |
| `acmg_mechanism_normalizer.curie/allelic` | Normalizzazione lessicale di namespace e allelic requirement già applicata dal motore locale |
| `OntologyMappingRegistry.pin/lookup` | Vista coerente e read-only del mapping MONDO/OMIM/ORPHA, conservando ambiguità e provenienza |
| `store.get_or_create_variant` e PK/UNIQUE dello store | Restano gli identificativi locali dell'indice, senza conversioni o sostituzioni |
| `association_key`, `record_reference`, `matrix_digest` | Hash storici separati, lasciati integralmente invariati; non vengono ricalcolati con il nuovo contratto |

Il nuovo modulo non chiama `TranscriptReferenceProvider.get/gene_transcripts`,
`import_mondo`, refresh delle fonti o metodi di scrittura degli store.
L'uso di alcuni helper interni già presenti evita duplicazioni; un loro futuro
cambiamento dovrà preservare i vettori di compatibilità di CACHE-02.

## 3. Serializzazione e versioni dei contratti

La serializzazione resta unica. Cambia soltanto il contratto degli alleli:

- `ALLELE_CONTRACT_VERSION = "helper-genomic-allele-2"`, prefisso `ga2:`.
- `CONTRACT_VERSION = "helper-biological-identity-1"` resta invariato per
  trascritti e associazioni, compresi payload, riferimenti e prefissi.

Il payload hashato è un oggetto JSON con `contract`, `kind` e i campi
dell'identità qualificata. Si usa esattamente `acmg_digest.digest`:
`ensure_ascii=False`, chiavi ordinate, separatori `,` e `:`, `allow_nan=False`,
codifica UTF-8, SHA-256 completo in esadecimale minuscolo.
Non si usa `hash()` Python e non si concatenano stringhe biologiche libere.

| Riferimento | Prefisso | Campi dell'identità oltre a contract/kind |
|---|---|---|
| `allele_ref` | `ga2:` | assembly canonico, chromosome come accession qualificata/versionata del contig, position, reference, alternate normalizzati |
| `transcript_context_ref` | `tc1:` | namespace, accession, version, assembly, ensembl_release |
| `association_ref` | `gd1:` | gene CURIE, disease CURIE originale normalizzato lessicalmente, allelic_requirement normalizzato |

La versione è del **contratto di serializzazione**, non di un algoritmo
d'interpretazione ACMG. Normalizer/reconciliation/mapping-policy version,
confidence, timestamp, run/campione e cache path non entrano negli hash.
Il dataset/release Ensembl appartiene invece al contesto biologico del trascritto.
Checksum, nome/percorso del FASTA, esito della verifica REF e normalizzazione
non entrano nel payload genomico; restano in `reference_provenance`.

Risultato comune:

```python
{
    "contract_version": "helper-genomic-allele-2",  # solo per gli alleli
    "status": "RESOLVED",          # oppure UNRESOLVED
    "reason": "...",               # motivazione sempre esplicita
    "original": {...},              # input originale, escluso dal digest
    "identity": {...},              # esatto payload hashato, oppure None
    "allele_ref": "ga2:...",       # campo specifico della funzione, oppure None
    # eventuale contesto di verifica, escluso dall'identità
}
```

I consumer devono controllare `status` e il riferimento. Due risultati
UNRESOLVED non sono equivalenti perché entrambi hanno riferimento `None`.
Non esiste un identificativo condiviso sintetico per questi casi: rimangono
validi ID campione/variante e rappresentazione originale dello store attuale.

## 4. Alleli: `allele_refs`

Firma:

```python
allele_refs(assembly, chromosome, position, reference, alternates, *, record=None)
```

Restituisce una lista, anche per una sola ALT. `alternates` è la stringa ALT
VCF: viene separata per virgola, con ordine e `original.alt_index` 1-based
conservati. Gli altri input non vengono riscritti. `record` è il medesimo
record run/reference accettato dalle funzioni esistenti di HELPER, per esempio
con `run_config.reference_fasta`; si rispetta anche
`HELPER_ACMG_REFERENCE_CONFIG`. Nessuna risoluzione implicita via rete.

Passi applicati a ogni ALT:

1. Normalizzare assembly con l'helper esistente; posizione intera positiva,
   cromosoma esplicito, REF/ALT non vuoti e composti da A/C/G/T.
2. Qualificare il contig usando `ASSEMBLY_ACCESSIONS`: per esempio
   GRCh37/hg19 + `1`, `chr1` o `NC_000001.10` indicano `NC_000001.10`;
   GRCh38/hg38 usa invece `NC_000001.11`. La qualificazione non dipende
   dall'intestazione o dal bundle FASTA. Un'accession di cromosoma principale
   appartenente all'altro assembly è rifiutata. Se il FASTA è disponibile,
   selezionare il suo contig corrispondente fra nome/alias/accession; più alias
   presenti contemporaneamente sono ambigui e producono UNRESOLVED.
3. Controllare REF **prima** del trimming: una base d'ancoraggio errata non può
   scomparire durante la normalizzazione.
4. Applicare `normalize_allele` con reference: trimming e left alignment anche
   nelle regioni ripetute. Non scomporre una MNV in varianti indipendenti.
5. Eseguire `acmg_reference.verify` sull'allele normalizzato nel contig fisico
   selezionato. Digest FASTA, file di origine, contig fisico, versione reference,
   esito REF ed esito di normalizzazione restano solo nella provenance.
   Il payload hashato usa assembly, accession qualificata, posizione, REF e ALT.

SNV e indel completamente verificati possono essere condivisi fra run senza
includere run ID, nome campione, rsID, ClinVar ID o HGVS. Assembly diversi
producono riferimenti diversi anche usando la stessa fixture FASTA.

Senza FASTA/.fai una **SNV** con assembly riconosciuto e contig qualificabile
produce allele_ref: `reference_provenance.ref_status = "UNVERIFIED"`, digest
assente e `normalization = "SNV_NO_ALIGNMENT_REQUIRED"`. La motivazione segnala
esplicitamente che REF non è stato verificato. Il riferimento coincide con
quello della stessa SNV verificata tramite FASTA; la verifica è un attributo
dell'evidenza, non una parte dell'identità genomica.

Gli indel e gli alleli complessi senza FASTA restano UNRESOLVED, senza alcuna
falsa equivalenza fra posizioni diverse in una ripetizione. Con FASTA si
conservano controllo REF originale, trimming e left alignment esistenti:
`ref_status = "VERIFIED"`, `normalization = "REFERENCE_NORMALIZED"`.
Un mismatch originale produce UNRESOLVED e `ref_status = "MISMATCH"`, con
file/checksum e motivo conservati anche sul risultato fallito. Un checksum
configurato discordante continua a produrre errore di verifica, senza identità.

Contig alternativi o sequenze mitocondriali richiedono un'accession genomica
esplicita con versione (RefSeq genomiche NC/NG/NT/NW o accession GenBank
compatibili con il formato supportato). Versioni/accession differenti non si
fondono. `chrM`, M, MT, decoy senza accession e nomi come
`chr1_KI270706v1_random` non vengono tradotti automaticamente: rimangono
UNRESOLVED. In particolare non si applica l'assunzione che hg19 e GRCh37
implichino la stessa sequenza mitocondriale. Un'accession esplicita distingue
invece `NC_012920.1` da `NC_001807.4`, indipendentemente dal contenuto locale REF.

Assembly ignoto, posizione invalida, REF=ALT, contig assente/ambiguo nel FASTA e
alleli simbolici/breakend/CNV/SV/`*` non supportati restano UNRESOLVED con
originale e motivo. In una stringa multiallelica l'ALT non supportata non
impedisce di qualificare le altre ALT. Non si introduce alcun nuovo mapping
upstream o catalogo di reference.

## 5. Trascritti: `transcript_context_ref`

```python
transcript_context_ref(transcript, assembly, release, *, namespace="Ensembl", raw=None)
```

Accetta una accession `ENST...version` e il `raw` di un bundle Ensembl **già
acquisito**. Riusa `qualify`: devono coincidere specie, accession/versione,
assembly e release prima/dopo l'acquisizione; i controlli strutturali e sulle
sequenze restano quelli esistenti. Il risultato aggiunge `artifact_digest`
come contesto, senza incorporare il contenuto completo nell'identificativo.

Stessa accession/versione, assembly e release producono lo stesso riferimento;
cambiando versione o release il riferimento cambia. La release intera e la
relativa stringa numerica hanno lo stesso contesto normalizzato. `original`
conserva comunque il tipo/valore ricevuto e può differire fra queste chiamate.

Accession senza versione, release mancante, mismatch o bundle assente sono
UNRESOLVED. Non si apre il provider, non si cercano file latest, non si scarica
nulla e non si sostituiscono RefSeq ed Ensembl. L'unico namespace qualificato
dal percorso attuale è Ensembl; gli altri sono esplicitamente non supportati.
Poiché si riusa la qualificazione molecolare esistente, i bundle non codificanti
o incompleti che essa non accetta restano UNRESOLVED. Il catalogo attuale rimane
disponibile e invariato, senza una nuova interpretazione delle sue righe.

## 6. Associazioni: `association_ref`

```python
association_ref(gene, disease, allelic_requirement=None,
                *, verified_gene_ids=(), registry=None)
```

Il chiamante deve fornire un gene con namespace supportato e includerlo in
`verified_gene_ids`, ricavati dalla propria fonte curata/reference qualificata.
Il modulo non prova l'esistenza di un gene su un servizio remoto e non trasforma
un simbolo in HGNC. Sono accettati HGNC/NCBI_GENE numerici e ID Ensembl ENSG
stabili; HGNC è preferibile quando già verificato, senza inventare equivalenze
tra namespace. Gli ID alternativi restano distinti se non esiste un mapping
verificato a monte.

La malattia è l'anchor MONDO/OMIM/ORPHA dichiarato dalla fonte, con namespace e
identificativo numerico; nomi e numeri senza namespace sono rifiutati.
`curie` conserva gli alias lessicali esistenti, come MIM→OMIM e Orphanet→ORPHA.
Il modulo valida il formato, non la presenza attuale del termine in un'ontologia
remota: la correttezza dell'anchor è responsabilità della fonte chiamante.

`allelic` mantiene le regole esistenti: AD e `monoallelic_autosomal` condividono
lo stesso requisito; monoallelic generico, AD, AR, X-linked e UNKNOWN restano
scope differenti. Un requisito assente è UNKNOWN, senza inferire inheritance.
Le etichette non riconosciute mantengono la distinzione OTHER già prevista.

Se fornito, `registry` è il registro esistente: `pin().lookup()` restituisce
stato, alias, canonical, record di mapping e manifest. La lettura non importa
né migra dati. **Il canonical del registry non sostituisce l'anchor nell'hash**:
OMIM e MONDO rimangono riferimenti di origine distinti, anche quando un exact
mapping qualificato li collega. Il consumer può usare tale relazione con la
sua provenance, senza alterare l'identità originale quando cambia il registry.
Un mapping ambiguo resta `AMBIGUOUS_MAPPING` nel contesto e non fonde i riferimenti.
L'identità dell'associazione di origine può restare RESOLVED mentre il suo
mapping cross-ontology è ambiguo. Senza registry la mappatura è NOT_REQUESTED.

L'assenza di identificativi verificati, simboli/nomi, namespace non supportati
o formati invalidi restituisce UNRESOLVED. Non si aggiunge MAPPING_VERSION o
alcuna versione di inferenza al nuovo hash. `gene_disease_key` conserva invece
la formula storica con la relativa policy e continua a funzionare separatamente.

## 7. Compatibilità e uso nelle cache successive

Gli identificativi sono chiavi testuali indipendenti dal database. Le attuali
PK intere SQLite restano valide; nessuna colonna nuova è necessaria per
calcolare questi riferimenti in memoria. Una futura persistenza SQLite o
PostgreSQL potrà memorizzarli senza cambiare serializzazione.

Prima della sostituzione del contratto ga1 sono state verificate le importazioni
nel codice attivo: il modulo è referenziato soltanto dai test, senza consumer
o scrittori applicativi. La verifica locale **in sola lettura** ha inoltre
controllato 9 database correnti, per 47 tabelle, senza trovare alcun riferimento
`ga1:` nei campi testuali. Il perimetro include i percorsi dati predefiniti,
gli override configurati e gli indici delle run individuate tramite lo storico
e i depositi import/external; non è una scansione di supporti offline, copie di
backup o directory di run non registrate. La prima apertura in sandbox era
bloccata; il controllo è stato completato fuori sandbox con `mode=ro` e
`query_only`, senza stampare contenuti delle righe. Il riepilogo della verifica
è in `/tmp/helper-cache021-persistence-audit.json`.
Non servono migrazione o adapter ga1→ga2; nessun riferimento persistito è stato
riscritto. Le identità tc1/gd1 e gli hash storici dei meccanismi restano invariati.

Uso previsto, esclusivamente nei futuri task autorizzati:

```python
from helper_next.core.biological_identity import (
    allele_refs, transcript_context_ref, association_ref,
)

alleles = allele_refs("GRCh38", "chr1", pos, ref, alt_field, record=run_record)
tx = transcript_context_ref(accession_with_version, "GRCh38", release,
                            raw=already_acquired_bundle)
relation = association_ref(source_gene_id, source_disease_id, source_requirement,
                           verified_gene_ids=qualified_gene_ids,
                           registry=existing_ontology_registry)
```

Si indicizzano soltanto risultati RESOLVED; negli altri casi rimane il binding
locale campione/variante con la motivazione. Il raw del trascritto deve provenire
dal percorso che ha già verificato chiave/digest dell'artefatto. I riferimenti
non sostituiscono provenance, versione dell'evidenza o selezione del campione.
Per gli alleli RESOLVED significa identità genomica dichiarata sufficientemente
specificata; il consumer deve leggere `reference_provenance.ref_status` prima
di considerare REF verificato. La correzione non cambia alcuna regola ACMG.
Non è stata inserita alcuna chiamata a queste funzioni nei consumer attuali.

## 8. Test e verifiche

La suite delle identità aggiornata a CACHE-02.1 copre 63 casi, inclusi:

- Stesso allele in run differenti con ID SQL/schema invariati; assembly distinti
  e alias di assembly; alias cromosomici verificati e contig realmente distinti.
- SNV, trimming, inserzioni/delezioni equivalenti in ripetizioni con FASTA;
  stesso allele GRCh37 su FASTA con nomi/contig/checksum differenti; SNV senza
  FASTA con REF non verificato e stesso identificativo; indel senza FASTA
  non condivisi; REF mismatch anche nell'ancora eliminabile dal trimming;
  checksum configurato errato, input non supportati e multiallelici misti.
- Accession primarie/versioni/assembly discordanti, contig mitocondriali o
  alternativi con versioni distinte, decoy e alias mitocondriali non qualificati.
- Identità/versioni/release dei trascritti, qualificazione e input non mutato,
  namespace/versione/release/reference mancanti o discordanti.
- Identificativi gene-malattia verificati dal chiamante, malattie e requirement
  differenti, assenza di prove d'identità, namespace genici distinti, mapping
  qualificati e ambigui, registry assente senza creazione di DB.
- Vettori fissi dei tre riferimenti e del digest storico, indipendenza dalla
  policy mechanism, determinismo in due processi con PYTHONHASHSEED differenti.
- Rete vietata tramite patch dei socket/urlopen; generazione senza connessioni
  SQL implicite e letture del registry senza modifica del relativo file.

Esecuzione mirata: `python -m pytest -q helper_next/tests/test_biological_identity.py`:
**63 passed**, con il warning `python_multipart` preesistente.

Suite combinata su identità, indicizzazione/query/importazione, fonti/Source
Manager, contesto, meccanismi/ontology e PVS1:

```bash
python -m pytest -q \
  helper_next/tests/test_biological_identity.py \
  helper_next/tests/test_variant_store.py helper_next/tests/test_variant_indexer.py \
  helper_next/tests/test_variant_query.py helper_next/tests/test_variant_viewer.py \
  helper_next/tests/test_external_vcf.py helper_next/tests/test_source_registry.py \
  helper_next/tests/test_acmg_context.py helper_next/tests/test_acmg_pvs1.py \
  helper_next/tests/test_acmg_mechanisms.py helper_next/tests/test_acmg_mechanism_assessment.py \
  helper_next/tests/test_acmg_mechanisms_bulk.py helper_next/tests/test_acmg_ontology.py \
  tests/test_pvs1_models.py tests/test_pvs1_molecular.py \
  tests/test_pvs1_impact.py tests/test_pvs1_calculator.py
```

Risultato CACHE-02 precedente: **382 passed, 1 skipped; 185 subtests passed**,
in 44,30 secondi. Risultato CACHE-02.1: **395 passed, 1 skipped;
185 subtests passed**, in 44,24 secondi, con la medesima suite eseguita fuori
sandbox per i test HTTP locali già noti.
Il test saltato è la verifica Chrome opt-in del Calculator; nessuna verifica UI
interattiva attestata. Un warning preesistente riguarda `python_multipart`.
La prima esecuzione combinata in sandbox si è fermata dopo 165 test senza errori
fino al timeout di 120 secondi; il rilancio fuori sandbox è terminato con il
risultato sopra. La suite mirata delle nuove identità passa anche in sandbox.

Confronto SHA-256 con una manifest salvata prima della correzione CACHE-02.1:
**51 file applicativi invariati**, nei core/API, helper_variants e pvs1;
l'unico modulo applicativo modificato è `biological_identity.py`.
Verificati inoltre sintassi Python, link documentali e assenza di errori di
whitespace nei tre nuovi file. Nessun test live di fonti biologiche, job
Nextflow o suite integrale estranea al perimetro eseguiti.

## 9. Limiti dichiarati

- La reference è un input locale amministrato: assembly/versione dichiarati
  dal chiamante/configurazione non sono certificati da un catalogo remoto.
  Si verifica il contenuto REF e il digest del file effettivamente selezionato.
- Si riusa la cache checksum in memoria di `acmg_reference`, indicizzata da
  path/size/mtime/ctime. I FASTA devono essere trattati come risorse immutabili:
  una sostituzione che conservi tutti questi metadati non garantisce una nuova
  verifica dei byte nello stesso processo. Usare un nuovo percorso/versione per
  una nuova reference; CACHE-02 non modifica questo comportamento preesistente.
- Il reader/normalizzatore FASTA mantiene i suoi limiti attuali. I mapping
  primari sono quelli già dichiarati da HELPER; altri contig richiedono
  accession genomiche esplicite con versione. Il formato non certifica da solo
  l'appartenenza reale di una sequenza a un assembly: il contesto dichiarato dal
  chiamante resta un input, senza verifiche upstream implicite.
- Namespace e formati supportati sono volutamente circoscritti a quelli già
  utilizzabili nei percorsi ispezionati. Un gene ID deve essere verificato a
  monte; la validazione sintattica da sola non dimostra esistenza o equivalenza.
- L'identità del trascritto non è un digest scientifico del contenuto: una fonte
  che cambiasse contenuto sotto lo stesso contesto richiederebbe gestione delle
  revisioni/provenance nelle cache successive.
- Non è implementato alcun uso di questi riferimenti in Source Manager, refresh,
  prefetch, persistenza delle evidenze o valutazione ACMG. Questo preserva il
  comportamento attuale e conclude esclusivamente CACHE-02.
