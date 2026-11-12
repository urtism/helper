# Caricamento completo del campione e preparazione Priority

Aggiornamento: 9 novembre 2026.

La preparazione delle evidenze avviene nell'indicizzazione della run, prima
dell'apertura dei campioni. Stato persistente, checkpoint, retry e gestione
degli indici precedenti sono descritti in
[Preparazione della run](RUN_PRIORITY_PREPARATION.md).
La consultazione ClinVar non calcola più il checksum dell'intero FASTA. Restano
le letture locali degli intervalli REF e la normalizzazione degli alleli usate
dal matching ClinVar; la provenance indica `checksum_status=NOT_CHECKED`, senza
inventare un digest. Anche l'apertura dei dettagli e il relativo matching VCEP
evitano il checksum integrale. Le verifiche esplicite che richiedono il digest
lo conservano su disco e lo riusano dopo il riavvio del backend; vedere
[Dettagli delle varianti e cache del riferimento](VARIANT_DETAIL_LOADING.md).

Il flusso attuale è:

1. Dopo l'indicizzazione VCF, il job della run prepara i dati gene-malattia
   GenCC/Gene2Phenotype tramite l'indice esistente.
   Riusa un indice corrente, attende un aggiornamento già avviato o tenta il
   refresh se manca o è scaduto. Se il refresh fallisce conserva i dati installati
   e segnala il limite. Un aggiornamento ancora in corso impedisce di mostrare
   punteggi provvisori.
2. Visita tutti gli alleli distinti della run in lotti fino a 50, indipendentemente
   dai filtri di visualizzazione. Quando servono acquisizioni remote, limita il
   lotto a cinque per aggiornare prima l'avanzamento. Recupera tramite il provider gnomAD esistente
   frequenze, proiezione GRCh37→38 e, per i negativi, copertura regionale.
   Riusa le risposte valide in cache e mostra il numero di varianti elaborate.
   Gli stessi alleli condivisi fra campioni riusano le cache esistenti.
3. Aprendo un campione, il browser legge lo stato del job della run. Alla fine
   della preparazione richiede `variants?load_all=true`, senza applicare
   i filtri della tabella. La query integra
   frequenze, contesto gene-malattia, ClinVar locale, annotazioni/predittori VCF,
   dati familiari e ricorrenza nella run; calcola e ordina prima della risposta.
   La risposta contiene tutti i risultati, anche oltre 500 varianti, con
   `next_cursor=null`, e i dati necessari ai filtri locali: annotazioni,
   frequenze per popolazione, classificazioni ClinVar, origine parentale e
   portatori nella famiglia. Le API paginate restano disponibili agli altri client.
4. Pubblica l'intero elenco in un'unica sostituzione. Il rendering resta virtuale:
   tutte le varianti sono caricate, ma il DOM contiene soltanto le righe visibili.
   Richieste sostituite o annullate non possono sovrascrivere il nuovo elenco.
5. Conserva l'elenco completo in memoria. Ordinamento, applicazione/rimozione
   dei filtri e riapertura delle schede riusano gli stessi oggetti e punteggi,
   senza chiamare nuovamente preparazione o query delle varianti. Le schede gene
   derivate riusano il campione caricato. Un filtro senza risultati non elimina
   i dati originali; una modifica durante il caricamento si applica al risultato
   completo, senza annullare l'acquisizione. Un aggiornamento delle evidenze
   sostituisce invece l'elenco originale e riapplica i filtri attivi.

Le fonti locali installate continuano a fornire ClinVar, annotazioni e predittori;
non si generano nuovi predittori né si scaricano automaticamente snapshot ClinVar.
Un'origine irraggiungibile non diventa una variante assente: le evidenze mancanti
restano N/A e le limitazioni di acquisizione sono riportate nel campione. Nessuna
modifica alla scala AF, alle formule o ai criteri clinici.

Le sezioni seguenti documentano le misure e le ottimizzazioni precedenti del
provider, che rimangono usate dal job della run. Il vecchio ciclo di
acquisizione per campione non è più usato dal browser.

## Rallentamento durante il recupero Priority: 590 / 756

Nel campione ID 7 della run `20261015_Run_723_CancerHS2`, il tratto intorno
alla variante 590 coincide con evidenze ancora da acquisire dopo una lunga parte
già in cache. Sono presenti errori gnomAD `The read operation timed out`, anche
su alleli con proiezione GRCh38 già disponibile. Il contatore si aggiorna alla
fine del lotto: non distingue da solo un'attesa remota dal lavoro locale.

La preparazione ora restituisce immediatamente il prefisso già in cache prima
di incontrare una variante mancante. Se il lotto inizia con un'acquisizione
necessaria, resta limitato a cinque alleli; soltanto gli alleli mancanti o con
copertura da completare entrano nel provider. Le proiezioni presenti nella cache
condivisa sono riconosciute prima di scegliere la pipeline: un lotto già
proiettato non viene diviso inutilmente in tre più due richieste alleliche.

Il riuso locale ricostruisce l'associazione esatta sorgente/destinazione e
aggiunge il collegamento nell'indice se manca, anche quando le evidenze erano
state acquisite da altri campioni. Un collegamento già coerente conserva
provenienza e timestamp: non viene riscritto per una semplice lettura. Questo
evita anche invalidazioni superflue della cache dei dettagli. I contatori API
aggiuntivi `cached`, `acquired` e `updated` distinguono riuso, alleli avviati al
provider (inclusi fallimenti) e righe effettivamente aggiornate.

Misura senza rete su due copie temporanee dello stesso indice reale, campione 7,
primo lotto di 50 varianti già disponibili nella cache condivisa:

| Operazione | Prima | Dopo |
| --- | ---: | ---: |
| Preparazione del lotto | 0,807 s | 0,113 s |
| Aggiornamenti delle righe varianti | 50 | 0 |
| Esito e avanzamento | 50 FOUND, cursore 94 | 50 FOUND, cursore 94 |

È una misura del riuso locale, non del primo caricamento dell'intero campione.
Le latenze remote rimangono: timeout, backoff, limiti gnomAD, controllo della
copertura e condizioni del punteggio restano invariati. Non si saltano alleli e
non si attribuiscono punti per un errore di recupero. Passati 125 test mirati,
inclusi Chrome, identità/proiezioni, lotti misti, riapertura senza scritture,
acquisizione della copertura sui negativi in cache e regressioni del provider.
Verificato anche l'endpoint del backend attivo: un allele già disponibile
restituisce `cached=1`, `acquired=0`, `updated=0`.

## Prima acquisizione senza cache

Il riuso locale non risolve da solo le attese degli alleli nuovi. Due ulteriori
ottimizzazioni intervengono sul percorso remoto:

- Per una SNV sorgente e una SNV contestuale di destinazione, entrambe con basi
  A/C/G/T distinte, la prima risposta NCBI contiene già l'intero allele VCF.
  La posizione SPDI interbase viene convertita in posizione VCF aggiungendo uno.
  Non occorre la seconda chiamata `vcf_fields`. La proiezione continua a essere
  acquisita e qualificata da NCBI sull'accession esatta della assembly di
  destinazione. Indel, rappresentazioni complesse, dati non idonei, proiezioni
  ambigue e assenti conservano il percorso completo o l'esito precedente.
  La provenance aggiunge `validation.vcf_conversion` (`SPDI_SNV` oppure
  `NCBI_VCF_FIELDS`). Le cache esistenti restano valide. La conversione segue il
  [modello SPDI descritto da NCBI](https://pmc.ncbi.nlm.nih.gov/articles/PMC7523648/)
  e la [distinzione fra SPDI e VCF](https://ncbiinsights.ncbi.nlm.nih.gov/2017/02/09/new-web-services-for-comparing-and-grouping-sequence-variants/).
- La pipeline può acquisire due piccoli gruppi contemporaneamente, sovrapponendo
  proiezione, recupero frequenze e copertura. Usa due worker condivisi e al
  massimo due gruppi per chiamante; non accoda l'intero campione nell'executor.
  Il gate HTTP mantiene la distanza fra gli avvii secondo il costo della query
  e limita a due le richieste attive. L'attesa di una lettura HTTP non trattiene
  più il lock del gate: una richiesta lenta non impedisce al secondo gruppo di
  partire quando il pacing lo consente. Risposte e identità sono ricomposte
  nell'ordine originale, conservando deduplicazione, single-flight e backoff.

Nel campione da 756 varianti, 607 sono SNV sorgente; la scorciatoia si applica
soltanto se anche il target NCBI soddisfa i requisiti sopra. Prova online su
cache SQLite temporanee inizialmente vuote, cinque SNV reali note alla fonte,
due gruppi da tre e due alleli, confronto con il codice precedente:

| Operazione | Prima | Dopo |
| --- | ---: | ---: |
| Proiezione + acquisizione gnomAD di cinque alleli | 12,644 s | 5,279 s |
| Esiti | 5 FOUND | 5 FOUND |
| Alleli, dataset completi e flag restituiti | Identici | Identici |

Una prova separata sulle sole proiezioni di tre SNV ha ridotto le chiamate NCBI
da sei a tre (10,119 s → 7,514 s), con destinazioni identiche. Sono misure di
lotti specifici: non garantiscono gli stessi tempi per indel, copertura o
timeout remoti, né per un intero esoma/genoma. I limiti delle fonti rimangono;
per la prima acquisizione su scala WES/WGS resta necessario il percorso con
fonti locali descritto nel [piano del catalogo condiviso](VARIANT_SHARED_CATALOG_PLAN.md#11-prima-preparazione-di-esomi-e-genomi).

Le regressioni verificano la conversione SNV in entrambe le direzioni, gli
indel sul convertitore originale, il rifiuto delle scorciatoie ambigue,
l'ordine dei risultati, la sovrapposizione di letture lente, il limite di due
richieste attive, il pacing per costo e la pressione sull'executor durante un
campione più grande. Nessun campo QC, regola Priority o controllo di copertura
è stato rimosso.

## Verifica

Test di regressione in `helper_next/tests/test_sample_priority_loading.py`:
assenza di checksum con matching/controllo REF degli indel conservati; ordine e
filtri con caricamento completo; 606 varianti oltre il limite pagina; acquisizione
unica degli alleli del campione; frequenze acquisite utilizzate nel punteggio;
errori di rete neutri; attesa dei dati gene-malattia; pubblicazione atomica,
annullamento delle richieste e prova Chrome con 606 varianti e rendering virtuale.
Le regressioni coprono inoltre il profilo AF e la copertura regionale, le identità
biologiche, la validazione esplicita della reference e gli endpoint esistenti.
La prova IGV di streaming/byte-range non è stata eseguita perché già bloccante
nella precedente verifica; resta separata dal caricamento del campione.

Misura sul solo calcolo/lettura, su copia dell'indice della run
`20261015_Run_723_CancerHS2`, campione da 854 varianti, senza accesso di rete e
con un errore imposto se viene richiesto il checksum FASTA:

| Fase | Prima | Dopo |
| --- | ---: | ---: |
| Prima risposta query | 6,79 s / 200 righe | 0,53 s / 854 righe |
| Checksum integrale FASTA | 6,23 s | Non eseguito |
| Serializzazione FastAPI dell'elenco completo | — | 0,45 s |

Questi tempi escludono acquisizione remota, trasferimento e rendering. La prima
acquisizione di dati non presenti in cache può richiedere tempo, in particolare
per la proiezione allelica e i limiti di richiesta gnomAD. Il browser attende il
completamento e mostra l'avanzamento, senza esporre Priority provvisorie.

## Misura online iniziale sul campione segnalato

Campione ID 2 della stessa run, 797 varianti. Misura sul
backend realmente attivo, con le acquisizioni del campione in corso:

| Operazione | Tempo misurato |
| --- | ---: |
| Lettura elenco campioni | 0,051 s |
| HTTP `variants?load_all=true`, tutte le 797 varianti | 0,960 s |
| NCBI: prima richiesta di una proiezione mancante | 3,049 s |
| NCBI: seconda richiesta della stessa proiezione | 2,096 s |
| gnomAD: acquisizione della variante proiettata | 0,315 s |
| Lookup completo di quella variante senza cache | 5,495 s |
| Riuso immediato della stessa variante dalla cache | 0,010 s |

Sono stati osservati aggiornamenti dell'indice alle 14:54:45 e 14:59:18 UTC.
I metadati possono essere sovrascritti dai lotti successivi o condivisi con altri
campioni: tali timestamp non sono una misura isolata della durata di una richiesta.
Al primo controllo del campione erano presenti 100 varianti preparate, 130 proiezioni
in cache, 102 frequenze in cache e 665 proiezioni ancora mancanti; due alleli
non erano supportati. Il contesto gene-malattia era corrente, ClinVar disponibile.

La prova remota della singola variante usa copie delle cache in `/tmp`, senza
scritture negli indici operativi. La risposta HTTP completa serve a isolare il
costo finale: **non certifica che l'acquisizione preliminare sia terminata**.

Il collo di bottiglia osservato nella misura iniziale era l'acquisizione sequenziale delle proiezioni NCBI,
seguita dalle chiamate gnomAD e dai relativi intervalli di pacing. Il contatore
frontend avanza solo dopo la risposta dell'intero lotto da 50: la pagina può
apparire ferma per minuti. Estrapolando il costo della proiezione singola alle
centinaia di alleli ancora mancanti, il completamento può richiedere un tempo dell'ordine di un'ora;
questa è una stima, non una misura dell'intero caricamento. Le risposte valide
vengono conservate e riusate nelle aperture successive.

### Correzione delle risposte HTTP e dei lotti remoti

La prova online ha riprodotto un ulteriore problema: una richiesta di cinque
varianti con alias `v0_all`, `v0_non_ukb`, ecc. riceveva una risposta con 200 alias
estranei (`q0`…`q199`). Il parser scartava correttamente quei dati come
`Incomplete GraphQL response`; nella cache attiva erano presenti 187 errori di
questo tipo al momento del controllo. La stessa variante richiesta singolarmente
era valida. Il costo delle proiezioni era quindi sostenuto anche per lotti le cui
frequenze non potevano essere utilizzate.

La richiesta HTTP ora include nella URL un SHA-256 del suo contenuto e invia
`Cache-Control: no-cache`. L'identificativo distingue query e variabili senza
introdurre checksum FASTA. Su due richieste di prova con cinque e due varianti
sono tornati gli alias attesi e risultati `FOUND`. Sul codice corretto, ripetendo
la richiesta di cinque varianti già proiettate, tutti e cinque i risultati sono
tornati `FOUND` in 0,586 s. Una prova intermedia era scaduta dopo 12 s: la latenza
remota rimane variabile. Gli errori incompleti pregressi vengono ritentati senza
attendere il precedente intervallo di riuso degli errori; gli altri errori
conservano il backoff esistente.

La preparazione conserva lotti grandi quando i dati sono già in cache e passa a
cinque alleli quando servono richieste remote. Il contatore può quindi avanzare
prima rispetto ai precedenti 50 alleli, mantenendo la visualizzazione subordinata
al completamento della preparazione e del calcolo per l'intero campione.

Sono passati 271 test mirati, inclusi regressioni della cache HTTP, recupero dopo
risposte con alias estranei, lotti adattivi, copertura regionale, scala AF e query.
Il ricaricamento automatico del server era rimasto in attesa delle vecchie
richieste sincrone: è stato necessario terminare il vecchio worker, conservando
il supervisore e i dati salvati. Il nuovo backend ha risposto HTTP 200.

## Quattro ottimizzazioni del recupero delle evidenze

Implementate il 5 novembre 2026. L'intero campione continua a essere acquisito e
valutato prima di pubblicare la tabella; la scala AF e le condizioni per +25 nei
negativi coperti restano invariate.

1. **Full cohort per Priority.** La preparazione richiede soltanto `gnomad_r4`.
   Il sottoinsieme `gnomad_r4_non_ukb` viene completato aprendo il dettaglio.
   Un errore nel solo sottoinsieme non invalida il full cohort. Il completamento
   del sottoinsieme non ricarica l'elenco se l'evidenza usata da Priority non è
   cambiata. Anche le cache preesistenti vengono lette in forma ridotta durante
   il calcolo: si eliminano il sottoinsieme e le righe di popolazione duplicate
   nella radice; le righe nei dataset, richieste dal calcolo, vengono conservate.
   I payload completi restano disponibili nella cache e nel dettaglio.
2. **Proiezione fornita dall'analisi.** Si riusa un allele GRCh38 completo legato
   all'allele sorgente nei metadati di arricchimento, oppure in `original_vcf.info`:
   `HG38=chr:pos:REF:ALT`, `GRCH38=...` o i quattro campi
   `HG38_CHROM/POS/REF/ALT` (anche con prefisso `GRCH38`). Per i multiallelici
   servono valori distinti per ogni ALT. Coordinate sole, sorgenti diverse e
   chiavi cache incoerenti non sono riusate. In assenza dell'allele completo si
   conserva la proiezione NCBI; non si introduce una verifica FASTA.
3. **Copertura BigWig indicizzata.** Si leggono soltanto intervalli dalle tracce
   UCSC gnomAD v4.0 exome e v3.0.1 genome, senza scaricare file completi. Mean e
   frazione `over_20` sono valutati base per base dalla policy già esistente,
   sulla stessa finestra; NaN e basi mancanti rimangono mancanti. La provenienza
   delle tracce è salvata nel riepilogo. Se un dataset non è leggibile, si tenta
   il GraphQL esistente conservando il dataset indicizzato valido. Una lettura
   nativa che supera 20 secondi viene terminata e va in backoff per 30 secondi.
4. **Richieste condivise e pipeline limitata.** Le richieste concorrenti dello
   stesso allele condividono il recupero attivo, incluse proiezione, frequenze e
   copertura. A fine recupero il registro in RAM viene svuotato: i dati restano
   nelle cache SQLite esistenti. Le proiezioni usano tre thread condivisi e un
   limite globale di una richiesta NCBI al secondo per processo. Nei lotti
   remoti GRCh37 gnomAD parte dopo i primi tre alleli risolti, mentre gli altri
   vengono proiettati. I limiti di pacing gnomAD restano applicati.

### Configurazione della copertura

`HELPER_GNOMAD_COVERAGE_MODE=auto` usa le letture indicizzate; `graphql` disabilita
il lettore BigWig e conserva il provider precedente. Facoltativamente
`HELPER_GNOMAD_COVERAGE_DIR` indica una directory locale con questi file:

```text
v4-exome/gnomad.coverage.mean.bw
v4-exome/gnomad.coverage.over_20.bw
v3-genome/gnomad.coverage.mean.bw
v3-genome/gnomad.coverage.over_20.bw
```

La dipendenza è `pyBigWig>=0.3.25`. Per gli URL serve una build con libcurl
(`pyBigWig.remote == 1`); alcune wheel non includono il supporto remoto. In questo
ambiente è stata installata e verificata la build da sorgente:

```bash
python -m pip install --force-reinstall --no-binary pyBigWig --no-build-isolation pyBigWig==0.3.25
```

Il lettore è un singolo processo separato avviato al primo utilizzo, perché le
letture native non rilasciano il GIL e non espongono un timeout totale. Conserva
al massimo quattro file aperti e 32 blocchi da 512 basi in LRU. Il riavvio
dell'applicazione libera questa cache in RAM. Non viene creata una copia locale
delle tracce remote.

### Tempi e memoria misurati

Misure RSS su processi di prova isolati, cache temporanee in `/tmp`; non sono
limiti garantiti di memoria dell'intera applicazione.

| Operazione | Misura |
| --- | ---: |
| Copertura chr11:108282880 GTA>G (GRCh38), prima apertura remota dei quattro file | 10,63 s |
| Stesso intervallo già nella cache del lettore | 0,0016 s |
| RAM del lettore e del processo di supporto, somma RSS | 73,78 MB |
| Incremento RSS del chiamante durante la lettura | 0,71 MB |
| Dimensione installata della nuova libreria, senza dipendenze già presenti | 254.181 byte |
| Cinque varianti reali senza cache, pipeline tre + due, tutte FOUND | 23,13 s |
| Stesse cinque varianti da cache | 0,055 s |
| Query finale completa delle 797 varianti, senza rete/checksum | circa 1,6 s |
| Serializzazione FastAPI della risposta, circa 8,46 MB | circa 0,44 s |
| Picco RSS della query completa, con lettura dei payload precedenti | 342,44 MB |
| Picco RSS della query completa, lettura ridotta per Priority | circa 205 MB |

Nel lotto remoto la prima richiesta gnomAD parte a 8,11 s, prima che l'ultima
proiezione termini a 12,40 s. Le due richieste gnomAD impiegano 9,34 e 5,56 s:
la latenza remota rimane il limite principale. Una misura separata, con cinque
alleli richiesti in un unico gruppo, aveva impiegato 12,91 s; non si deduce un
fattore di accelerazione da prove con latenze remote diverse. Non è stato
completato un nuovo caricamento da zero di tutte le 797 varianti.

Il picco della query esclude il lettore BigWig, perché la fase finale legge solo
le evidenze già acquisite. Le tracce complete richiederebbero circa 36 GB su
disco: questa implementazione non le scarica. Crescono soltanto le cache SQLite
già esistenti; nei cinque alleli di prova, la cache frequenze occupa 430.080 byte
e quella delle proiezioni 20.480 byte.

Fonti dei file e dei vincoli:
[tracce exome](https://hgdownload.soe.ucsc.edu/gbdb/hg38/gnomAD/coverage/v4-exome/),
[tracce genome](https://hgdownload.soe.ucsc.edu/gbdb/hg38/gnomAD/coverage/v3-genome/),
[pyBigWig](https://github.com/deeptools/pyBigWig),
[specifica NCBI Variation Services](https://api.ncbi.nlm.nih.gov/variation/v0/var_service.yaml).

Verifica finale: 396 test mirati superati e tre prove Chrome superate. Una prova
aggiuntiva confronta il calcolo su cache completa e ridotta per tutte le 797
varianti reali: punteggi, spiegazioni e ordine coincidono. I test delle nuove
acquisizioni coprono anche errori, rilascio del registro prima del risveglio dei
client, completamento concorrente del sottoinsieme, pipeline, coordinate esatte,
valori mancanti, fallback, timeout e limiti della cache del lettore. Resta escluso
il test IGV di streaming/byte-range già segnalato come bloccante.
