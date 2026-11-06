# CACHE-05.2 — Validazione preventiva della reference FASTA

Data: **30 ottobre 2026**. Nessun avvio di CACHE-06.

## 1. Audit completato prima delle modifiche

Letti CACHE-02/02.1, CACHE-04/04.1, CACHE-05 e CACHE-05.1; analizzati
`acmg_reference`, `biological_identity`, `clinvar_local`, `indexer`, la CLI e
le dichiarazioni reference in `configs/tools_cfg/`. Conservati i due moduli
reference/identità iniziali in `/tmp/helper-cache052/before-source/`.
Le numerose modifiche preesistenti del working tree sono state preservate.

File del task: nuovo `core/reference_validation.py`, integrazione in
`core/acmg_reference.py` e `core/biological_identity.py`, snapshot FAI e chiusura
su errore in `helper_variants/indexer.py`, sottocomando in `helper_next/cli.py`,
nuovi `tests/test_reference_validation.py` e
`scripts/benchmark_reference_validation.py`, questo report. Nessuna modifica
applicativa a `clinvar_local.py`, query, motore priority o moduli scientifici PVS1.

| Operazione esistente | Percorso e costo |
|---|---|
| Esistenza FASTA/FAI | `indexer.open_reference`: path della run, poi `tools_config[build].fasta`; entrambi file presenti, FASTA non compresso |
| Assembly | Alias GRCh37/hg19 e GRCh38/hg38 qualificati tramite `_assembly`; accession primarie/versioni da `ASSEMBLY_ACCESSIONS`; non inferito dal nome del file |
| Configurazione | `acmg_reference.reference_record`: override `HELPER_ACMG_REFERENCE_CONFIG`, con `fasta`, `version` esplicita e `sha256` opzionale; altrimenti record storico invariato |
| Apertura FASTA | `IndexedFasta`, handle binario con seek; non carica l'intero genoma in RAM |
| Lettura FAI | Piccolo indice letto alla costruzione del reader, riusato nel batch |
| SHA-256 | `acmg_reference._checksum`, chiamato dalla qualificazione ga2 e dal verificatore autonomo; legge **tutti** i byte su cache miss |
| Checksum atteso | Confronto con `config.sha256`; richiede un digest effettivamente acquisito, non una dichiarazione di verifica |
| REF originale e normalizzato | Accesso casuale alle basi richieste; entrambi i controlli restano attivi |
| Trimming e left alignment | `indexer.normalize_allele`; accessi locali, anche nelle ripetizioni, senza scansione del FASTA |

La LRU SHA esisteva già, con durata limitata al processo e chiave
path/size/mtime_ns/ctime_ns. CACHE-05.1 riusava i reader nel batch, ma in un nuovo
processo il primo SHA richiedeva ancora circa 6,17 secondi. Nessuna delle altre
operazioni elencate richiede di rileggere integralmente la reference.

La run reale seleziona `ucsc.hg19.fasta`, versione `hg19`, **3.199.905.909 byte**;
FAI da 3.534 byte. La dichiarazione hg38 dei tools punta invece a un `.gz`:
rimane indisponibile per questo reader finché non viene fornito un FASTA
non compresso con FAI. Non sono cambiate le configurazioni delle run.

## 2. Validazione preventiva e manifest

Nuovo modulo `helper_next.core.reference_validation`; nessun database o servizio.
L'amministratore esegue il comando durante installazione/configurazione e dopo
ogni aggiornamento della reference, senza aprire un campione.

La prima validazione scorre il FASTA una volta, calcola SHA-256 e ricostruisce
indipendentemente nomi, lunghezze, offset e geometria delle righe di tutti i
contig. Confronta la geometria con il FAI; rifiuta FASTA malformati, contig vuoti
o duplicati, sequenze non IUPAC, righe irregolari e indici discordanti/duplicati.
Confronta il checksum atteso quando configurato e registra anche SHA-256 del FAI.
Controlla prima e dopo le identità dei file e degli handle. Una verifica fallita
non pubblica un risultato positivo e non sostituisce un precedente manifest.
La scansione strutturale completa della copia reale da 3,2 GB ha richiesto
**74,933 s**, separati dai tempi di consultazione: comprende controlli su ogni
riga e non soltanto il digest da circa sei secondi. Non viene ripetuta
automaticamente all'avvio o durante l'apertura dei campioni.

Destinazione predefinita:
`$XDG_DATA_HOME/helper_next/reference_validation/`, oppure
`~/.local/share/helper_next/reference_validation/`.
Override: `HELPER_REFERENCE_VALIDATION_DIR`. Non vengono scritti sidecar nella
directory del FASTA, né modificati run, configurazioni o indici VCF.

Ogni JSON è identificato da SHA-256 di `[assembly, versione, path FASTA canonico]`.
Il digest del nome è soltanto una chiave locale, distinta dall'hash del genoma.

| Campo | Significato |
|---|---|
| `schema` | `helper-reference-validation-1` |
| `status`, `verified_at` | `verified` solo dopo scansione completa conclusa, timestamp UTC |
| `assembly`, `version` | Assembly canonico e versione configurata/della run |
| `trust` | `managed-immutable-v1` solo con esplicito `--managed-immutable`; altrimenti `full-check-only` |
| `files.fasta`, `files.fai` | Path canonico, device, inode, size, mtime_ns, ctime_ns per ciascun file |
| `digest` | SHA-256 effettivamente calcolato del FASTA |
| `expected_sha256` | Checksum atteso della configurazione, eventualmente assente |
| `fai_verified`, `fai_sha256` | Geometria verificata contro FASTA e checksum del FAI |

Pubblicazione: temporaneo univoco nella stessa directory, file con permessi
0600, flush/fsync, `os.replace`, fsync directory. Directory nuova con permessi
0700. Reader e writer concorrenti vedono un manifest completo precedente o
successivo; i temporanei non sono candidati alla lettura. Writer concorrenti
possono ripetere il lavoro, senza lock persistenti o infrastrutture aggiuntive.

## 3. Condizioni del percorso rapido

La consultazione rimane read-only. Dopo la selezione della reference e l'apertura
del reader, `reference_checksum` cerca il manifest e richiede:

1. Schema/stato/formato validi, FAI verificato, checksum registrato valido.
2. Esplicita precedente adesione al modello `managed-immutable-v1`.
3. Stessi assembly, versione e metadati di **entrambi** i file.
4. Identità del FASTA aperto coincidente con il path attuale; identità del FAI
   coincidente con quella del file effettivamente letto dal reader.
5. Manifest e directory appartenenti all'utente corrente, senza scrittura di
   gruppo/altri. Il checksum registrato deve coincidere con quello atteso oggi,
   quando presente nella configurazione.

Solo allora si riusa il digest precedente. L'accesso ai piccoli intervalli REF,
la qualificazione dei contig e la normalizzazione restano quelli esistenti.
La provenance restituita è identica: nessun nuovo campo nel contratto ga2.

Manifest assente, parziale, corrotto, non fidato, relativo ad altro assembly o
versione, oppure FASTA/FAI modificati: si torna alla verifica SHA esistente,
senza scrivere un manifest durante l'apertura. La LRU di processo aggiunge
device/inode per distinguere anche sostituzioni allo stesso path.
Un cambio osservato durante apertura o checksum genera errore esplicito.
La modifica del FAI invalida il manifest anche se il FASTA è invariato; nel
fallback resta la semantica preesistente, non si certifica nuovamente il FAI.
Il comando esplicito controlla invece l'intera corrispondenza FASTA/FAI.

## 4. Comandi operativi

Con `HELPER_ACMG_REFERENCE_CONFIG` già impostata:

```bash
PYTHONPATH=helper_next/src python -m helper_next.cli reference-verify \
  --assembly hg19 --managed-immutable

PYTHONPATH=helper_next/src python -m helper_next.cli reference-verify \
  --assembly GRCh37 --check

PYTHONPATH=helper_next/src python -m helper_next.cli reference-verify \
  --assembly GRCh37 --force --managed-immutable
```

Disponibile anche come `helper-next reference-verify`. Per un record storico
aggiungere `--record /percorso/record.json`: oggetto contenente `run_config`
con `reference_fasta` e `reference_version`, oppure il record completo esistente.
La configurazione reference esterna conserva la precedenza già prevista.

`--check` controlla l'idoneità al riuso senza leggere tutto il FASTA, con exit 1
se occorre validare. `--force` forza una scansione reale, ignorando manifest
e LRU; non è combinabile con `--check`. Senza `--force`, un manifest già idoneo
viene riusato anche dal comando. La prima verifica senza `--managed-immutable`
registra un risultato completo, ma non abilita il percorso rapido. Per revocare
l'adesione si può eseguire `--force` senza `--managed-immutable`, oppure rimuovere
il manifest. Non esiste verifica integrale obbligatoria all'avvio di HELPER.

**Il primo caricamento veloce in un nuovo processo richiede una precedente
validazione esplicita con `--managed-immutable`, nello stesso contesto utente e
directory manifest usato da HELPER.** Le vecchie run non richiedono migrazione.

## 5. Benchmark sulla run reale

Run `20261015_Run_723_CancerHS2`: 2.609 varianti, 10 campioni, 7.996 righe.
Snapshot ClinVar invariato:
`composite-sha256:da8e890d1ad7950bb61fa74218dcb86a82629d6c3ddaba76d0e8af08446038a7`.

Metodo CACHE-05.1: copia temporanea dell'indice clinico, rifiuto di WAL attivo,
fingerprint size/mtime/SHA sorgente prima/dopo; ClinVar read-only. Pagine reali
da 200 righe; il calcolo globale della priority precede la paginazione. Prima
pagina calda con LRU dell'ordine svuotata; pagina successiva con ordine riusato.
Socket e trasporti HTTP vietati. Cache filesystem non svuotata.

Tre processi nuovi per ciascun lato. Il controllo ripristina soltanto i due
moduli/funzioni reference/ga2 salvati prima del task; adapter/query e reader
sono gli stessi su entrambi i lati. I fingerprint adapter/query coincidono
in tutte le prove. Mediane:

| Operazione | CACHE-05.1 pubblicato | Prima controllato | Dopo, manifest precedente |
|---|---:|---:|---:|
| Prima pagina, primo accesso del processo | 6,526 s | 6,510 s | **0,350 s** |
| Prima pagina, reference già calda nel processo | 0,334 s | 0,334 s | 0,333 s |
| Pagina successiva | 0,115 s | 0,115 s | 0,115 s |
| SHA completo alla prima apertura | ~6,17 s | 1 chiamata / 6,164 s | **0 chiamate / 0 s** |
| HTTP / tentativi di rete | 0 | 0 | **0** |

Riduzione della mediana del primo accesso: circa **94,6%**. Il percorso rapido
si avvicina al tempo caldo precedente; la differenza della mediana della pagina
successiva è circa 0,8 ms. Una misura separata con codice nuovo e manifest assente
richiede **6,521 s**, con un SHA da **6,175 s**: il costo non è stato nascosto
o eliminato nei casi senza verifica affidabile.

La verifica reale ha creato il manifest esclusivamente in
`/tmp/helper-cache052/receipts/`: non è stata installata una dichiarazione di
fiducia nel profilo operativo dell'utente. Per usarlo in HELPER occorre scegliere
la stessa directory o validare nel percorso predefinito con i comandi sopra.

I casi di modifica e checksum errato sono misurati separatamente, senza cambiare
il FASTA installato: per il primo è stata validata una copia temporanea completa,
poi modificata una sola maiuscola di una base, a size e sequenza biologica
invariati. `--check` ha restituito exit 1; l'apertura ha ricalcolato il digest
anziché riusare il precedente. Il secondo usa il FASTA installato in sola
lettura con un override di configurazione temporaneo contenente SHA atteso errato.
I tempi di questi controlli sono singole misure, non mediane delle tre coppie.

| Stato della reference | Prima pagina | SHA completi / tempo SHA | Esito |
|---|---:|---:|---|
| Mai verificata | 6,521 s | 1 / 6,175 s | Fallback completo, consultazione normale |
| Verificata in una sessione precedente | 0,350 s (mediana) | 0 / 0 s | Manifest riusato |
| Modificata dopo la verifica, copia temporanea reale | 6,662 s | 1 / 6,316 s | Manifest invalidato; nuova provenance |
| Checksum atteso errato, FASTA reale | 6,456 s | 1 / 6,174 s | Verifica fallita, qualificazione/matching rifiutati |

La minore dimensione dei payload nel caso di checksum errato deriva dall'assenza
di evidenze qualificate: quel tempo non è un miglioramento del percorso normale.
Anche i digest della copia modificata differiscono per path/digest della
provenance, come previsto; non sono usati per la prova di equivalenza della
reference invariata. La copia FASTA temporanea viene rimossa dopo le misure.

## 6. Equivalenza dei risultati

Identici prima/dopo, in tutti i confronti sulla reference invariata:

| Output integrale | SHA-256 canonico |
|---|---|
| 2.609 evidenze, inclusi identità ga2 e provenance | `f4b32131c40928cca40112bbd6a1aa80c6175f2418bb4877c75c573434bc79a8` |
| 7.996 righe in ordine per campione, inclusi punteggi/componenti | `6cc95fdf3da27898198bd3e3a98ad645ca4adb58a48e7dfec861ac940efabbc2` |
| Prima pagina | `51b0b5a8c27c7ae8470142a710dd73dd569785e364cba51b2fe745f6ca81cd13` |
| Pagina successiva | `81926de329966c1e0566eaafb8c748d6bc25ab7d4d04b28c8afdacde6db08a7d` |

Payload prima pagina invariato: **1.832.949 byte**. Non sono cambiate formula
priority, regole ACMG/PVS1, schema/dataset ClinVar, normalizzazione, accession
o contratto ga2; nessuna modifica a retention CURRENT/BACKUP o indici VCF.

## 7. Test e verifiche

Regressione estesa: **647 passed, 2 skipped, 185 subtests passed**, in 61,16 s.
Include ClinVar locale/provider/integration, API/viewer, registry, priority,
ga2, indexer/store/query, gnomAD, contesto ACMG, meccanismi/ontology e PVS1,
calcolatore e fixture molecolari. XML: `/tmp/helper-cache052/regression.xml`.

Suite finale della nuova validazione: **40 passed**; i 33 casi iniziali sono
anche nella regressione estesa, sette ulteriori casi verificano FASTA multilinea,
CRLF, input FASTA malformati e primi writer in quattro processi concorrenti.
XML: `/tmp/helper-cache052/reference-tests-final.xml`.

Coperti prima scansione/manifest, riuso in processo nuovo con checksum vietato,
entrambi gli assembly/alias, SNV/indel e mismatch con risultati identici,
modifica a pari size/mtime ma ctime diverso, sostituzione per inode, cambio
symlink, FAI modificato/sostituito/errato, checksum atteso errato, manifest
assente/corrotto/parziale/altro assembly/versione, permessi non fidati,
dichiarazione config priva di verifica, receipt senza adesione al modello,
force, CLI, interruzioni, chiusura reader anche su errore FAI, cambi durante
la scansione, pubblicazione atomica e commit fallito senza perdita del precedente.

Eseguiti compileall mirato e `git diff --check`. La regressione in sandbox è
stata interrotta sul blocco AnyIO locale già noto; il rilancio autorizzato
fuori sandbox è terminato correttamente. Saltati soltanto i due controlli
Chrome opt-in ClinVar/PVS1; warning preesistente `python_multipart`.
Nessun browser interattivo, job Nextflow o servizio biologico live eseguito.

## 8. Riproduzione e modello di fiducia

Artefatti in `/tmp/helper-cache052/`: sorgenti iniziali, `before-outputs.json`,
`control-before-1..3.json`, `verified-1..3.json`, `unverified.json`, `summary.json`,
`modified.json`, `wrong-checksum.json`, metadati della modifica e della verifica
preventiva, manifest e XML. Il nuovo benchmark riusa la raccolta esaustiva CACHE-05.1:

```bash
PYTHONPATH=helper_next/src python scripts/benchmark_reference_validation.py \
  --database /percorso/run/results/VARIANT_VIEWER/variants.sqlite \
  --manifest-dir /percorso/manifest-validati --output /tmp/verified.json
```

Per il controllo aggiungere
`--baseline-source /tmp/helper-cache052/before-source`; per il caso mai verificato
scegliere una directory manifest assente. Eseguire ogni prova in un processo
nuovo. Gli artefatti di confronto trattengono tutte le righe per calcolarne i
digest: questa memoria è della verifica, non una cache aggiunta all'applicazione.

I metadati filesystem **non sono una prova crittografica del contenuto**.
`--managed-immutable` è un impegno operativo esplicito: reference e FAI sono
gestiti da amministratori fidati, non riscritti durante le consultazioni, e gli
aggiornamenti modificano identità/metadati e richiedono una nuova validazione.
Anche tutti gli utenti/gruppi con diritto di scrittura sui file e le directory
di origine devono essere fidati. Il manifest privato è una ricevuta locale
fidata, non firmata e non resistente a manipolazioni da parte dell'utente stesso.

Filesystem che non forniscono inode/timestamp affidabili, ripristini di snapshot
che possono riprodurre tutte le identità, writer concorrenti non coordinati,
alterazioni ostili dei metadati o corruzione silente del supporto non soddisfano
questo modello. In tali ambienti non usare l'adesione `managed-immutable`:
conservare il percorso completo e usare `--force` per un nuovo controllo reale.
Non si promette il rilevamento di corruzione silente senza lettura del contenuto.

Assembly/versione restano dichiarazioni qualificate della configurazione:
la scansione non deduce da sola l'assembly biologico. Un checksum atteso fidato
certifica il bundle atteso; senza checksum atteso si registra l'integrità del
bundle locale selezionato, con gli stessi limiti precedenti. REF e left alignment
restano necessari anche dopo una verifica preventiva riuscita.
