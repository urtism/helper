# ACMG Interpretation Workbench — uso e avvio

## Installazione separata

HELPER e ACMG Engine utilizzano ambienti Python separati, comunicando solo via
REST. Verifica eseguita con Python 3.12. Nessuna libreria scientifica ACMG viene
importata da HELPER; le dipendenze FastAPI/Pydantic dei due progetti restano separate.

```bash
cd /home/jarvis/git/Helper
python3.12 -m venv .venv-helper-next
.venv-helper-next/bin/python -m pip install -e ./helper_next

cd /home/jarvis/git/acmg-engine
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Per una dimostrazione research riproducibile, copiare solo profili dai fixture
TASK20, non l'intera directory (contiene anche risultati e manifest):

```bash
mkdir -p /tmp/helper-acmg-profiles
cp docs/examples/task20/population_generic_profile.json /tmp/helper-acmg-profiles/
cp docs/examples/task20/population_myh7_profile.json /tmp/helper-acmg-profiles/
cp docs/examples/task20/population_custom_profile.json /tmp/helper-acmg-profiles/
cp docs/examples/task20/population_custom_genome_profile.json /tmp/helper-acmg-profiles/
cp docs/examples/task20/splice_ps1_generic_profile.json /tmp/helper-acmg-profiles/
cp docs/examples/task20/splice_ps1_custom_profile.json /tmp/helper-acmg-profiles/
ACMG_ENABLE_RESEARCH_INTERPRETATION=true ACMG_PROFILES_DIR=/tmp/helper-acmg-profiles .venv/bin/acmg-engine
```

Engine: `http://127.0.0.1:8000`, documentazione `/docs`. Questi sono profili
sperimentali/fixture, non un insieme di regole clinicamente approvate. Senza
profili configurati il servizio può essere disponibile ma offrire zero selezioni.

### Profili configurati nell'avvio automatico HELPER

`configs/acmg_engine.json` elenca esplicitamente i sei profili TASK20 del
comando precedente: cinque generici e una specializzazione MYH7. I percorsi
sono relativi al file di configurazione. HELPER ne copia i file originali in
una directory temporanea privata, imposta `ACMG_PROFILES_DIR` per il processo
figlio e rimuove la copia alla chiusura. I documenti e i loro digest restano
invariati. Il motore valida i profili durante il caricamento.

`HELPER_ACMG_CONFIG` consente di scegliere un altro file di configurazione;
`ACMG_PROFILES_DIR` impostato nell'ambiente ha priorità e usa direttamente la
directory indicata. La configurazione si applica soltanto ai processi avviati
da HELPER: un motore già attivo va riavviato per cambiare profili. La
specializzazione MYH7 appare solo per il contesto gene-malattia corrispondente.

Il caricamento rende disponibili i profili EXPERIMENTAL nella discovery.
La configurazione locale abilita esplicitamente l'esecuzione research tramite
`"enable_research_interpretation": true`, su richiesta dell'utente per usare
**Classify variant**. `ACMG_ENABLE_RESEARCH_INTERPRETATION` nell'ambiente HELPER
ha priorità; impostarlo a `false` disabilita l'esecuzione anche con questa
configurazione. Con un motore già attivo è necessario riavviarlo e riaprire il
workbench per rileggere le capabilities. Quando **Classify variant** è
disabilitato, il workbench mostra il requisito mancante: esecuzione research,
verifica FASTA oppure selezione del profilo.

### Errore ENGINE_UNAVAILABLE

All'avvio del server, HELPER avvia automaticamente ACMG Engine se l'URL è HTTP
locale (`127.0.0.1`, `localhost` o `::1`, senza prefisso di percorso) e la
connessione è rifiutata. Riutilizza un motore già attivo. Cerca il comando in
`acmg-engine/.venv/bin/acmg-engine` accanto al repository HELPER, poi nel `PATH`.
L'installazione separata descritta sopra è necessaria una sola volta; HELPER
non installa pacchetti automaticamente. Se l'avvio fallisce, HELPER resta
disponibile e registra il motivo nei log del server.

Per un'installazione in un'altra posizione impostare `HELPER_ACMG_ENGINE_DIR`
alla directory del repository del motore, oppure `HELPER_ACMG_COMMAND` al suo
eseguibile (percorsi con spazi vanno racchiusi tra virgolette nella variabile).
Il comando viene eseguito senza shell. Il processo eredita l'ambiente HELPER,
inclusi `ACMG_PROFILES_DIR` e l'eventuale opt-in
`ACMG_ENABLE_RESEARCH_INTERPRETATION`; la configurazione locale precedente
definisce i profili e l'opt-in research. `ACMG_HOST` e `ACMG_PORT` vengono ricavati da
`ACMG_ENGINE_URL` per il processo figlio.

Alla chiusura HELPER ferma solo il motore che ha avviato. Con
`HELPER_ACMG_AUTOSTART=0` si mantiene l'avvio manuale in un terminale separato;
gli URL remoti o HTTPS restano sempre gestiti esternamente.

La risposta di errore indica
ora `engine_url`, `reason` e `timeout_seconds`: `CONNECTION_REFUSED` significa
che nessun servizio accetta la connessione su quell'indirizzo; `TIMEOUT` indica
che la richiesta non è terminata entro il limite.

Verificare prima `http://127.0.0.1:8000/health`, poi
`http://127.0.0.1:8765/api/acmg/discovery`. Se il motore usa una porta diversa,
impostare `ACMG_ENGINE_URL` nell'ambiente del processo HELPER e riavviare HELPER.
Quando il motore torna disponibile, chiudere e riaprire il workbench.

## Riferimento FASTA

Gli EvidencePacket con evidenza strutturata richiedono REF verificato e allele
normalizzato. HELPER riutilizza IndexedFasta e normalize_allele del viewer.
Per run con reference_fasta già configurato è possibile riutilizzare quel file.
Per upload esterni configurare un JSON locale per assembly, ad esempio:

```json
{
  "GRCh38": {
    "fasta": "/percorso/assoluto/GRCh38.fa",
    "version": "GRCh38"
  }
}
```

Usare un FASTA non compresso con `.fai` corrispondente, dell'assembly dichiarata.
Se necessario creare l'indice con `samtools faidx /percorso/assoluto/GRCh38.fa`.
La versione deve descrivere il riferimento reale; il contenuto viene comunque
identificato tramite SHA256 calcolato localmente. Il campo facoltativo `sha256`
permette anche di verificare un digest atteso ottenuto dalla propria fonte.
Il percorso non viene trasmesso al motore. Nessun download di riferimenti.

```bash
cd /home/jarvis/git/Helper
ACMG_ENGINE_URL=http://127.0.0.1:8000 \
HELPER_ACMG_REFERENCE_CONFIG=/percorso/assoluto/acmg-references.json \
.venv-helper-next/bin/helper-next serve --host 127.0.0.1 --port 8765
```

Aprire `http://127.0.0.1:8765`, sezione Variants. Se si configura un riferimento
dopo un'importazione di indel e l'allele richiede un diverso allineamento,
reimportare il file per rigenerare l'indice con il riferimento corretto; HELPER
non sostituisce silenziosamente l'identità della variante selezionata.

## Flusso

La schermata principale segue due passaggi: **Context** e **Classification**.
I dati univoci forniti da HELPER sono riassunti nel contesto; restano in primo
piano solo i selettori che richiedono una scelta o dati mancanti. **Automatic
data and sources** raccoglie ID, namespace, assembly e provenienza. Dopo
**Continue to classification** il contesto si richiude. Un solo profilo generico
utilizzabile viene preselezionato; più profili richiedono una scelta esplicita.
La classificazione viene sempre avviata con **Classify variant**.

Il risultato mostra classificazione, completezza e contributi effettivi, seguiti
da una tabella di sei colonne per tutti i 28 criteri. **Show technical columns**
ripristina le 16 colonne complete. Un clic sul criterio apre spiegazione,
calcoli, audit e revisione. **Advanced tools and evidence** raccoglie il confronto
profili, l'evidenza originale, il packet e le correzioni JSON. Cronologia,
dettagli della classificazione ed esportazioni tecniche sono richiudibili;
**Download report** resta direttamente disponibile. Prerequisiti bloccanti,
contesti ambigui e avvisi del motore restano segnalati nella vista principale.

1. Aprire un run indicizzato oppure **Upload external VCF** (.vcf/.vcf.gz),
   confermando GRCh37/GRCh38. L'upload non crea analisi, esperimenti o cronologia
   Nextflow. Le due sorgenti condividono parser, tabella, dettaglio e paginazione.
2. Aprire un campione e una variante, quindi **Interpret with ACMG Engine**.
3. HELPER prepara il campo strutturato `interpretation_context` del dettaglio
   variante, ricavando gli identificativi stabili dalle annotazioni VCF e dalla
   propria cache gene-malattia. Gene ID, disease ID e namespace sono compilati
   automaticamente e visualizzati in campi di sola lettura. L'associazione unica
   viene selezionata automaticamente; con più malattie si sceglie il contesto
   per nome, senza digitare identificativi. Anche annotazione unica, assembly
   già dichiarata ed ereditarietà univoca da fonte vengono precompilate.
4. Preparare l'EvidencePacket. Scegliere un profilo generico/versione ed
   eventualmente una specializzazione esatta. La metodologia e il metodo di
   classificazione sono quelli del profilo, senza strategie inventate o VCEP
   dedotti dal solo simbolo del gene.
5. Eseguire l'interpretazione o scegliere esplicitamente il profilo di confronto
   e usare **Compare Standard vs VCEP**. Le richieste condividono lo stesso
   snapshot di evidenza. Le combinazioni non supportate sono segnalate.
6. Filtrare i 28 criteri e aprire l'ispettore: valori, soglie, operatori, audit,
   rami decisionali, regole, fonti, evidenza esclusa e prerequisiti mancanti.
7. Registrare CONFIRM, CONTEST o REQUEST_REVIEW con commenti, categoria,
   reviewer e riferimenti. Il risultato del motore resta immutato.
8. Nell'editor JSON aggiungere correzioni strutturate con evidenza, provenienza
   MANUAL, fonte/versione/checksum, commento e ID sostituito. Rilanciare e
   confrontare la cronologia. Le revisioni precedenti non si applicano al nuovo
   risultato. I contesti salvati restano selezionabili anche dopo riapertura.
9. Esportare risultato JSON, EvidencePacket JSON, tabella CSV con audit,
   report Markdown leggibile, troubleshooting, revisioni, confronto profili e
   differenza prima/dopo. Nessun nome campione aggiunto automaticamente ai report.

## Mapping ed evidenza manuale

Il contesto strutturato HELPER (`helper-interpretation-context-v1`) contiene,
per ogni annotazione/trascritto, gene, malattie associate, modalità ereditarie
registrate, fonti, versioni, stato della cache e fingerprint. Il workbench invia
la selezione del record: il backend recupera gli ID dal dato HELPER e verifica
che la fonte non sia cambiata dall'anteprima. Il contesto risolto viene congelato
con il workspace, le interpretazioni e i report.

L'assenza di dati locali o ID discordanti viene segnalata senza inventare una
malattia. In questi casi aggiornare le fonti gene-malattia di HELPER e usare
**Reload HELPER context**. La risoluzione non avvia download o richieste esterne.
Per ereditarietà discordanti tra fonti si sceglie una modalità presente nel
record oppure si mantiene il prerequisito irrisolto. Il simbolo del gene non
diventa da solo un'identità stabile né determina automaticamente una malattia.

CHROM/POS/REF/ALT sono allele-specifici. QUAL/FILTER, INFO originale,
FORMAT/genotipo del campione, annotazioni e intestazioni/versioni disponibili
restano nello snapshot locale. CSQ/ANN vengono interpretati secondo il loro
header. ALLELE_NUM disambigua le CSQ multialleliche; annotazioni minimizzate
ambigue non sono assegnate a più ALT. L'INFO originale resta ispezionabile.

REVEL numerico e componenti SpliceAI_pred_DS_* sono osservazioni importate sul
trascritto scelto. HELPER non calcola il massimo SpliceAI. Le annotazioni
gnomAD/gnomADe/gnomADg AF/AC/AN sono mappate solo se disponibili e riferibili
all'ALT, rispettando INFO Number=A/R/1. AC/AN di coorte senza dataset esplicito
non diventano evidenza di popolazione. Nessun AC/AN viene ricavato da AF.

Il dettaglio variante include anche `gnomad_frequency`, il lookup strutturato
già presente nella cache locale HELPER per quello stesso allele e assembly.
Durante **Continue to classification** il backend ne prepara un'evidenza
`POPULATION` indipendente dal VCF: AC, AN, AF, conteggi omozigoti/emizigoti,
popolazioni, filtri e copertura vengono trasferiti con release, dataset, identità
dell'allele e checksum del record sorgente. Nessuna richiesta gnomAD aggiuntiva.
I record senza conteggi conservano lo stato HELPER, compreso
`not_observed_covered`, in `quality_information` e nelle note dell'osservazione;
AC/AN non restituiti non diventano zero né una numerosità stimata. L'adeguatezza
della copertura conserva l'euristica HELPER esistente; non certifica la
rappresentazione ancestrale o la copertura delle singole sottopopolazioni.

Questo collegamento riguarda i dati: soglie, dataset ammessi e assegnazione di
PM2 restano nel profilo del motore. Dopo un nuovo lookup gnomAD preparare un
nuovo contesto per includere il dato aggiornato; workspace e risultati precedenti
restano immutati.

Un checksum del record VCF ne fissa il contenuto: **non è una versione del
dataset gnomAD o del predittore**. Qualità, popolazione e release non registrate
rimangono mancanti e il motore può rifiutare l'evidenza come insufficiente.
ClinVar e IMPACT non attivano criteri. Genotipo singolo e separatore `|` non
diventano automaticamente evidenza di segregazione o fase scientificamente validata.

L'editor accetta un array di oggetti con questa struttura, usando gli schemi
reali disponibili nel link alla discovery:

```text
{
  evidence: <Evidence dell'engine con id, kind, observation, provenance>,
  source: <PacketSource con source_id, version, checksum, url>,
  replaces: <ID esistente, facoltativo per un'aggiunta>,
  comment: <spiegazione obbligatoria>
}
```

provenance.source_identifier/source_version/artifact_digest devono coincidere
con source.source_id/version/checksum. Le prove funzionali, familiari, di
splicing e bibliografiche richiedono i rispettivi contratti strutturati e fonti
esplicite. Nessun campo dell'editor modifica profili o soglie scientifiche.

## Persistenza, limiti e verifiche

Default sotto `$XDG_DATA_HOME/helper_next` (oppure `~/.local/share/helper_next`):
`external_vcf/` per upload/indici e `acmg.sqlite3` per contesti, esiti immutabili,
correzioni e revisioni append-only. Non viene duplicato il VCF nel DB di review.
Override: HELPER_EXTERNAL_VCF_DIR, HELPER_ACMG_DB. Il DB review è chmod 0600;
ogni directory di upload è 0700. Dati conservati localmente per riprendere il
lavoro; nessuna pulizia automatica che invalidi gli snapshot salvati.

Upload in streaming: massimo 256 MiB ricevuti, 1 GiB espansi, 4 MiB/riga e
5 milioni di record. Compressione controllata prima dell'indicizzazione,
pulizia di upload incompleti, nomi interni casuali e protezione traversal.
Il nome originale passa in un header, non nella query degli access log.
Il browser invia il File direttamente e non ne legge interamente il contenuto.

ACMG_ENGINE_URL è configurabile solo sul backend, default loopback; timeout
ACMG_ENGINE_TIMEOUT (15 secondi per richiesta). Niente redirect HTTP, invio di
VCF interi, dipendenze scientifiche copiate o esposizione pubblica predefinita.

Gli audit eterogenei e gli oggetti OpenAPI opachi rendono PARTIAL alcune viste
scientifiche universali: [contratto e proposta 1.1](TASK22_ACMG_CONTRACT.md).
Formula o branch non esposti restano NOT_RECORDED. Nessun VUS forzato in caso
di input incompleto. Nessuna approvazione scientifica/validazione clinica.

Test ordinari: `PYTHONPATH=helper_next/src python -m pytest -q helper_next/tests`.
Non richiedono il motore; i test REST reali richiedono opt-in:

```bash
HELPER_TEST_ACMG_SERVICE=1 ACMG_ENGINE_URL=http://127.0.0.1:8000 \
PYTHONPATH=helper_next/src python -m pytest -q helper_next/tests/test_acmg_service_integration.py
```

Il test PM2 necessita anche di HELPER_TEST_ACMG_BOUNDARY_REQUEST, percorso di
una richiesta sintetica esportata dalla fixture upper_request(ac=1,an=118595)
del repository engine, con i profili corrispondenti caricati nel servizio.
Non introdurre fixture sintetiche nel catalogo di produzione.

Test browser riproducibile con API simulate (Chrome e pacchetto opzionale
`websocket-client` richiesti):

```bash
HELPER_TEST_ACMG_BROWSER=1 PYTHONPATH=helper_next/src \
python -m pytest -q helper_next/tests/test_acmg_browser.py --tb=short
```

Avvia temporaneamente HELPER su 127.0.0.1:8793 e DevTools su 127.0.0.1:9293,
poi chiude i processi. Override HELPER_TEST_BROWSER_PORT e
HELPER_TEST_BROWSER_DEBUG_PORT. Usa un profilo Chrome temporaneo e seleziona
esclusivamente la scheda HELPER, senza leggere schede o estensioni dell'utente.
