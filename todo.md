# TODO

Usare questo file come lista operativa per le modifiche future.

Regola di lavoro:
- aggiungere qui le modifiche da apportare prima di iniziare;
- rimuovere le voci quando sono state completate;
- lasciare solo attivita ancora aperte o bloccate.

## Da Fare

### Priorita immediata: matrice E2E short variant calling

- Preparare fixture sintetiche schema v2 per cinque scenari: only-case, family, case-control, tumor-normal e run mista con tutti i tipi di analisi.
- Aggiungere uno script E2E Nextflow schema v2 con wrapper locali, sul modello di `scripts/run_nextflow_demo.sh`.
- Verificare che only-case, family e case-control producano GVCF per campione e un solo `run.GATK.vcf` multisample.
- Verificare che ogni coppia tumor-normal produca un VCF filtrato con Mutect2 + FilterMutectCalls e che tumor/normal non entrino nel joint VCF germline.
- Verificare nomi, numero di campioni e genotipi contenuti nei VCF prodotti, non solo l'esistenza dei file.
- Eseguire la matrice sia con ingresso BAM sia, almeno per una run mista, partendo da FASTQ attraverso alignment e preprocessing.
- Verificare la propagazione contemporanea del VCF germline e dei VCF tumor-normal attraverso `vcf_norm`, `vcf_filter`, `vcf_to_tsv` e VEP.
- Verificare log, status TSV, conteggi della run matrix e arresto dei downstream step quando fallisce un campione o un gruppo.
- Aggiungere una validazione del read-group `SM` dei BAM rispetto a `sample_name`, necessaria per associare correttamente tumor e normal in Mutect2.
- Dopo i test con wrapper, eseguire una smoke run con piccoli BAM reali e installazioni reali di GATK, bcftools e VEP.

### Dopo la stabilizzazione E2E

- Estendere IGV con confronto multi-campione per trio e tumor-normal.
- Integrare in IGV tracce locali per CNV/SV e annotazioni geniche quando prodotte dalla pipeline.
- Esportare un file PED dai campi `sample_name`, `father`, `mother`, `sex` e `affected`, includendo gli individui non sequenziati referenziati come genitori.
- Implementare analisi downstream di segregazione, ereditarieta e prioritizzazione de novo usando i gruppi family.
- Implementare un sistema di prioritizzazione data-driven affiancato al motore decisionale attuale: costruire dataset di training e validazione versionati, prevenire leakage tra varianti/gene/famiglie, integrare MAF e copertura, conseguenza coerente con il meccanismo di malattia, ClinVar, predittori di danno e splicing, ereditarieta e compound heterozygosity; produrre probabilita calibrate, spiegazioni per variante, confronto con il baseline a regole e monitoraggio delle prestazioni per release e sottogruppo clinico.
- Rendere esplicita la configurazione somatica per germline resource, panel of normals, contaminazione e orientation-bias filtering.
- Implementare i moduli ancora mancanti: adapter trimming, FASTQ filtering, BAM filtering e UMI merging.
- Implementare nel DAG Nextflow i quattro tipi di Variant Calling esposti dalla UI: Short variants, CNV, SV e metilazione, con canali di input/output, validazione, log e status dedicati per ciascun ramo.
- Implementare postannotation nel DAG Nextflow.
- Completare e validare container e runtime per profili local e SLURM/HPC.

## In Corso

### Catalogo tracce IGV

- Aggiungere un menu compatto per mostrare o nascondere trascritti, target, varianti del campione, ClinVar, gnomAD e regioni difficili GIAB.
- Aggiungere una vista dedicata alle split reads con soft clipping e allineamenti supplementari evidenziati.
- Rendere le tracce compatibili con hg19/GRCh37 e hg38/GRCh38, con stato di disponibilita e sorgente espliciti.
- Verificare caricamento, rimozione, persistenza della selezione e comportamento responsive.

## Bloccate

- Nessuna attivita bloccata.
