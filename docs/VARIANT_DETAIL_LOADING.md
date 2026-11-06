# Dettagli delle varianti e cache del riferimento

Aggiornamento: 6 novembre 2026.

L'endpoint del dettaglio verifica REF e normalizza l'allele leggendo solo gli
intervalli necessari dal FASTA. Non calcola il checksum integrale, nemmeno al
primo accesso dopo il riavvio o quando mancano tutte le cache. Anche il fallback
di qualificazione dell'allele in VCEP riceve `checksum_reference=False`.
Il controllo REF continua a rifiutare sequenze discordanti; gli indel conservano
la normalizzazione. La provenance riporta `checksum_status=NOT_CHECKED` e digest
assente, senza dichiarare verificato l'intero file.

Le altre chiamate che richiedono il checksum conservano la verifica SHA-256.
Una volta calcolato, il digest viene salvato atomicamente su disco in un file
`*.checksum.json`, riutilizzabile anche da un nuovo processo. La cache si trova
in `HELPER_REFERENCE_VALIDATION_DIR`, oppure nella directory
`$XDG_DATA_HOME/helper_next/reference_validation` (predefinita:
`~/.local/share/helper_next/reference_validation`). Non contiene dati dei campioni.

Il riuso richiede la stessa assembly, versione, percorso e identità dei file
FASTA e FAI: dispositivo, inode, dimensione, mtime e ctime in nanosecondi.
Modifiche, sostituzioni dei file o cambi di versione invalidano la cache;
un file corrotto viene ignorato. Directory e file devono appartenere all'utente
e non essere scrivibili da gruppo o altri. Se la cache non può essere scritta,
la verifica appena completata continua a funzionare.

La cache del solo checksum resta distinta dalle ricevute di validazione
FASTA/FAI: non abilita `validate_reference(check=True)`. La validazione esplicita
completa e il confronto con uno SHA-256 configurato restano disponibili.

## Misura sul campione reale

Prova senza rete, in un nuovo processo, su copia dell'indice della run
`20261015_Run_723_CancerHS2`, campione 2, stessa variante SNV:

| Fase | Prima | Dopo |
| --- | ---: | ---: |
| Prima esecuzione del dettaglio nel backend | 6,24 s | 0,10 s |
| Lettura integrale FASTA per SHA-256 | 6,12 s | Non eseguita |
| Serializzazione FastAPI della risposta | circa 0,10 s | 0,09 s |

I tempi escludono trasferimento HTTP, rendering e acquisizioni avviate
successivamente dal browser. Il payload di quella variante resta di circa 3 MB.
Il miglioramento riguarda il lavoro sincrono necessario a produrre il dettaglio.

## Regressioni

`test_variant_detail_loading.py` copre dettagli SNV/indel senza cache, discordanza
REF e fallback VCEP, vietando ogni chiamata al checksum integrale.
`test_reference_checksum_cache.py` verifica il riuso da un nuovo processo,
l'invalidazione anche quando viene ripristinato mtime, file sostituiti,
cambi di percorso/versione, cache danneggiate o non sicure, scrittura negata e
confronto con il digest configurato. Le regressioni esistenti continuano a
coprire identità ga2 e validazione completa FASTA/FAI.

## Prima ottimizzazione della consultazione

Il browser richiede `?compact=true` sul dettaglio. Il formato predefinito delle
API e i dati persistenti restano invariati. Il trasporto opzionale
`helper-variant-detail-compact-v1` conserva una sola copia delle risorse di
release e dei contesti/origini condivisi; ogni annotazione mantiene i propri
identificatori, collegamenti e fingerprint. Il browser ripristina la struttura
completa prima di passarla al rendering, IGV o al calcolatore ACMG.

Ogni scheda conserva al massimo otto risposte del dettaglio in memoria.
La riapertura invia `If-None-Match`: se i dati sono invariati, il backend risponde
304 senza ricostruire il dettaglio. L'ETag debole deriva dai soli metadati dei
file, includendo WAL e sostituzioni, dalle configurazioni, dal profilo Priority,
dalla rappresentazione richiesta e da una finestra di freschezza di un minuto.
Sono considerate reference/FAI, indice della run, ClinVar, VCEP, dati
gene-malattia, gnomAD e proiezioni. Non viene letto né calcolato il checksum
integrale del FASTA. Se le dipendenze cambiano durante la costruzione, oppure
ClinVar/VCEP restituiscono un errore, la risposta non pubblica un ETag riusabile.
La ricarica delle evidenze del campione svuota la cache della scheda.

Le richieste liftover, gnomAD e portatori usano una query della sola identità
allelica, mantenendo il controllo di appartenenza al campione. Le pagine
ClinVar aggiuntive usano `/variants/{id}/clinvar-submissions?offset=…&limit=…`,
senza caricare annotazioni, ricalcolare Priority o ricostruire contesti ACMG.
La paginazione precedente sul dettaglio completo resta disponibile.

Gli aggiornamenti asincroni sostituiscono soltanto la sezione interessata.
La tabella e le altre sezioni mantengono il proprio DOM; vengono conservati
apertura delle sezioni, selezioni e scorrimento del pannello. Richieste
sostituite non possono sovrascrivere lo stato corrente, anche riaprendo lo
stesso allele.

Nuova misura sullo stesso campione reale, senza rete, su copia temporanea
dell'indice:

| Operazione | Formato completo | Formato compatto |
| --- | ---: | ---: |
| Payload SNV | 2.991.822 byte | 716.013 byte (−76%) |
| Payload indel | 4.851.705 byte | 833.499 byte (−83%) |
| Costruzione + serializzazione SNV | 0,178 s | 0,140 s |
| Costruzione + serializzazione indel | 0,217 s | 0,168 s |

La rivalidazione di un dettaglio invariato richiede 0,0032 s nel backend e
restituisce 304 senza corpo. I tempi escludono HTTP e rendering. Il riuso è
stato verificato anche con l'implementazione ASGI reale e con dipendenze
modificate. Le nuove regressioni coprono round-trip senza perdita di dati,
contesti ACMG/fingerprint, pagine submission, controllo del campione, WAL,
reference, cache limitata e risposte concorrenti. Chrome verifica conservazione
del DOM della tabella, delle sezioni aperte, del focus e dello scorrimento.

Questa fase non aggiunge uno snapshot persistente della tabella calcolata né
un indice globale dei portatori. La cache delle risposte del dettaglio è in
memoria nel browser; la cache del checksum del riferimento descritta sopra
rimane persistente su disco.
