# VSC — Catalogo condiviso delle varianti e consultazione scalabile

Data: 6 novembre 2026. Stato: progetto eseguibile; implementazione da avviare.

## 1. Obiettivo e condizioni di completamento

Registrare una sola volta identità ed evidenze riutilizzabili di una variante,
collegandole alle occorrenze nei campioni e nelle analisi. Consultare pannelli,
esomi e genomi senza ripetere acquisizioni valide, ricalcolare Priority a ogni
interazione o trasferire milioni di righe al browser.

Il task è completo quando:

- alleli equivalenti di run diverse condividono record ed evidenze compatibili,
  anche dopo il riavvio;
- apertura di una vista pronta, filtri, ordinamento e pagine eseguono soltanto
  letture locali, senza scoring, normalizzazione o acquisizioni;
- una nuova tabella diventa visibile dopo il completamento della preparazione;
  score, dettaglio e fonti sono riferiti alla stessa generazione;
- memoria e risposte restano limitate con cinque milioni di varianti per campione;
- import, acquisizioni e pubblicazione sono idempotenti e riprendibili;
- spazio e tempi vengono misurati per alleli distinti, annotazioni versionate
  e occorrenze nei campioni, con benchmark riproducibili.

Le formule Priority, i file sorgente e i contratti API attuali restano invariati.
Le nuove API sono additive. Il task non include un download completo automatico
di gnomAD né la pubblicazione automatica di osservazioni in una coorte clinica.

### Vincolo di conservazione funzionale

Requisito dell'utente, applicabile a tutte le fasi: correggere le incoerenze
soltanto se si conservano le funzionalità e si ottimizza il processo. Un
meccanismo esistente può essere sostituito soltanto quando l'alternativa offre
qualità equivalente, verificata prima del passaggio.

Per ogni modifica documentare funzione attuale, incoerenza riprodotta,
comportamento sostitutivo, beneficio e prove di equivalenza. Il beneficio può
essere riduzione di latenza, memoria, disco, richieste, scritture o lavoro
operativo di verifica/rielaborazione; va dimostrato, non presunto dal refactor.
Una correzione priva di beneficio verificato o di sostituto equivalente viene
rinviata e registrata, senza diventare un requisito che blocca tutto il task.

Conservare filtri, ordinamenti, ricerca dei candidati, dettagli, provenance,
spiegazioni Priority, esportabilità e accesso ai risultati completi. La
paginazione cambia il trasferimento, senza troncare l'insieme consultabile.
Nessun controllo viene rimosso o disabilitato per rispettare un benchmark.
L'equivalenza riguarda anche input incompleti, errori, aggiornamenti e riavvii;
non soltanto il caso ideale. Mantenere il percorso esistente finché il nuovo
non supera le verifiche pertinenti.

## 2. Componenti da riutilizzare

| Componente | Base disponibile e limite |
| --- | --- |
| `helper_variants/store.py` | Varianti, annotazioni e chiamate separate; store `run` e `cohort`. Il supporto allo schema cohort non implica un catalogo globale già popolato. |
| `helper_variants/indexer.py` | Import a lotti, ALT e provenance; ID SQL locali, normalizzazione non uniforme in tutti gli indici storici. |
| `core/biological_identity.py` | Contratto `ga2`, contig qualificati, controllo REF e normalizzazione; usare `checksum_reference=False` nel percorso di preparazione interattiva. |
| Provider gnomAD, ClinVar/VCEP Local e gene-malattia | Proprietari delle rispettive fonti e acquisizioni; nessun secondo provider parallelo. |
| `helper_variants/acquisition.py` | Single-flight nel processo; da estendere con coordinamento durevole fra processi. |
| `helper_variants/query.py` | Contratto tabella e scoring esistenti; oggi il riuso dell'ordine può ancora ricostruire righe e punteggi. |
| `variant_detail_cache.py`, `detail_transport.py` | Conservare rivalidazione e trasporto compatto; legare i dettagli alla vista selezionata. |
| `variant-browser.js` | Modalità completa locale per dataset piccoli, rendering virtuale e aggiornamenti parziali; pagine per dataset grandi. |

Riferimenti: [architettura cache](CACHE_01_ARCHITECTURE.md),
[identità](CACHE_02_IDENTITIES.md), [roadmap](VARIANT_PLATFORM_TODO.md),
[caricamento attuale](SAMPLE_PRIORITY_LOADING.md),
[dettagli](VARIANT_DETAIL_LOADING.md).
Le sezioni storiche dei documenti vanno confrontate con il codice attivo, senza
ripristinare consumer o comportamenti rimossi.

## 3. Identità, condivisione e contesto

### 3.1 Identità condivisa

Usare l'`allele_ref` di `helper-genomic-allele-2`, con interi SQL nei join.
La stringa `ga2` viene memorizzata una volta per allele, non in ogni occorrenza.

- Assembly diversi restano distinti; una proiezione è una relazione versionata
  fra due alleli, non un merge implicito.
- Alias e indel equivalenti sono riconciliati dal normalizzatore esistente,
  non tramite rsID, HGVS o posizione soltanto.
- Le SNV qualificate senza FASTA conservano REF `UNVERIFIED`, come previsto
  dal contratto; non vengono promosse a sequenze verificate.
- `UNRESOLVED` conserva ID locale e causa. Due riferimenti nulli non sono
  un'identità condivisa.
- `*`, simbolici e alleli non supportati restano tracciabili nelle origini e
  nei conteggi; non entrano nei lookup A/C/G/T e non bloccano gli altri alleli.
- Qualificazione e lettura degli intervalli REF avvengono durante import o
  preparazione, in batch. Nessun checksum integrale FASTA nel browsing.

### 3.2 Proprietà dei dati

| Ambito | Informazioni |
| --- | --- |
| Allele | Assembly, contig qualificato, posizione, REF/ALT normalizzati, tipo. |
| Allele + bundle di annotazione | Trascritti, conseguenze, HGVS e predittori, con release e parametri. |
| Allele + fonte/versione/selettore | Frequenze, QC della fonte, matching ClinVar/VCEP e fatti usati da Priority. |
| Gene + malattia + release | Associazioni e meccanismi condivisi; non copiarli per ogni variante. |
| Occorrenza nell'analisi | GT, fase, DP/AD, VAF, GQ, QUAL/FILTER, caller e rappresentazione originale. |
| Campione/famiglia/run | Segregazione, callability, compound e ricorrenza nel relativo insieme. |
| Vista del campione | Bundle selezionati, profilo, contesto esplicito, fonti fissate e Priority finale. |

Non copiare indiscriminatamente `variants.metadata_json` nel catalogo: contiene
INFO e qualità specifici dell'analisi. Una frequenza VEP resta legata al proprio
bundle; un'AF della coorte presente nel VCF non diventa una frequenza globale.
Non riconciliare persone o campioni dal solo nome.

### 3.3 Versionamento delle annotazioni

Il `release_key` attuale può contenere run e digest del file originale: non è
una versione globale VEP. Definire un `annotation_bundle` con assembly,
annotatore/versione, cache dei trascritti, plugin, risorse e parametri che
influenzano i risultati. Usare metadati già registrati; niente nuovi checksum
di FASTA/VCF all'apertura.

Se il bundle non è qualificabile, conservare lo scope dell'origine. Due
annotazioni con etichetta «VEP 116» non sono automaticamente intercambiabili.
Il blob canonico può essere deduplicato tramite digest del piccolo record;
origini e versioni restano separate. Un conflitto non autorizza overwrite
silenziosi o la selezione implicita dell'annotazione più recente.

## 4. Persistenza fisica e contratti delle entità

### 4.1 Topologia

1. **Catalogo locale condiviso**, configurabile, basato sullo store `cohort`
   esistente con un'estensione versionata. Ruolo `variant_catalog`, distinto
   dalla pubblicazione clinica M5 della roadmap.
2. **Store derivato di consultazione per run**, affiancato all'indice attuale:
   mapping, risultati piccoli per campione, generazioni, job e checkpoint.
3. **Store delle fonti esistenti**, mantenuti come proprietari dei grandi dati.
   Il catalogo conserva selezioni e fatti derivati, non un secondo intero
   dataset gnomAD/ClinVar/VCEP.

Percorsi risolti dal backend, con override configurabili. Gli indici delle run
restano leggibili e non si riscrivono durante l'apertura. In prima fase
l'estensione catalogo ha versione propria sullo schema base cohort v2:
non incrementare lo schema di tutte le run per inizializzare il catalogo.

### 4.2 Catalogo condiviso

Nomi progettuali, non tabelle già implementate:

| Entità | Identità e contenuto minimo |
| --- | --- |
| `catalog_metadata` | UUID catalogo, versione estensione, contratti. |
| `variants` + `catalog_alleles` | Riutilizzare gli ID interi; relazione 1:1 con `allele_ref UNIQUE` e identità canonica. |
| `annotation_bundles` | Bundle, risorse condivise e qualificazione. |
| `annotation_contents` | Allele, bundle, trascritto quando qualificato, contenuto biologico immutabile e digest. |
| `annotation_origins` | Origini dei contenuti, senza GT o qualità del campione. |
| `source_versions` | Fonte, release/snapshot, schema/parser e selettore. |
| `variant_source_facts` | Allele, versione/selettore, revisione, esito, completezza, acquisizione/scadenza/retry, metriche tipizzate, subset decisionale e provenance. |
| `variant_annotation_features` | Metriche derivate per allele/bundle, versione estrattore e riferimenti ai fatti. |
| `projection_relations` | Sorgente/target, policy/versione, esito e prova della corrispondenza. |
| `variant_dependencies` | Dipendenze indicizzate da fonte, bundle e gene. |
| `acquisition_leases` | Richiesta unica, owner/fencing token, scadenza, tentativi e retry. |

Il subset decisionale conserva le osservazioni necessarie a riprodurre la
vista, inclusi negativi e limitazioni. ClinVar/VCEP mantengono condizioni e
asserzioni pertinenti, senza riduzione a una classificazione senza contesto.
I grandi payload rimangono nel provider con identità/versione esplicite.

Una vista storica deve poter spiegare il proprio punteggio anche dopo il
ritiro dello snapshot esterno. Se un dettaglio storico non conservato non è
disponibile, segnalarlo; non sostituirlo con dati correnti presentati come vecchi.
La retention pianificata deve preservare le fonti necessarie alle viste attive
o fissate. Il ritiro è consentito solo dopo aver verificato un archivio
alternativo senza perdita dei record pertinenti e delle stesse funzioni di
consultazione. Il messaggio di indisponibilità gestisce rimozioni esterne o
guasti, non sostituisce una funzionalità eliminata dalla nuova architettura.

### 4.3 Store di consultazione

| Entità | Funzione |
| --- | --- |
| `origin_manifest` | UUID stabile origine, UUID catalogo, revisione indice. Il percorso è aggiornabile. |
| `run_variant_bindings` | `(local_variant_id, index_revision)` → ID catalogo, stato identità e provenance locale; una relazione per variante della run. |
| `analysis_annotation_bindings` | Bundle/contenuti selezionati per analisi e variante. |
| `sample_view_generations` | Analisi/campione, profilo/policy, manifest dipendenze, generazione, stato e conteggi. |
| `sample_variant_results` | PK `(view_id, local_variant_id)`; riferimenti interi, score/banda, componenti numeriche, reason code e proiezioni strettamente necessarie. |
| `view_gene_dependencies` | Revisioni dei geni, delle famiglie e dei gruppi pertinenti. |
| `preparation_jobs` | Input univoco, lease, stato, checkpoint per intervalli e contatori. |
| `active_sample_views` | Puntatore alla generazione pubblicata per campione/profilo, aggiornato con CAS. |

Le chiamate originali restano nell'indice. Proiettare scalari GT/DP/VAF per
indicizzazione quando serve; non duplicare FORMAT o JSON originali. Salvare
componenti numeriche e codici motivazione versionati, evitando testi lunghi
ripetuti. Gli ID locali di database diversi non sono intercambiabili.

Ogni vista dichiara l'insieme delle analisi considerate e la policy di
aggregazione delle chiamate, riproducendo inizialmente il comportamento
esistente. Una nuova analisi non modifica implicitamente i risultati di una
vista fissata. Il binding di un'annotazione al campione non autorizza il riuso
di qualità, FORMAT o AF specifiche di altre analisi.

## 5. Flussi e concorrenza

### 5.1 Import

1. Identificare origine e revisione; adottare una sola volta l'UUID senza usare
   soltanto nome della run o percorso. Riconoscere i tentativi dello storico
   riferiti alla stessa origine.
2. Leggere blocchi configurabili, inizialmente 1.000–5.000 righe, con staging
   SQL per join in batch; nessun array globale dell'intero campione.
3. Riusare binding validi; normalizzare soltanto gli alleli nuovi o invalidati.
4. Registrare identità, bundle e contenuti con vincoli unici e verifica dei
   conflitti; conservare origini e assegnazione degli ALT.
5. Salvare mapping e checkpoint in transazioni brevi. Una nuova verifica
   integrale di un input modificato appartiene all'import esplicito.

### 5.2 Evidenze

Pianificare gli **alleli distinti mancanti**, separando cache valida,
proiezioni, frequenze, coperture, completamenti opzionali, retry e unresolved.
Non rileggere 50 risultati per elaborarne ripetutamente solo cinque.
Una cache hit non riscrive `attempted_at` o i metadati della run.

Riutilizzare single-flight nel processo e aggiungere lease persistenti con
chiave `(allele, source_version, selector, operation)`. Acquisizione/rinnovo
usano transazioni brevi e fencing token: un worker scaduto non pubblica sul
lavoro posseduto da un altro. Un crash può richiedere un secondo tentativo
HTTP; la pubblicazione locale è idempotente, senza promettere «exactly once»
per la rete.

Generare lavoro per finestre limitate, senza milioni di record pending pieni
di payload. Coordinare le scritture per database e mantenere lettori separati.
Nessuna transazione di scrittura resta aperta durante la rete. Riutilizzare
limiti di concorrenza e pacing dei provider prima di proporre aumenti.

### 5.3 Scoring e pubblicazione

Fissare bundle, fatti di fonte, contesto familiare, ricorrenza e profilo.
Riutilizzare metriche biologiche condivise ed eseguire lo scorer esistente
per il risultato contestuale del campione. Una componente numerica è condivisibile
solo se tutte le sue dipendenze sono identiche e dichiarate: non basta che usi
un'AF o un predittore. La prima consegna conserva il motore come riferimento
di equivalenza, senza riscriverne le formule.

Preparare risultati e spiegazioni in staging a lotti. I GET ricostruiscono
la presentazione da componenti salvate e fatti immutabili, senza rieseguire
lo scorer.

Non assumere atomicità distribuita fra file SQLite:

1. Committare prima i fatti condivisi immutabili referenziati.
2. Completare staging, riferimenti, conteggi e revisioni della generazione.
   Preservare le dipendenze prima di renderla visibile.
3. Se cambiano input, riparare il sottoinsieme o ricostruire in background.
4. Attivare la vista nella transazione locale della run con CAS sulla revisione
   attesa. Il puntatore pubblicato è la prova dell'attivazione.
5. Riprendere idempotentemente dopo crash anche fra attivazione e chiusura del
   job; staging orfano eliminabile solo dopo verifica e scadenza della lease.

Nella prima fase nessun GC elimina fatti condivisi referenziabili. La retention
successiva richiede pin durevoli e controllo dei riferimenti delle viste.

Stati job: `QUEUED`, `IMPORTING`, `ACQUIRING`, `SCORING`, `VALIDATING`, `READY`,
`READY_WITH_LIMITATIONS`, `FAILED`, `SUPERSEDED`. Ready richiede un esito per
tutti gli alleli previsti. Errori di fonte possono produrre N/A secondo la
policy corrente, senza diventare AF zero o NOT_FOUND. Separare lavoro concluso
da completezza biologica delle evidenze.

## 6. Apertura, API e frontend

Una vista pronta si apre leggendo manifest e pagina. Se manca una vista valida,
avviare o riagganciare un unico job per input; il browser osserva i contatori.
Chiudere una scheda interrompe l'osservazione, non il lavoro degli altri consumer.
La nuova tabella viene pubblicata a preparazione conclusa; una vista precedente
rimane identificata dalla propria generazione/data, senza essere dichiarata fresca.

Dataset piccoli: modalità completa locale, decisa in base a righe **e byte**
della proiezione compatta. Dataset grandi: pagine iniziali da 200 righe,
massimo 500, cache browser limitata per pagine/byte e prefetch contenuto.
Filtri e sort SQL leggono i risultati salvati, senza riavviare preparazione.

Route proposte sotto la risorsa campione già autorizzata:

| Operazione | Contratto |
| --- | --- |
| `POST .../sample-views` | Vista pronta riusabile o 202 con job esistente/nuovo per lo stesso input. |
| `GET .../sample-views/status?job_id=...` | Job autorizzato del campione, generazione, stato, conteggi di occorrenze/distinti/hit/acquisiti/retry/unresolved e limitazioni. |
| `GET .../sample-views/{view_id}/variants` | Pagina filtrata/ordinata e cursore vincolato alla vista. |
| `GET .../sample-views/{view_id}/filter-options` | Opzioni coerenti con la generazione. |
| Dettaglio attuale con `view_id` opzionale | Formato completo/compatto esistente, fonti e score della vista. |

I GET non avviano rete o job. ETag e manifest consentono rivalidazione dopo
riavvio. Le nuove risposte espongono `view_id`, revisione e modalità, non percorsi.
Il dettaglio/ACMG usa i bundle fissati alla vista; fonti più recenti vengono
distinte e possono portare a una nuova generazione, senza modificare una riga
silenziosamente. Preservare i miglioramenti DOM e cache dei dettagli già presenti.

## 7. Query, filtri e indici

Una sola specifica dei filtri con fixture comuni fra modalità locale e SQL.
Una variante passa i filtri su annotazioni quando esiste una **stessa
annotazione** che soddisfa tutti i vincoli pertinenti, indipendentemente
dall'ordine delle annotazioni.

Keyset pagination: cursore con `view_id`, firma filtri, campo/direzione e
ultima chiave con ID di spareggio; niente OFFSET profondo. Policy esplicite
per null e multivalori. Allowlist dei campi SQL. Un cursore di una vista diversa
viene rifiutato senza mescolare righe.

| Ambito | Indici iniziali da misurare |
| --- | --- |
| Catalogo | `allele_ref UNIQUE`, identità canonica, `(variant_id,bundle_id,transcript)`, `(variant_id,source_version_id,selector,revision)`. |
| Mapping | Variante locale e indice inverso su variante catalogo. |
| Risultati | PK `(view_id,local_variant_id)`, `(view_id,score,local_variant_id)`, `(view_id,selected_af,local_variant_id)`. |
| Annotazioni | Relazioni condivise gene/conseguenza/allele/bundle per `EXISTS`, senza una copia completa per campione. |
| Dipendenze | Indici inversi da allele, gene, bundle e gruppo alle viste. |
| Portatori | Membership origine/analisi/allele con revisione; dettagli della chiamata letti dall'indice originale. |

Altri indici, inclusi DP/VAF/qualità, richiedono `EXPLAIN QUERY PLAN` e misure:
non indicizzare ogni campo JSON. I filtri grandi usano dati tipizzati o relazioni
indicizzabili, non scansioni di blob compressi. Il conteggio esatto dei filtri
complessi può essere separato e annullabile, senza bloccare la prima pagina;
una stima non viene mostrata come conteggio esatto.

## 8. Revisioni e aggiornamenti incrementali

Usare revisioni logiche dei record e manifest: una frequenza modificata per
un allele estraneo non invalida tutte le viste. Registrare dipendenze da indice,
chiamate, policy di normalizzazione, bundle/estrattore, fatti/selettori,
gene-malattia, famiglia/callability, ricorrenza, profilo e schema della vista.

I provider emettono modifiche dopo il commit. Per scritture esterne, stat/WAL
e sostituzioni attivano riconciliazione in background; finché le revisioni non
sono verificabili non dichiarare fresca la vista. Nessuna scansione globale nel GET.

| Modifica | Sottoinsieme da rivalutare |
| --- | --- |
| Frequenza/matching allele | Feature e righe delle viste che lo usano. |
| Annotazione/bundle | Contenuti e selezioni coinvolte; preservare viste fissate a bundle precedenti. |
| Gene-malattia | Feature del gene e viste dipendenti. |
| Chiamata parentale | Campione, famiglia e geni/gruppi compound pertinenti. |
| Portatore nuovo | Gruppo di ricorrenza pertinente; nessun cambio implicito da run a coorte. |
| Profilo/policy | Nuova generazione delle viste che lo adottano. |

Accorpare gli eventi durante la preparazione. Per aggiornamenti piccoli
riusare chunk immutabili o patch normalizzate con catena limitata e compattazione
in background; non copiare cinque milioni di risultati immutati per un allele.
Layout e limite delle patch sono un gate di benchmark prima dell'abilitazione;
la ricostruzione completa resta un fallback esplicito.

## 9. Correttezza da risolvere prima di materializzare

I punti seguenti sono interventi candidati, subordinati al vincolo del §1.
Prima di renderli obbligatori, dimostrare beneficio ed equivalenza funzionale.

1. Genitori senza chiamate non equivalgono a 0/0 verificato. GT/callability
   mancanti producono UNKNOWN; de novo/assenza richiedono prove esplicite.
   L'indice attuale conserva soprattutto ALT: gVCF/joint VCF vanno eventualmente
   interrogati per intervalli, senza espandere tutti i siti di riferimento.
2. I filtri gene/conseguenza/frequenza per popolazione devono considerare tutte
   le annotazioni compatibili, con vincolo sulla stessa annotazione.
3. MAX_AF deve coincidere fra tabella e API dopo la selezione delle evidenze.
4. Le cache attuali dell'ordine devono riconoscere WAL e sostituzioni; evitare
   ordini vecchi per risultati aggiornati durante il passaggio alle revisioni.

La ricerca dei candidati de novo e dei pattern familiari deve restare
disponibile anche con input incompleti: distinguere candidati da verificare
e assenza supportata da prove, conservando un percorso esplicito per trovare
entrambi. Nessuna variante prima esaminabile deve diventare irraggiungibile
per effetto della distinzione; nessun dato mancante viene dichiarato 0/0.
Per gli altri filtri preservare controlli, combinazioni e casi d'uso mentre
si allineano le implementazioni locale e SQL.

Conservare massimo fra frequenze gnomAD ammissibili e MAX_AF VEP,
`discrepant_frequencies` come avviso non bloccante e le altre policy QC/assenza
attuali. Nessuna modifica delle formule mascherata da ottimizzazione.

## 10. Spazio, retention e migrazione

Misura separata:

`delta disco = catalogo distinto + binding run + risultati per occorrenza/profilo
             + indici + job + staging`

Gli alleli crescono con l'unione delle varianti; collegamenti e score crescono
con le occorrenze. Genomi con molti alleli nuovi fanno crescere il catalogo:
la condivisione non garantisce spazio costante aggiungendo campioni.

Non ripetere payload provider, risorse di release, contesti gene-malattia,
identificatori lunghi e motivazioni testuali per ogni campione. Il prototipo
precedente da circa 4,8 KB/variante comprimeva la riga JSON completa e non è
il budget del nuovo modello.

Obiettivo da verificare: store di consultazione entro **1 KiB per occorrenza
e profilo**, inclusi risultati e relativi indici, esclusi catalogo, fonti,
staging e migrazione legacy. È un target progettuale, non una misura garantita.

Retention iniziale: una vista corrente e al massimo una sostituita per
campione/profilo, più staging attivo; export/audit possono fissare pin espliciti.
Cleanup non elimina chiamate o fatti usati da altri campioni. Nessuna scrittura
di timestamp a ogni lettura; checkpoint e compattazione fuori dai GET.

La prima migrazione è additiva. Gli indici legacy conservano le annotazioni:
il catalogo può inizialmente aumentare lo spazio. La loro compattazione è un
sottotask esplicito, con formato versionato, portabilità, consumer compatibili
e verifica delle origini. Non dichiarare eliminate copie prima di quella fase.
Nessuna cancellazione automatica di VCF/BAM/FASTA o indici originali.

## 11. Prima preparazione di esomi e genomi

Il lavoro remoto dipende dagli **alleli distinti mancanti** per fonte/versione.
Un catalogo evita ripetizioni ma non elimina il costo di milioni di alleli nuovi.

Prevedere nei provider letture locali in batch e import di annotazioni già
prodotte dalla pipeline. Un adattatore locale gnomAD completo o ridotto è un
sottotask successivo con campi/selettori e spazio misurati, non un download
automatico. Un dato VEP non autorizza a inventare gnomAD o dichiarare verificato
il massimo fra fonti mai acquisite.

Misurare separatamente prima preparazione con fonti locali, prima acquisizione
remota, secondo campione sovrapposto e riapertura pronta dopo riavvio. Nessun
tempo WGS garantito usando soltanto API remote per alleli sconosciuti.

## 12. Fasi di consegna

Ogni fase lascia il sistema utilizzabile. Nuovi nomi di moduli indicativi:

| Fase | Ambito e file principali | Criterio di uscita |
| --- | --- | --- |
| VSC-00 | Baseline e valutazione §9; `query.py`, filtri JS, cache ordine e test. | Correzioni con beneficio verificato e funzionalità preservate; interventi non equivalenti rinviati. |
| VSC-01 | `catalog.py`, estensione schema, dipendenza da identità esistente. | Stessi alleli fra run → stesso ID; unresolved isolati. |
| VSC-02 | `catalog_import.py`, adapter indexer, manifest/mapping. | Due run importate in streaming, idempotenza e ripresa; origini/versioni conservate. |
| VSC-03 | `view_jobs.py`, adapter provider, lease e checkpoint. | Riuso fra campioni/processi; cache valida senza rete o riscrittura della run. |
| VSC-04 | `sample_views.py`, feature, scorer e pubblicazione. | Parità con il motore per input corretti, crash recovery, viste durevoli. |
| VSC-05 | `view_query.py`, route additive e indici. | Pagine/filter/sort senza scoring/rete, cursori e query plan verificati. |
| VSC-06 | Browser e integrazione dettaglio/ACMG. | Modalità locale/paginata equivalenti, memoria limitata e generazione coerente. |
| VSC-07 | Cutover, retention, report spazio; compattazione come sottotask. | Adozione progressiva, rollback leggibile e benchmark pubblicato. |

Prima modalità di confronto, poi cutover per run/campione dopo equivalenza.
Il percorso legacy resta disponibile durante la migrazione. Import fallito
non blocca l'indice precedente; input/schema incompatibili fermano il job con
checkpoint, senza riparazioni distruttive. Il provider locale è un sottotask
separato: la sua disponibilità non viene presunta per misurare una prima WGS.
Ogni fase include una matrice funzione attuale → sostituto → test → misura
del beneficio. Il cutover non procede se una funzione manca o perde qualità;
la stessa regola vale per compattazione, retention e ritiro del fallback.

## 13. Test e benchmark di accettazione

### Correttezza e resilienza

- Inventario delle funzioni attuali, confronto con i sostituti e verifica del
  beneficio; candidati familiari consultabili anche con dati incompleti,
  filtri completi, dettagli e fonti storiche preservati.
- SNV alias, indel, multiallelici, assembly diversi, contig ambigui,
  reference assente/modificata e input esclusi.
- Stesso allele in run diverse con GT/DP/VAF/FILTER differenti: dati condivisi
  uguali, osservazioni e Priority contestuale distinte.
- Bundle/plugin diversi o incompleti, fonti nuove e conflitti senza overwrite.
- Annotazioni riordinate, filtri combinati, AF finale, N/A/zero, errore/negativo,
  flag gnomAD e assenza con copertura.
- Famiglia senza chiamate, 0/0 documentato, callability insufficiente, compound
  non fasato e conteggio di gruppi della run.
- Parità di score/componenti sugli stessi input corretti; correzioni del §9
  con aspettative esplicite proprie.
- Crash fra lotti, commit dei fatti, prima/dopo attivazione; lease scaduta,
  worker vecchio, due processi, catalogo/binding mancanti.
- Fonte storica ritirata: spiegazione riproducibile e dettaglio indisponibile
  dichiarato, senza sostituzione implicita.
- Test che vietano scorer/rete/checksum integrali nei GET/filter/sort.
- Chrome: paging, annullamento, cambio rapido campione/variante, stato della
  vista, limiti di memoria e assenza di righe provenienti da generazioni diverse.

### Matrice prestazionale

Fixture con seed e manifest di ambiente: pannello 1.000 righe, esoma 200.000,
genoma 5.000.000; 1/10/100 campioni sintetici con sovrapposizione 0/50/90%,
annotazioni multiple e complessi; fonti locali e remoto simulato con errori.
Le combinazioni più grandi appartengono ai benchmark periodici, non ai test rapidi.
Aggiornamenti di prova: un allele, un gene, una famiglia e una release.
La matrice non è un prodotto cartesiano da eseguire automaticamente: i profili
di benchmark dichiarano numero totale di occorrenze, budget disco/RAM e scala.
Avviare la prova WGS con uno o due campioni; espandere a coorti più grandi su
hardware adeguato senza mascherare i costi del catalogo e dei collegamenti.

Obiettivi iniziali su SSD e hardware dichiarato, con vista già preparata:

| Misura | Criterio |
| --- | --- |
| Riapertura invariata | Zero acquisizioni, scoring e scritture alle varianti sorgenti. |
| Verifica manifest pronto | p95 entro 100 ms. |
| Prima pagina 200 righe | p95 entro 300 ms backend, cache OS calda. |
| Sort/filtri comuni su 5 milioni | p95 entro 500 ms; riportare anche filtri complessi fuori soglia. |
| Pagina | Target entro 512 KiB non compressi, senza payload completi delle fonti. |
| Preparazione | Incremento RSS entro 512 MiB per job, includendo processi di supporto; memoria non lineare con le righe totali. |
| Riuso fra campioni | Nessuna acquisizione per stessi alleli/fonti/selettori validi. |
| Spazio per campione | Budget §10, distinto da catalogo e WAL/staging. |

Rilevare p50/p95, locale/remoto, RAM dei worker, tabelle/indici/WAL, byte
trasferiti, nuovi alleli/fatti, hit e scritture. Conteggi e filtri complessi
non si nascondono nella media. Il primo recupero remoto non si confronta con
soglie che presuppongono fonti locali.

Script proposto: `scripts/benchmark_variant_catalog.py`, output JSON e report
Markdown. Prima contratti/schema e correttezza, poi ottimizzazione degli indici.

## 14. Decisioni e limiti

Decisioni fissate: catalogo SQLite condiviso, `ga2`, annotazioni versionate,
chiamate contestuali, Priority per campione, job durevoli, pagine limitate,
pubblicazione coerente e nessun checksum integrale nel browsing.

VSC-00 e VSC-01 possono iniziare senza ulteriori scelte dell'utente. Soglie
local/paged, lotti, indici, patch e retention vanno confermati con benchmark
prima del cutover. Misurare il limite del writer prima di proporre sharding
o un database server; nessuno dei due è requisito della prima consegna.

Una cache non risolve disponibilità delle fonti per il primo genoma,
qualificazione dei bundle storici o assenza di prove parentali. Questi stati
restano espliciti, senza inventare dati o equivalenze per rispettare un tempo.
