# CACHE-06A — Data Sources Manager

Data: 2 novembre 2026.

Il menu principale di HELPER Next include **Data Sources** (`#data-sources`).
Il pannello è indipendente da campioni, Variant Browser, dettaglio variante e
calcolatore ACMG. Non acquisisce dataset durante l'apertura. Le informazioni
amministrative sono disponibili soltanto tramite i nuovi endpoint locali.

## Audit preliminare

Consultati CACHE-01, CACHE-02, CACHE-03, CACHE-04, CACHE-05, CACHE-05.1 e
CACHE-05.2 e le rispettive implementazioni nel working tree, già contenente
modifiche di altri task. L'audit non ha costruito, aggiornato o ripulito database.
Le informazioni seguenti descrivono i provider effettivi: il pannello verifica
la presenza dei relativi artefatti nella configurazione dell'installazione.

| Sorgente | Persistenza e metadati realmente disponibili |
| --- | --- |
| ClinVar | `clinvar_local`: SQLite immutabili e ruoli CURRENT/BACKUP; manifest `release` con snapshot composito, importazione, file originali, checksum/date quando conservati, conteggi e validazione. Nessuna release scientifica comune dedotta dalla data d'importazione. |
| ClinGen VCEP Variants | Nessun importatore o dataset locale nel codice attuale. Sorgente distinta, non installata, con collegamento al [repository ufficiale](https://erepo.clinicalgenome.org/evrepo/). Nessuna acquisizione o classificazione aggiunta. |
| gnomAD genomes | `gnomad_frequency`: cache SQLite puntuale; release salvate nelle righe, ultima acquisizione; dataset/assembly configurati separati dalle release presenti. Nessun checker di release globale. |
| GenCC / Gene2Phenotype / HPO / ClinGen Dosage / Orphadata | `gene_phenotype`: indice SQLite condiviso, metadati d'importazione/URL, conteggi distinti; ETag e Last-Modified soltanto per GenCC. Nessuna release globale inventata. Un export opzionale non è installato solo perché esiste il database condiviso. |
| ClinGen Gene–Disease | Può contribuire attraverso i submitter GenCC; non è un dataset autonomo importato da HELPER. Distinto esplicitamente da Dosage e dalle classificazioni VCEP. |
| gnomAD constraint | Tabella puntuale nell'indice gene–disease. La vecchia etichetta descrittiva `v4.1.2` del catalogo browser non diventa una versione verificata nel pannello. |
| Gene2P mechanisms | `MechanismStore.statistics()` in sola lettura; matrici, snapshot ed evidenze derivate. Nessuna modifica a inferenza, ontologie o TTL. |
| Gene Struct | JSON `TranscriptReferenceProvider`: release/assembly/chiavi e data di acquisizione degli artefatti; release configurata distinta da quelle presenti. Inventario dei metadati, senza ricalcolo delle strutture o nuova validazione biologica. |
| FASTA | Dichiarazioni di `HELPER_ACMG_REFERENCE_CONFIG` tramite `reference_record`, altrimenti configurazioni GRCh37/GRCh38 e alias nel file Tools esistente. Disponibilità FASTA/FAI e ricevuta riutilizzabile di CACHE-05.2. Nessun hash completo o validazione implicita durante la lettura. |
| VEP | Versioni e percorsi dichiarati in `tools_cfg/tools.cfg`, senza eseguire tool o certificare installazioni. `annotation_releases` e risorse statiche effettive rimangono negli indici delle singole run, non vengono aggregate come release globali. |
| PanelApp / NCBI Variation / ACMG SF | Stato dai reader esistenti; cataloghi per pannello, cache delle proiezioni e snapshot inclusi nell'applicazione, rispettivamente. |

I valori sconosciuti rimangono `null`. Le date di acquisizione non sono date di
revisione scientifica. Le informazioni per run non richiedono né causano
l'apertura di indici clinici nel nuovo pannello.

## Implementazione e API

`helper_variants/source_registry.py:administrative_catalog` presenta una vista
amministrativa separata dal contratto storico `catalog()` usato dal browser.
Gli identificativi delle fonti già presenti sono conservati; ClinGen VCEP usa
`clingen_vcep_variants`. Le richieste per una singola fonte non inventariano
tutte le altre cache, anche durante il polling.

`clinvar_local.installation_status()` coordina i ruoli con il lock di
pubblicazione e consulta i manifest con `ClinVarLocal`. CURRENT/BACKUP e la
retention restano invariati. I reader gnomAD e gene–disease usati per lo stato
aprono ora esplicitamente SQLite in modalità `ro`, senza inizializzazioni.

| Metodo e percorso | Comportamento |
| --- | --- |
| `GET /api/data-sources` | Inventario locale e ultimo esito ClinVar. |
| `GET /api/data-sources/{source_id}` | Dettagli della fonte; 404 per ID inesistente. |
| `POST /api/data-sources/clinvar/check` | Accetta la verifica esplicita con 202; riusa quella già attiva. |
| `GET /api/data-sources/clinvar/check` | Stato dell'ultima verifica. |

Le fonti senza checker non espongono un pulsante di verifica e rispondono 400
alla richiesta di controllo. Tutte le risposte amministrative usano `no-store`.
`update_supported` indica il supporto alla **verifica**, non all'installazione.

L'app esistente non ha autenticazione o ruoli. Le nuove route richiedono peer
loopback, Host locale e, quando presente, Origin coincidente; rifiutano richieste
browser cross-site. Sono testati IPv4 e IPv6. Non è stata aggiunta un'autenticazione
globale né modificata la politica degli endpoint esistenti. L'accesso remoto
amministrativo e il funzionamento attraverso proxy richiederanno una politica
di autenticazione esplicita; il pannello attuale è per l'app locale.

## Verifica manuale ClinVar

Il click avvia un thread limitato alla funzione esistente `check_for_updates`,
con timeout di 15 secondi per richiesta, soltanto sui due piccoli `.md5` NCBI.
Il reader mantiene fissato lo snapshot durante il confronto. Nessun download
dei dataset completi e nessuna pubblicazione di database.

Un lock `flock` per installazione impedisce duplicati anche fra processi API.
L'esito viene scritto atomicamente, separato dai database biologici, in
`$XDG_DATA_HOME/helper_next/data_sources/` (fallback `~/.local/share`), con
override `HELPER_DATA_SOURCES_STATE_DIR`. File temporanei con permessi 0600;
directory creata 0700. Il nome dipende dal percorso configurato del database.

La ricevuta conserva snapshot confrontato, data dell'ultimo tentativo concluso,
checksum remoti/locali, esito ed eventuale errore. Il riavvio conserva gli esiti;
un check interrotto viene mostrato come errore e può essere ripetuto manualmente.
Un risultato riferito a un diverso CURRENT non afferma disponibilità o assenza di
aggiornamenti per il nuovo snapshot. Un errore remoto lascia disponibilità
sconosciuta e rende visibile l'errore, senza alterare il dataset installato.

La pagina rimane navigabile durante il controllo e interroga lo stato solo
mentre è visibile e una verifica risulta attiva. Il polling non avvia controlli
remoti. Non ci sono scheduler, installatori, pulsanti Aggiorna fittizi o import
ClinGen anticipati. CACHE-06B potrà leggere le stesse ricevute e aggiungere le
azioni supervisionate; CACHE-07 resta responsabile dell'importazione VCEP.

## Verifiche

Test offline con snapshot sintetici temporanei: inventario assente/corrotto,
CURRENT/BACKUP e lettura senza modifiche, release conosciute/configurate,
fonti opzionali, ricevute FASTA e invalidazione senza hashing, accesso locale e
rifiuto remoto/cross-origin, fonti non supportate, verifica non bloccante,
deduplicazione, errori/timeout, persistenza e cambio snapshot.

Test Chrome con shell e moduli JavaScript reali, API simulate: menu principale,
indipendenza dal browser, dettagli/BACKUP, link ufficiale VCEP, assenza di azioni
non supportate, rendering testuale dei metadati, navigazione durante la verifica
e polling senza ulteriori POST. Regressioni mirate su ClinVar locale e integrazione,
registry storico, gnomAD, gene–disease e validazione reference; controllo sintattico
JavaScript e `git diff --check`.

Esito finale: **177 test passati**, incluso Chrome. Un warning preesistente di
deprecazione `python_multipart`. La suite mirata è stata rieseguita fuori dalla
sandbox dopo errori sui socket che impedivano Chrome e le notifiche del threadpool
ASGI; le risposte remote sono rimaste simulate anche in questa esecuzione.

```bash
python -m pytest -q -o faulthandler_timeout=20 \
  helper_next/tests/test_data_sources.py \
  helper_next/tests/test_data_sources_browser.py \
  helper_next/tests/test_clinvar_local.py \
  helper_next/tests/test_clinvar_integration.py \
  helper_next/tests/test_source_registry.py \
  helper_next/tests/test_gnomad_frequency.py \
  helper_next/tests/test_gene_phenotype.py \
  helper_next/tests/test_reference_validation.py
```

Nessuna prova con download reali, nessun aggiornamento/installazione su dati
operativi, nessuna esecuzione Nextflow o modifica delle cache biologiche locali.
La suite completa del repository non è stata eseguita: i controlli sono limitati
ai moduli coinvolti e alle regressioni direttamente pertinenti.
