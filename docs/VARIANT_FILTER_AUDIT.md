# Verifica dei campi usati dai filtri delle varianti

Verifica del 5 novembre 2026. I filtri lavorano sul campione completo già
caricato, senza richieste di rete, modifiche alle varianti o ricalcoli Priority.

| Controllo | Informazioni usate |
| --- | --- |
| Geni / pannello | `filter_data.annotations[].gene`, senza distinzione maiuscole/minuscole |
| Conseguenza | `filter_data.annotations[].consequence`; separazione delle conseguenze multiple con `&` |
| Maximum AF | `population_af` della variante, lo stesso valore AF_max della tabella, comprensivo delle evidenze gnomAD già acquisite |
| Frequenza di una popolazione | Campo AF nominato nelle informazioni dell'annotazione corrispondente, ad esempio `AFR_AF` o `EUR_AF` |
| Keep variants with AF not reported | Mantiene o esclude AF assenti/non valide quando è impostata una soglia AF |
| Classe Priority | `priority.band` (`P1`–`P4`) |
| Intervallo Priority | `priority.normalized_score` (0–100), con estremi inclusi |
| ClinVar | Classificazioni dello snapshot locale associato alla variante; nessun ripiego sul significato clinico del VCF |
| Dominante / recessivo | Zigosità del campione: rispettivamente `het` / `hom_alt` |
| X-linked / Y-linked / mitocondriale | Cromosoma della variante, gestendo il prefisso `chr` |
| Compound candidate | Alleli eterozigoti distinti del campione con annotazioni nello stesso gene |
| Origine parentale | Presenza dell'allele nelle chiamate del probando e dei genitori identificati nei metadati familiari |
| Parental compound | Alleli eterozigoti nello stesso gene con origine parentale complementare |
| Pedigree | Presenza/assenza dell'allele nei membri selezionati della famiglia |
| VCF FILTER | `filter_status` delle chiamate del campione; flag separati da `;`/`,` e alias normalizzati |
| DP minimo | `depth` del campione |
| VAF minima | `allele_fraction` del campione, nell'intervallo 0–1 |
| QUAL minima | `quality` della variante nelle chiamate del campione; non `genotype_quality`/GQ |

DP, VAF e QUAL mantengono l'aggregazione esistente: il massimo delle chiamate
della stessa variante nello stesso campione. Le chiamate degli altri campioni
non contribuiscono a queste soglie.

Più valori nella stessa categoria si combinano con OR; categorie diverse con
AND. Geni e conseguenze devono corrispondere alla stessa annotazione. I match
su trascritti alternativi non sostituiscono la riga canonica o i punteggi già
calcolati. Le etichette di ereditarietà restano filtri per candidati.

Le soglie numeriche sono inclusive. I valori mancanti, vuoti, non numerici o
non finiti non diventano zero. AF/VAF fuori da 0–1 e Priority fuori da 0–100
non superano le soglie; lo zero valido continua a essere accettato. I valori
decimali e in notazione scientifica sono supportati.

## Correzioni emerse dalla verifica

- Maximum AF usava la vecchia frequenza dell'annotazione VCF anche quando la
  variante mostrava un massimo aggiornato da gnomAD: ora usa `population_af`.
- Una frequenza malformata poteva essere convertita in zero e passare come
  rara: ora viene trattata come mancante.
- Soglie pari a zero e confronti numerici potevano ammettere valori vuoti o
  non numerici: ora richiedono un valore numerico valido nel campo corretto.
- I flag FILTER con spazi o alias non coincidevano con la selezione: ora si
  normalizzano spazi, maiuscole e alias prima del confronto.

## Verifica eseguita

`helper_next/tests/test_variant_filter_audit.py` controlla separatamente tutti
i campi, combinazioni di categorie, limiti, valori mancanti/malformati e flag.
Comprende una prova Chrome che imposta i controlli reali del pannello, invia il
form e confronta gli ID restituiti con risultati attesi indipendenti, verificando
anche l'assenza di richieste e modifiche ai dati originali.

Le regressioni in `test_sample_priority_loading.py` coprono inoltre il confronto
con le query SQL sui dati indicizzati, il matching ClinVar locale, i dati
familiari e il mantenimento dell'elenco completo durante filtri e ordinamenti.
