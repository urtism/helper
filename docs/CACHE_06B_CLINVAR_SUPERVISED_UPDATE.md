# CACHE-06B — ClinVar Supervised Update Workflow

Data: 2 novembre 2026.

HELPER Next controlla la disponibilità di nuovi file ClinVar ogni sette giorni.
Il Data Sources Manager permette di confermare **Aggiorna** oppure scegliere
**Posticipa**. CHECK non acquisisce archivi completi; UPDATE li acquisisce
soltanto dopo conferma; POSTPONE modifica soltanto lo stato amministrativo.

## Audit e riuso

Consultati prima delle modifiche CACHE-04/04.1, CACHE-05, CACHE-05.1,
CACHE-05.2 e `CACHE_06A_DATA_SOURCES.md`, insieme ai componenti attivi.
Il working tree conteneva già modifiche di altri task: sono state conservate.
Nessun database operativo è stato modificato durante l'audit o le verifiche.

| Componente esistente | Riuso in CACHE-06B |
| --- | --- |
| `clinvar_local.check_for_updates` / CLI `check-updates` | Confronto MD5 dei due export NCBI; nessuna decisione fondata sulla sola data HTTP. |
| `download_sources` | Stesso downloader, controllo lunghezza, MD5/SHA-256 e parziali protetti. Aggiunti checksum attesi vincolati all'approvazione e callback di avanzamento. |
| `build_database`, `_build_database` | Stesso schema, importatore, indici, conteggi, foreign key, `integrity_check`, validazione tramite reader e pubblicazione atomica. |
| Lock della directory `.snapshots` e cleanup del builder | Estratti senza duplicazioni in `_build_session`, usata da build e dal nuovo percorso condiviso `download_and_build`. Il lock copre anche il download supervisionato. |
| CLI `download-build` | Ora richiama `download_and_build`, lo stesso percorso del worker supervisionato. Rimane un'azione CLI esplicita. |
| CURRENT/BACKUP, `_retirement_guards`, `_select_roles`, `cleanup_snapshots` | Invariati nel significato; conservano la protezione dei reader e la coppia atomica di ruoli. Usati anche per riconciliare interruzioni. |
| CLI `info`, `rollback`, `cleanup` | Conservati. Nessun pulsante rollback aggiunto. |
| `clinvar_adapter.LocalEvidence` e cache priority per `snapshot_id` | Nessuna modifica: nuovi reader vedono il nuovo CURRENT; reader esistenti terminano sullo snapshot fissato. Il cambio snapshot invalida già l'ordine della priorità. |
| Registry e API Data Sources di CACHE-06A | Mantengono ID, fonti e protezione amministrativa locale. Nuovi campi operativi soltanto per ClinVar. |
| Ricevuta JSON e lock di CHECK di CACHE-06A | Stesso percorso/nome; campi aggiuntivi per installazione e rinvio. Lo stesso lock serializza CHECK e UPDATE. |

`source_registry.py`, `clinvar_adapter.py`, query, regole/pesi di priorità,
calcolatore ACMG, reference FASTA e strutture trascrittomiche non richiedono
modifiche in questo task. Nessuna nuova implementazione ClinGen o gnomAD.

## Controllo automatico

Lo startup FastAPI crea un task leggero, senza attenderne il lavoro di rete.
Un lock di leadership per installazione ammette un solo controllo periodico
attivo, anche con più worker API. Il task controlla localmente la scadenza ogni
ora; interroga NCBI soltanto quando l'ultimo tentativo concluso risale ad almeno
sette giorni fa o manca. Anche gli errori hanno data di conclusione: la verifica
manuale resta disponibile per riprovare prima della scadenza automatica.

La data è ricontrollata dopo l'acquisizione del lock di CHECK, evitando due
richieste avviate contemporaneamente da worker diversi. CHECK già attivo o
UPDATE attivo non genera una seconda operazione. Senza installazione leggibile
non parte un'acquisizione né un'installazione iniziale implicita.

Lo stesso checker manuale di CACHE-06A richiede soltanto:

- `variant_summary.txt.gz.md5`;
- `submission_summary.txt.gz.md5`.

Il timeout rimane 15 secondi per richiesta. Un errore lascia la disponibilità
sconosciuta e visibile, senza alterare CURRENT/BACKUP. Il trigger manuale o
automatico è documentato nella ricevuta. Le richieste GET delle pagine non
avviano controlli remoti. Quando HELPER è chiuso non esiste uno scheduler esterno;
alla riapertura viene rivalutata la scadenza.

## Approvazione e rinvio

Il set dei due MD5 remoti ha un identificativo deterministico `ncbi-md5:<sha256>`.
È l'identità dei file candidati, **non una release scientifica comune**.

Aggiorna è disponibile quando l'ultimo CHECK concluso ha trovato cambiamenti,
il CURRENT confrontato coincide ancora con quello installato, l'installazione
è gestita/valida e non sono attivi altri update o builder CLI. Il frontend legge
nuovamente lo stato prima di aprire la conferma. La conferma contiene CURRENT,
entrambi i nomi/MD5 dei file, la data del controllo, il passaggio CURRENT → BACKUP,
la rimozione protetta del backup precedente e l'effetto potenziale sulla priorità.
Annullare non invia UPDATE.

Il server richiede conferma esplicita, snapshot e ID del set di checksum.
Ricava i checksum dalla ricevuta locale: il client non può approvare un set
arbitrario o un percorso di download. Se la selezione è superata risponde 409.

Posticipa conserva ID del set, data del rinvio e `remind_after` a sette giorni.
La disponibilità resta visibile e Aggiorna rimane utilizzabile. Solo l'avviso
nel pannello viene silenziato; alla scadenza o all'arrivo di un diverso set di
checksum torna visibile. Un nuovo avvio dell'app non azzera il rinvio. Non sono
state aggiunte notifiche o azioni nel Variant Browser.

## Processo di installazione

L'endpoint risponde 202 dopo aver avviato un processo Python separato, senza
attendere il download o la costruzione. `start_new_session`, descrittori separati
e lock ereditato fanno proseguire l'operazione dopo la chiusura del browser o
del processo API. Non sono introdotti servizi, code o framework di job management.

Il worker usa `download_and_build` sotto il lock esistente del builder:

1. Rilegge e confronta il CURRENT approvato.
2. Ricontrolla entrambi i checksum NCBI e li confronta con quelli approvati.
3. Esegue la verifica dello spazio prima di qualsiasi GET degli archivi.
4. Riusa il downloader; ogni sidecar viene nuovamente confrontato con la selezione
   e ogni archivio viene verificato contro il checksum approvato e la lunghezza.
5. Riusa costruzione e validazione in staging sul filesystem degli snapshot.
6. Ricontrolla CURRENT all'interno del lock di pubblicazione prima del commit.
7. Pubblica la coppia CURRENT/BACKUP con le primitive esistenti e ritira soltanto
   file non utilizzati da reader attivi.
8. Elimina gli archivi temporanei dell'operazione e registra il risultato.

File cambiati rispetto all'approvazione causano un errore che richiede nuova
verifica/conferma; non vengono installati dati diversi silenziosamente.
L'integrità gzip e strutturale resta controllata dall'importatore esistente.
Un BACKUP in uso blocca la pubblicazione senza cambiare i ruoli; il tentativo
può essere ripetuto dopo il rilascio dei reader. Il backup non viene eliminato
preventivamente per recuperare spazio. Le sole modifiche del builder riguardano
riuso del contesto di lock, vincoli di approvazione e callback delle fasi.

## Spazio e avanzamento

Le dimensioni remote sono consultate con HEAD, soltanto nel percorso UPDATE.
Non sono considerate prova di aggiornamento. Se HEAD o Content-Length non sono
disponibili, la stima usa dimensioni conservatrici del dataset corrente e degli
archivi documentati. Con `S` dimensione di CURRENT e `A` somma delle stime degli
archivi, si riservano:

- database nuovo stimato: `max(2*S, 6*A)`;
- ulteriore spazio temporaneo SQLite: la stessa quantità;
- archivi compressi: `A`;
- margine per ciascun filesystem: `max(256 MiB, S/4)`.

Le riserve sono sommate per device reale (`st_dev`) e confrontate con lo spazio
libero. Download temporanei nel percorso amministrativo e staging degli snapshot
possono risiedere su device diversi. Il processo imposta `SQLITE_TMPDIR` sulla
directory degli snapshot, compresa nella stima. Non viene promessa la dimensione
finale del dataset; esaurimenti successivi restano errori protetti dal builder.

Fasi mostrate: CHECKING, DOWNLOADING, VALIDATING_DOWNLOAD, BUILDING,
VALIDATING_DATABASE, PUBLISHING, CLEANING, COMPLETED e FAILED. Download: byte
effettivi e lunghezza dichiarata quando disponibile. Build: conteggi già emessi
dall'importatore. Nessuna percentuale globale inventata. Gli aggiornamenti dei
contatori sono limitati a circa uno al secondo, mentre i cambi di fase sono
registrati subito. Il pannello interroga lo stato ogni secondo durante operazioni
attive e ogni minuto quando visibile/inattivo, per rilevare controlli automatici;
queste GET non fanno CHECK remoti. Uscire e rientrare non perde l'operazione.

## Persistenza e recupero

Rimane la ricevuta di CACHE-06A in `$XDG_DATA_HOME/helper_next/data_sources/`,
fallback `~/.local/share/helper_next/data_sources/`, rispettando
`HELPER_DATA_SOURCES_STATE_DIR`. I campi storici di CHECK rimangono compatibili.
Sono aggiunti `update`, `postpone` e `last_successful_update`, con ID operazione,
PID informativo, snapshot/checksum approvati, fase, contatori e date/errori.
Il manifest biologico completo non viene duplicato. L'eventuale data di
completamento dell'installazione è mostrata solo se la ricevuta corrisponde
all'attuale CURRENT; la data d'importazione preesistente rimane distinta.

Scritture atomiche con fsync file/directory e breve lock per read/modify/write:
CHECK e progressi non cancellano lo stato di POSTPONE o dell'ultima installazione.
Il lock delle operazioni è ereditato dal worker e prova l'esistenza del lavoro
attivo senza affidarsi a PID riutilizzabili. La chiusura del processo libera il
lock anche dopo SIGKILL.

Startup e lettura dello stato riconciliano una ricevuta operativa rimasta attiva:
confrontano i checksum approvati con il manifest reale di CURRENT e usano
`cleanup_snapshots` per staging/snapshot abbandonati. Se il commit era già avvenuto,
il risultato viene recuperato come COMPLETED; altrimenti FAILED. Sono ripulite
soltanto le directory di download di proprietà della specifica operazione.
Reader o builder che impediscono la pulizia non vengono forzati: lo stato indica
il problema e permette di ritentare la riconciliazione nelle letture successive.
Una ricevuta amministrativa corrotta non nasconde un database biologico valido
e non autorizza nuovi download.

## API e file interessati

Gli endpoint di CACHE-06A restano disponibili. Sono aggiunti:

| Metodo e percorso | Uso |
| --- | --- |
| `POST /api/data-sources/clinvar/update` | `{snapshot_id, update_id, confirmed: true}`; avvio approvato, 202. |
| `POST /api/data-sources/clinvar/postpone` | `{snapshot_id, update_id}`; rinvio persistente senza download. |
| `GET /api/data-sources/clinvar/update/status` | Stato dell'operazione, inclusa riconciliazione. |

Tutte le route mantengono le restrizioni locali/same-origin e `no-store` di
CACHE-06A. Nessuna nuova API di installazione per le altre sorgenti.

Modifiche: `core/data_source_checks.py` e nuovo `core/clinvar_update.py` per
ricevuta/scheduler/processo; `api/data_sources.py` e `api/app.py` per API/lifecycle;
`helper_variants/clinvar_local.py` per riuso del builder e progressi; `web/static/`
limitatamente ad API helper, bootstrap e pannello Data Sources. Test aggiornati
in `test_data_sources.py`, `test_data_sources_browser.py` e nuovo
`test_clinvar_update.py`.

## Verifiche e limiti

Test offline con file gzip sintetici e URL `file://`, incluso il vero processo
separato: successo, rinvio/scadenza/nuovo checksum, approvazioni superate,
deduplicazione, avvio non bloccante, space preflight sullo stesso/diversi device,
file cambiati, MD5 errato, gzip invalido, reader CURRENT/BACKUP, builder già attivo,
fallimento di lancio, SIGKILL prima/dopo commit, pulizia e recupero, ricevuta
corrotta, fasi/contatori e invalidazione della priority senza variazioni di regole.
Chrome verifica annullamento/conferma, rinvio, byte reali e navigazione durante
l'installazione con API simulate. Le regressioni conservano i test CACHE-04/05/06A.

Esito finale: **197 test passati**, di cui 20 nel nuovo modulo del workflow.
Un warning preesistente `python_multipart`. La regressione finale è stata
eseguita fuori dalla sandbox dopo un blocco nelle notifiche asincrone
dell'executor; anche fuori dalla sandbox sono state usate esclusivamente fixture
locali, senza acquisizioni NCBI reali. Controlli sintattici Python/JavaScript e
`git diff --check` superati.

```bash
python -m pytest -q -o faulthandler_timeout=20 \
  helper_next/tests/test_clinvar_update.py \
  helper_next/tests/test_data_sources.py \
  helper_next/tests/test_data_sources_browser.py \
  helper_next/tests/test_clinvar_local.py \
  helper_next/tests/test_clinvar_integration.py \
  helper_next/tests/test_source_registry.py \
  helper_next/tests/test_gnomad_frequency.py \
  helper_next/tests/test_gene_phenotype.py \
  helper_next/tests/test_reference_validation.py --tb=short
```

Nessun aggiornamento o download ClinVar reale eseguito, nessuna modifica dei
database operativi. Il flusso completo sui dataset NCBI di dimensioni reali non
è stato eseguito in questo task. Non sono stati avviati Nextflow o la suite
completa del repository.
