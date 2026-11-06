# HELPER — New ACMG Calculator: PVS1 Interactive MVP

## Apertura e perimetro

Aggiornare l'installazione nell'ambiente Python del backend con `python -m pip install --no-deps --no-build-isolation -e /home/jarvis/git/Helper/helper_next`, poi riavviare il backend e ricaricare il browser.
Nel dettaglio di una variante fare clic su **Valuta ACMG**: apre la modal **ACMG Calculator**, esclusivamente PVS1, policy STANDARD e modello `PVS1_GENERAL 1.1.0` (implementazione parziale MVP).
Il trascritto della riga HELPER viene conservato; se necessario si sceglie esplicitamente una delle annotazioni già presenti. Nessun altro trascritto viene cercato o preferito dal Calculator.
La rilevanza biologica del trascritto resta `NOT_EVALUATED`, informativa e non bloccante, anche se il campo è assente: si valuta sempre il trascritto fornito, senza certificarne la rilevanza.
La malattia disponibile viene mostrata dal contesto strutturato HELPER; contesti multipli richiedono selezione. Ereditarietà ambigua o assente resta sconosciuta.
Con più associazioni disponibili la modal richiede la scelta del contesto prima della richiesta: non mostra associazioni presenti come dati mancanti per una selezione omessa.
La modal mostra stato, strength calcolata/applicata, motivazione, dati mancanti e warning. Ogni requisito è espandibile con PASS/FAIL/UNKNOWN/NOT_APPLICABLE/NOT_EVALUATED, valore, soglia, fonte e motivazione.
Escape, pulsante di chiusura e clic sullo sfondo chiudono la modal; il focus torna al pulsante di apertura. Una nuova richiesta annulla quella precedente.

## Percorso nuovo e dati utilizzati

`pvs1/calculator.py:calculate_pvs1(PVS1Input, policy="STANDARD") -> PVS1Result` contiene logica Python esplicita; non esiste un nuovo motore generico di regole.
`POST /api/acmg-calculator/pvs1` legge la variante dall'indice del campione e richiede run/sample/variant, annotation_id e transcript corrispondenti; il browser non può sostituire identità/alleli con un input arbitrario.
La route chiama direttamente il nuovo Calculator; non chiama vecchio Engine, Task 22, Workbench o relative API di valutazione. Riusa solo indice/contesto HELPER, riferimenti trascrizionali e componenti DOM/HTTP esistenti.
Il vecchio Workbench e i suoi endpoint sono stati rimossi: vedere [pulizia strutturale](HELPER_STRUCTURAL_CLEANUP.md). Il calcolatore locale PVS1 è l'unico percorso di valutazione disponibile.
Il package `pvs1` resta nella root ed è incluso nella distribuzione `helper-next`, insieme ai namespace `api` e `core`: dopo la reinstallazione l'import funziona anche avviando il backend fuori dal repository, senza aggiungere la root al PYTHONPATH.

- Variante/gene/conseguenza/trascritto provengono dall'annotazione esatta dell'ALT selezionato; malattia/ereditarietà dal contesto locale già disponibile. Validità del gene non viene trasformata in meccanismo LoF.
- Il catalogo trasporta anche record G2P e associazioni presenti solo in G2P. Meccanismo esplicito, ereditarietà e fonti vengono importati soltanto per gene, identificativo di malattia e modalità ereditaria selezionati; si riusano `allelic()` e `molecular_mechanism()` esistenti. Asserzioni curate ammesse, univoche ed esplicite qualificano il meccanismo come DEFINITIVE; la classificazione originale G2P dell'associazione resta nella fonte, distinta da questa qualificazione. Conflitti restano DISPUTED.
- Record G2P senza identificativo di malattia non vengono associati per nome; il limite compare nei warning. Nella cache ATM verificata il record recessivo G2P01390 è collegabile a MONDO:0008840; G2P03403 monoallelico è privo di identificativi di malattia e non viene trasferito a un contesto tumorale per supposizione.
- Se `annotation.metadata.pvs1_input` contiene un input PVS1 già preparato, lo si riusa dopo validazione strutturale e confronto di allele, trascritto, gene e malattia selezionata. È opzionale e non crea nuove persistenze o annotatori.
- Altrimenti si usa soltanto la cache del `TranscriptReferenceProvider`, con accession/versione/assembly esatti e `fetch=False`. Nessun download, ricerca multitranscritto o FASTA genomico.
- Un PTC numerico esplicito in HGVSp/Protein_position viene trasportato come **annotazione predetta**, dopo la mappatura REF/CDS esistente. Per fsTer numerico si considera la posizione del primo residuo cambiato e la distanza al nuovo stop; forme incerte o non supportate non sono interpretate.
- In assenza di PTC annotativo utilizzabile si richiamano le primitive dello STEP 3A sulla CDS in cache; per frameshift senza NMD si può ricostruire anche la regione proteica mancante. `pvs1/molecular.py` è invariato.
- Da score/offset SpliceAI o dalla sola conseguenza VEP non si inventa un evento splice. Un evento già ricostruito deve essere presente nell'input PVS1 fornito e conservare `basis` e provenance.
- `decision_trace` mantiene il contratto `list[str]`: ogni stringa è un record JSON con id, descrizione, stato, valore, soglia, fonte, riferimento STEP0 e motivazione. Non è un nuovo modello di regole.

## Regole realmente implementate

Prerequisiti obbligatori: contesto gene–malattia/ereditarietà disease-specific, LoF DEFINITIVE e fonte del meccanismo/confidenza, trascritto versionato e dati molecolari necessari al ramo. La rilevanza biologica del trascritto non è un prerequisito del percorso richiesto.
Da `PVS1_GENERAL 1.1.0`, `affected_exon_relevant`, `affected_exon_lof_tolerant` e `rescue_present` sono opzionali per il calcolo: valore assente o privo di fonte resta UNKNOWN nella decision trace e genera un warning, senza entrare nei dati mancanti bloccanti né imporre revisione o riduzione automatica della strength. Nessun valore favorevole viene inventato. Le asserzioni con fonte continuano a essere valutate e le esclusioni biologiche documentate restano bloccanti. Questi fatti non sono dedotti da VEP o cataloghi di isoforme. Un risultato ACTIVE può quindi avere controlli biologici UNKNOWN, esplicitamente segnalati nei warning.
Stop-gain e frameshift con PTC determinato: controllo di frame/coerenza, asse del prodotto, geometria delle giunzioni e predizione NMD generale (P08–P10).
Con distanza firmata dall'inizio del PTC all'ultima giunzione downstream **>50 nt**, i prerequisiti soddisfatti consentono VERY_STRONG. Distanza 50 nt o minore/nessuna giunzione downstream indirizzano al ramo senza NMD, senza rendere PVS1 automaticamente negativo.
Senza NMD: regione documentata critica con evidenza funzionale consente STRONG (P11); altrimenti perdita pura documentata >10% STRONG, <10% MODERATE, esattamente 10% REQUIRES_REVIEW (P12–P14). Lunghezza reference dalla CDS qualificata, stop escluso; nessuna percentuale di funzione dedotta.
GoF/DN/OTHER definitivo nel contesto o un'esclusione biologica esplicita e documentata consentono INACTIVE; dati mancanti non diventano un risultato negativo.
Meccanismi INFERRED/DISPUTED richiedono revisione: le riduzioni P02–P05 non sono implementate. La presenza del valore LoF senza adeguata documentazione/confidenza non è sufficiente.
Strength calcolata/applicata coincidono quando i requisiti obbligatori del ramo sono risolti, anche con i tre controlli biologici opzionali UNKNOWN; per NOT_EVALUABLE/REQUIRES_REVIEW/INACTIVE rimangono nulle. Non è una classificazione ACMG complessiva né una verifica clinica indipendente delle fonti.

## Controlli splice e altri limiti espliciti

PREDICTED/OBSERVED/UNKNOWN restano distinti. Un PTC calcolato non conferma sperimentalmente l'evento e non cambia la sua base.
Splice non canonica solo predetta: NOT_EVALUABLE (P34). Predizione canonica esplicita: i fatti molecolari/NMD sono esaminati, ma alternative e motivi atipici P15/P36 richiedono revisione, senza strength automatica.
Evento OBSERVED: riferimento RNA originale obbligatorio; qualità mancante è UNKNOWN, mentre ponderazione del saggio, attribuzione/completezza e profili misti P40–P45 sono NOT_EVALUATED e richiedono revisione. Nessuna soglia RNA inventata.
Prodotti multipli, rami splice in-frame selezionati P39/P48, start-loss e CNV restano non completamente valutabili. Non si sceglie il prodotto più dannoso e non si eseguono ricerche di siti criptici/rescue.
I check non raggiunti rimangono NOT_EVALUATED; NOT_APPLICABLE indica soltanto l'assenza di pertinenza al ramo. FAIL su NMD non equivale a FAIL del criterio.
Il risultato conserva le fonti, ma non ne certifica automaticamente la correttezza biologica. NMD è una previsione del modello generale; eccezioni specifiche richiedono revisione.

## Verifiche e problemi di integrazione

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_next/src python -m pytest -q tests/test_pvs1_calculator.py tests/test_pvs1_molecular.py tests/test_pvs1_models.py helper_next/tests/test_acmg_context.py
node --check helper_next/src/helper_variants/web/static/acmg-calculator.js
node --check helper_next/src/helper_variants/web/static/variant-browser.js
```

**95 test passati, 1 test browser opt-in saltato, 185 subtest passati**. Test mirati: Calculator, soglie 49/50/51 nt e 9/10/11%, PREDICTED/OBSERVED/UNKNOWN, contesti G2P con fonti e ambito corretto, conflitti/dati non qualificati, rilevanza del trascritto non bloccante, immutabilità, binding della route e regressioni molecolari/modelli/catalogo contesti. Sintassi della modal JavaScript riverificata; controllo del browser principale già superato.
Nuova regressione: costruzione del package in una directory temporanea e import/registrazione della route fuori dal repository. Verificati anche wheel e wheel editable in directory temporanee, senza installazioni nell'ambiente utente, download o dipendenze aggiuntive.
La route è verificata con chiamata diretta e registrazione FastAPI. Il test di trasporto HTTP asincrono è rimasto bloccato nella sandbox; la prova minima del ponte thread senza I/O va anch'essa in timeout. L'esecuzione esterna richiesta è stata rifiutata e non ripetuta.
Il test opt-in della modal è presente e verifica apertura, requisiti espandibili, fonti/soglie, dati mancanti e chiusura/focus tramite Chrome su file locali e risposte sintetiche del nuovo Calculator. Qui Chrome è bloccato da `setsockopt: Operation not permitted`: test saltato, comportamento visivo non dichiarato verificato.
I tre run dell'archivio locale non disponevano di un indice varianti accessibile; usate esclusivamente fixture sintetiche. Le strength delle fixture verificano rami algoritmici, non conclusioni cliniche.
Nessuna suite completa, modifica al vecchio Engine/Task22/Workbench, database/provider/dipendenza aggiuntiva, commit o step successivo.
