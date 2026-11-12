# Preparazione delle evidenze durante l'indicizzazione della run

Aggiornamento: 12 novembre 2026.

La preparazione delle evidenze Priority avviene dopo l'indicizzazione locale
dei VCF, nello stesso flusso in background della run. Anche gli import di run
archiviate e gli upload VCF avviano la preparazione. La lettura strutturale
`indexer.index_run` resta separata dal lavoro remoto; l'orchestrazione API
coordina i due passaggi.

## Acquisizione e consultazione

Il job prepara una volta il contesto gene-malattia e visita gli alleli distinti
dell'intera run. La stessa variante presente in più campioni viene acquisita
una volta. Posizioni non positive e REF/ALT non risolti A/C/G/T sono esclusi con
lo stesso filtro del browser. Il provider conserva proiezione NCBI, frequenze
full cohort gnomAD, QC e copertura regionale dei negativi; non cambia formule,
scala AF o condizioni per i punti di rarità. I risultati pubblici rimangono
nella cache SQLite condivisa fra run; nell'indice rimangono i collegamenti
allelici già esistenti.

Quando si apre un campione, il browser legge lo stato della preparazione con
`GET /api/variants/runs/{id}/priority-evidence`. Se il lavoro è terminato,
richiede immediatamente l'elenco completo e ne calcola Priority dal contesto
locale del singolo campione. Se il job sta lavorando mostra l'avanzamento della
**run**, con polling annullabile; non avvia lotti remoti per campione e non
mostra righe con punteggi provvisori. Filtri e ordinamento continuano a riusare
la tabella completa in memoria.

## Classificazioni ACMG automatiche

Dopo le frequenze, lo stesso job prepara ACMG per ogni coppia campione–variante,
con checkpoint riprendibili. L'avanzamento espone `phase: ACMG` e i contatori
`acmg_preparation`. La valutazione legge le annotazioni locali senza acquisire
ClinVar. I risultati automatici, inclusi quelli non valutati, sono conservati
in `automatic_classifications` nel database delle interpretazioni della run;
restano separati dalle revisioni salvate dall'utente, che hanno precedenza.

La preparazione valuta le varianti con un massimo predefinito di quattro
worker, limitato alle CPU disponibili. `HELPER_ACMG_WORKERS` permette di
impostare da 1 a 16 worker prima di avviare il backend (1 disabilita il
parallelismo). Il numero effettivo compare in `acmg_preparation.workers`.
I worker condividono i cataloghi gene–fenotipo già letti, invalidati quando
cambiano le fonti locali. Le scritture dei contesti sono raggruppate per
variante e affidate a un unico writer SQLite, che conferma solo dopo il commit.
Il resolver dei meccanismi e il catalogo MONDO sono condivisi fra contesti,
varianti e campioni della stessa configurazione. Ogni richiesta controlla la
release attiva e conserva una vista immutabile; una nuova release ricarica il
catalogo. Revisioni delle fonti, TTL, integrità degli snapshot e regole vengono
ancora verificati a ogni risoluzione. Le scritture di altri meccanismi non
causano il ricaricamento del catalogo MONDO.
Il checkpoint avanza nell'ordine campione–variante: alla ripresa gli esiti
già completati fuori ordine vengono riutilizzati. Durante la preparazione
non vengono registrati ticket temporanei per il salvataggio interattivo.

Il browser riusa i risultati e le richieste già in corso per variante. Filtri,
ordinamento, riapertura del dettaglio e aggiornamenti delle sezioni non
riavviano l'analisi molecolare. Dopo un riavvio, la cache persistente conserva
gli esiti e ricrea soltanto i ticket temporanei necessari al salvataggio.
Il ricalcolo avviene quando cambiano annotazioni, fonti biologiche del gene,
riferimento, regole o un PVS1 salvato. Aggiornamenti di altri geni e date di
accesso alla cache non invalidano il risultato. Gli errori transitori non diventano risultati validi
permanenti. La tabella legge anche i risultati automatici preparati senza
attendere l'apertura del dettaglio.
I salvataggi manuali invalidano le viste del browser; le scritture della cache
automatica non invalidano il dettaglio né avviano nuovi calcoli.

Alla lettura della tabella, le firme delle annotazioni vengono riutilizzate fra
campioni e riavvii tramite la cache opzionale `variants.sqlite.acmg-inputs.json`.
Una modifica o sostituzione dell'indice, inclusi aggiornamenti nel WAL, invalida
la cache; le firme restano quelle del contenuto biologico originale. La cache
può essere ricostruita e non è necessaria per aprire una run in sola lettura.
Il browser richiede il trasferimento compatto della tabella: righe dei filtri
e provenienza ClinVar ripetute sono trasferite una sola volta e ricostruite
prima di applicare filtri o mostrare i dati. L'API predefinita resta invariata.

Le run preparate con il flusso precedente richiedono una nuova preparazione
delle evidenze con **Priority · ACMG** nella lista run; i VCF non devono essere reindicizzati.

I dettagli mantengono il recupero opzionale del sottoinsieme non-UKB e tutte le
funzioni ClinVar, VCEP, IGV e ACMG precedenti. Non sono introdotti download
automatici di interi dataset gnomAD o ClinVar, né checksum integrali del FASTA.

## Stato persistente e ripresa

`helper_variants.run_evidence` salva `priority_preparation` nei metadati della
run: stato, numero totale di alleli supportati, numero visitato, esiti, ultimo
ID completato, timestamp, contesto gene-malattia e firma delle dipendenze.

- `queued` / `running`: lavoro avviato; l'indice strutturale può essere già
  completo, ma l'API di indicizzazione riporta ancora il lavoro in corso con
  `phase=priority_evidence` e i contatori.
- `complete`: tutti gli alleli supportati sono stati visitati e le evidenze
  richieste sono disponibili.
- `partial`: visita terminata con evidenze non disponibili. La consultazione
  rimane possibile, con avviso riferito alla run e N/A dove non valutabile.
  Errori e dati mancanti non diventano AF=0 o assenze verificate.
- `failed`: errore del job; l'indice e i dati acquisiti rimangono conservati.
- `interrupted`: esiste un checkpoint di lavoro in corso, ma il processo non
  detiene più il lock. All'avvio il backend legge i metadati delle run note e
  riaccoda soltanto i lavori precedentemente avviati/interrotti. Non prepara
  automaticamente tutte le run mai aperte. Anche il polling dello stato o la
  successiva selezione della run possono riaccodare un lavoro interrotto.
- `stale` / `not_started`: serve una preparazione nuova.

Un lock di file con `flock` impedisce lavori duplicati sulla stessa run anche
fra processi. Il kernel lo rilascia alla fine del processo; il file `.priority.lock`
può restare presente senza rappresentare un lavoro attivo. Non si mantiene una
transazione SQLite durante le richieste remote. Il checkpoint è salvato dopo
il lotto: un'interruzione fra il salvataggio delle evidenze e il checkpoint
può far ripassare il lotto, che riusa i dati validi senza riscriverli.

L'acquisizione lunga usa un worker separato dalla richiesta HTTP; la risposta
di accodamento e la lettura dello stato rimangono disponibili anche mentre una
fonte è bloccata. Alla chiusura del backend il job si arresta fra i lotti,
conservando il checkpoint. La richiesta HTTP non attende l'acquisizione completa
durante il riavvio; il recupero delle fonti del lotto attivo mantiene i timeout
e i limiti già previsti dal provider.

La firma considera i digest VCF già presenti nell'indice, lo stato delle
sorgenti, il massimo ID variante, release/parser gnomAD, parametri della policy
di copertura e percorso/identità del file cache condiviso. Non rilegge i VCF
o il FASTA per calcolare digest. Una modifica delle dipendenze avvia una nuova
visita, conservando i risultati validi in cache. Una sostituzione della cache
durante un job lo invalida; non si pubblica come completa una preparazione
basata su dipendenze cambiate a metà.

## Run già indicizzate e recupero esplicito

Alla selezione di una run, il browser esegue
`POST /api/variants/runs/{id}/priority-evidence`: per una run già pronta è un
controllo senza nuove acquisizioni. Per gli indici precedenti a questa modifica
avvia una sola preparazione della run; campioni e schede condividono quel job.
Gli esiti parziali non vengono ritentati a ogni apertura del campione.

Il nuovo pulsante **Priority** nella lista delle run usa lo stesso endpoint con
`force=true` per ripassare le evidenze e ritentare i fallimenti. Mantiene il
backoff del provider e riusa le risposte valide; al termine aggiorna i punteggi
delle schede aperte e riapplica i filtri. Il pulsante **gnomAD**, il suo endpoint
di arricchimento completo e l'endpoint esplicito POST per le evidenze del singolo
campione restano disponibili. Il browser non usa quest'ultimo nel caricamento.

Un errore nell'accodamento delle evidenze di un upload non elimina il VCF
caricato e indicizzato. Il job può essere richiesto di nuovo dalla run.

## Verifica e limiti

Le regressioni coprono acquisizione automatica dopo l'indicizzazione, alleli
condivisi fra campioni, filtri sugli alleli, checkpoint e ripresa, esclusione di
duplicati fra processi, esiti parziali e retry, invalidazione delle dipendenze,
upload conservato in caso di errore, arresto cooperativo, recupero all'avvio,
risposta HTTP durante una fonte bloccata e richieste reali tramite ASGI.
Chrome verifica caricamento completo, filtri, ordinamento e dettagli senza
acquisizioni per campione.

Il tempo della prima acquisizione viene anticipato alla preparazione della run.
L'API remota rimane il limite per molti alleli nuovi; questo cambiamento non
garantisce tempi rapidi per il primo esoma/genoma. Il catalogo condiviso e le
fonti locali restano il percorso per la scala WES/WGS.
