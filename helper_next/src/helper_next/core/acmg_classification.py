"""Small manual ACMG evidence worksheet, with an explicit point model.

Points: Tavtigian 2020, Tables 2–3 (doi:10.1002/humu.24088).
This combines selected assertions; it does not discover or validate evidence.
"""
VERSION = "helper-acmg-classification-1.0"
MODEL = "POINTS_2020"
POINTS = {"SUPPORTING": 1, "MODERATE": 2, "STRONG": 4, "VERY_STRONG": 8}
CLASSES = {"NOT_EVALUATED": "Non valutata", "PATHOGENIC": "P", "LIKELY_PATHOGENIC": "LP",
           "VUS": "VUS", "LIKELY_BENIGN": "LB", "BENIGN": "B"}
SOURCE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC8011844/"
PM2_SOURCE = "https://www.clinicalgenome.org/site/assets/files/5182/pm2_-_svi_recommendation_-_approved_sept2020.pdf"

_LABELS = {
    "PVS1": "Perdita di funzione", "PS1": "Stesso cambiamento amminoacidico", "PS2": "De novo confermato",
    "PS3": "Evidenze funzionali", "PS4": "Arricchimento nei casi", "PM1": "Regione critica",
    "PM2": "Rarità nella popolazione", "PM3": "Osservazione in trans", "PM4": "Lunghezza proteica alterata",
    "PM5": "Altra sostituzione nello stesso residuo", "PM6": "De novo presunto", "PP1": "Cosegregazione",
    "PP2": "Contesto missenso", "PP3": "Predizioni computazionali", "PP4": "Specificità fenotipica",
    "BA1": "Frequenza incompatibile con patogenicità", "BS1": "Frequenza superiore all'atteso",
    "BS2": "Osservazione in soggetti sani", "BS3": "Funzione conservata", "BS4": "Mancata segregazione",
    "BP1": "Missenso con altro meccanismo atteso", "BP2": "Contesto allelico", "BP3": "Indel in regione ripetitiva",
    "BP4": "Predizioni senza impatto", "BP5": "Spiegazione molecolare alternativa", "BP7": "Variante sinonima senza impatto",
}


def catalog():
    result = []
    for code, label in _LABELS.items():
        strength = ("STAND_ALONE" if code == "BA1" else "VERY_STRONG" if code == "PVS1" else "SUPPORTING" if code == "PM2"
                    else "STRONG" if code.startswith(("PS", "BS")) else "MODERATE" if code.startswith("PM") else "SUPPORTING")
        result.append(dict(code=code, label=label, direction="BENIGN" if code.startswith("B") else "PATHOGENIC", default_strength=strength))
    return result


def normalize(criteria):
    if not isinstance(criteria, list) or len(criteria) > len(_LABELS):
        raise ValueError("Elenco dei criteri ACMG non valido")
    result, seen = [], set()
    for item in criteria:
        if not isinstance(item, dict) or not isinstance(item.get("code"), str) or item["code"] not in _LABELS:
            raise ValueError("Criterio ACMG sconosciuto; PP5 e BP6 non sono utilizzati")
        code = item["code"]
        if code in seen:
            raise ValueError("Criterio ACMG duplicato: " + code)
        seen.add(code)
        strength = item.get("strength")
        if not isinstance(strength, str) or (strength != "STAND_ALONE" if code == "BA1" else strength not in POINTS):
            raise ValueError("Strength non valida per " + code)
        row = dict(code=code, strength=strength)
        for name in ("note", "source"):
            text = item.get(name, "")
            if not isinstance(text, str) or len(text) > 1000:
                raise ValueError("Nota o fonte del criterio troppo lunga")
            row[name] = text.strip()
        origin = item.get("origin", "MANUAL")
        if not isinstance(origin, str) or origin not in {"MANUAL", "PVS1_SAVED", "PVS1_AUTO"} or (origin != "MANUAL" and code != "PVS1"):
            raise ValueError("Origine del criterio non valida")
        row["origin"] = origin
        if origin == "PVS1_SAVED":
            revision = item.get("pvs1_revision")
            if type(revision) is not int or revision < 1:
                raise ValueError("Revisione PVS1 non valida")
            row["pvs1_revision"] = revision
        if origin == "PVS1_AUTO":
            token = item.get("pvs1_evaluation_id")
            if not isinstance(token, str) or len(token) != 32 or any(char not in "0123456789abcdef" for char in token):
                raise ValueError("Valutazione PVS1 automatica non valida")
            row["pvs1_evaluation_id"] = token
        result.append(row)
    return sorted(result, key=lambda row: list(_LABELS).index(row["code"]))


def combine(criteria, model="POINTS_2020", *, splice=False):
    if model != MODEL:
        raise ValueError("Modello di classificazione non supportato")
    rows = normalize(criteria)
    codes = {row["code"] for row in rows}
    warnings, conflicts = [], []
    for left, right in (("PS2", "PM6"), ("PS1", "PM5"), ("PVS1", "PM4"), ("BA1", "BS1")):
        if {left, right} <= codes:
            conflicts.append(left + " e " + right + ": verificare il doppio conteggio dell'evidenza")
    if splice and {"PVS1", "PP3"} <= codes:
        conflicts.append("PVS1 splice e PP3: l'evidenza splice non può essere conteggiata due volte")
    path = [row for row in rows if row["code"].startswith("P")]
    benign = [row for row in rows if row["code"].startswith("B") and row["code"] != "BA1"]
    total = sum(POINTS[row["strength"]] for row in path) - sum(POINTS[row["strength"]] for row in benign)
    if path and (benign or "BA1" in codes):
        warnings.append("Sono presenti evidenze in entrambe le direzioni: controllarne indipendenza e pertinenza")
    classification = "NOT_EVALUATED" if not rows else "VUS"
    if "BA1" in codes:
        classification = "BENIGN"
        if path:
            conflicts.append("BA1 insieme a evidenze patogeniche: combinazione da rivedere")
    elif rows:
        classification = ("PATHOGENIC" if total >= 10 else "LIKELY_PATHOGENIC" if total >= 6 else
                          "BENIGN" if total <= -7 else "LIKELY_BENIGN" if total <= -1 else "VUS")
    if conflicts:
        classification = "VUS"
    return dict(model=model, model_label="ACMG a punti · Tavtigian 2020", version=VERSION, source_url=SOURCE,
                criteria=rows, total_points=total, classification=classification, label=CLASSES[classification],
                requires_review=bool(conflicts), warnings=conflicts + warnings)
