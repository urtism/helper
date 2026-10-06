"""Versioned ACMG Secondary Findings gene-list snapshots."""


SF_V3_0 = sorted("""
APC RET BRCA1 BRCA2 PALB2 SDHD SDHAF2 SDHC SDHB MAX TMEM127 BMPR1A SMAD4 TP53
MLH1 MSH2 MSH6 PMS2 MEN1 MUTYH NF2 STK11 PTEN RB1 TSC1 TSC2 VHL WT1 FBN1
TGFBR1 TGFBR2 SMAD3 ACTA2 MYH11 PKP2 DSP DSC2 TMEM43 DSG2 RYR2 CASQ2 TRDN
TNNT2 LMNA FLNC TTN COL3A1 LDLR APOB PCSK9 MYH7 MYBPC3 TNNI3 TPM1 MYL3 ACTC1
PRKAG2 MYL2 KCNQ1 KCNH2 SCN5A BTD GLA OTC GAA HFE ACVRL1 ENG RYR1 CACNA1S
HNF1A RPE65 ATP7B
""".split())
SF_V3_1 = sorted(set(SF_V3_0) | {"BAG3", "DES", "RBM20", "TNNC1", "TTR"})
SF_V3_2 = sorted(set(SF_V3_1) | {"CALM1", "CALM2", "CALM3"})
SF_V3_3 = sorted(set(SF_V3_2) | {"ABCD1", "CYP27A1", "PLN"})


_VERSIONS = [
    ("3.3", 2025, SF_V3_3, "40568962", True),
    ("3.2", 2023, SF_V3_2, "37347242", False),
    ("3.1", 2022, SF_V3_1, "35802134", False),
    ("3.0", 2021, SF_V3_0, "34012068", False),
]


def catalog():
    return [{
        "source": "acmg", "id": "sf-v{}".format(version),
        "name": "ACMG Secondary Findings v{}".format(version), "version": version,
        "version_created": str(year), "disease_group": "Secondary findings",
        "disease_sub_group": "", "relevant_disorders": ["ACMG SF", "Secondary findings"],
        "gene_count": len(genes), "types": ["ACMG Secondary Findings"],
        "current": current,
    } for version, year, genes, _, current in _VERSIONS]


def detail(identifier):
    normalized = str(identifier or "").lower().replace("sf-v", "").replace("v", "")
    for version, year, genes, pmid, current in _VERSIONS:
        if normalized == version:
            return {
                **next(item for item in catalog() if item["version"] == version),
                "genes": {"all": list(genes)}, "gene_counts": {"all": len(genes)},
                "fetched_at": "{} snapshot".format(year),
                "source_url": "https://pubmed.ncbi.nlm.nih.gov/{}/".format(pmid),
                "publication_pmid": pmid, "current": current,
            }
    return None
