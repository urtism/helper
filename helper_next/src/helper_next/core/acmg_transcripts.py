"""Targeted, release-pinned Ensembl references; no ACMG interpretation.

The JSON cache contains public reference data only. Coordinates are 1-based
inclusive; cDNA/CDS run 5' to 3' on either genomic strand. CDS includes stop.
"""
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from helper_next.core.acmg_digest import digest
from helper_next.core.analysis_history import now


VERSION = "helper-transcript-reference-1.0"
STOPS = {"TAA", "TAG", "TGA"}
_BASES = "TCAG"
_AA = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
_CODE = dict(zip((a + b + c for a in _BASES for b in _BASES for c in _BASES), _AA))


def translate(cds):
    return "".join(_CODE.get(cds[i:i + 3], "?") for i in range(0, len(cds), 3))


def complement(sequence):
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def genomic_to_mrna(exons, strand, position):
    for exon in exons:
        if exon["genomic_start"] <= position <= exon["genomic_end"]:
            offset = position - exon["genomic_start"] if strand == "+" else exon["genomic_end"] - position
            return exon["mrna_start"] + offset
    return None


def mrna_to_genomic(exons, strand, position):
    for exon in exons:
        if exon["mrna_start"] <= position <= exon["mrna_end"]:
            offset = position - exon["mrna_start"]
            return exon["genomic_start"] + offset if strand == "+" else exon["genomic_end"] - offset
    return None


def qualify(raw, transcript, assembly, release):
    """Qualify one Ensembl response bundle, independently of the selected variant."""
    lookup = raw["lookup"]
    accession, version = transcript.rsplit(".", 1)
    if (lookup["id"] != accession or str(lookup["version"]) != version
            or lookup["assembly_name"] != assembly or lookup["species"] != "homo_sapiens"
            or lookup["object_type"] != "Transcript"):
        raise ValueError("Transcript identity/version/species/assembly mismatch")
    if raw["release_before"] != raw["release_after"] or raw["release_before"] != {"releases": [int(release)]}:
        raise ValueError("Ensembl release mismatch or release changed during retrieval")
    if lookup["strand"] not in (1, -1) or lookup["seq_region_name"] not in {str(i) for i in range(1, 23)} | {"X", "Y"}:
        raise ValueError("Only primary nuclear chromosomes and standard genetic code are supported")
    strand = "+" if lookup["strand"] == 1 else "-"
    exons, cursor = [], 1
    for row in sorted(lookup["Exon"], key=lambda e: e["start"], reverse=strand == "-"):
        if (row["assembly_name"] != assembly or row["seq_region_name"] != lookup["seq_region_name"]
                or row["strand"] != lookup["strand"] or row["start"] < 1 or row["end"] < row["start"]):
            raise ValueError("Exon identity/coordinates mismatch")
        if exons and (row["start"] <= exons[-1]["genomic_end"] if strand == "+"
                      else row["end"] >= exons[-1]["genomic_start"]):
            raise ValueError("Overlapping reference exons")
        length = row["end"] - row["start"] + 1
        exons.append({"exon_id": row["id"], "genomic_start": row["start"], "genomic_end": row["end"],
                      "mrna_start": cursor, "mrna_end": cursor + length - 1})
        cursor += length
    cdna, cds, protein = (raw[k]["seq"].upper() for k in ("cdna", "cds", "protein"))
    if not exons or len(cdna) != cursor - 1 or len(cdna) != lookup["length"] or set(cdna) - set("ACGT"):
        raise ValueError("Complete unambiguous cDNA/exon structure required")
    translation = lookup["Translation"]
    if (raw["cdna"]["id"] != accession or raw["cds"]["id"] != accession
            or raw["protein"]["id"] != translation["id"]):
        raise ValueError("Sequence identifiers disagree with transcript/translation")
    endpoints = [genomic_to_mrna(exons, strand, translation[k]) for k in ("start", "end")]
    if None in endpoints:
        raise ValueError("Translation boundary outside exons")
    cds_start = min(endpoints)
    cds_end = cds_start + len(cds) - 1
    if (not cds or len(cds) % 3 or cds[:3] != "ATG" or cds[-3:] not in STOPS
            or cdna[cds_start - 1:cds_end] != cds or max(endpoints) != cds_end
            or translate(cds) != protein + "*" or len(protein) != translation["length"]):
        raise ValueError("CDS/translation disagreement, missing complete CDS or unsupported genetic code")
    segments = []
    for exon in exons:
        start, end = max(cds_start, exon["mrna_start"]), min(cds_end, exon["mrna_end"])
        if start <= end:
            coordinates = [mrna_to_genomic(exons, strand, p) for p in (start, end)]
            segments.append({"exon_id": exon["exon_id"], "mrna_start": start, "mrna_end": end,
                             "genomic_start": min(coordinates), "genomic_end": max(coordinates)})
    mane_types = {m["type"] for m in lookup.get("MANE", [])}
    return {"transcript": {"namespace": "Ensembl", "accession": accession, "version": version},
            "assembly": assembly, "annotation_release": str(release), "chromosome": lookup["seq_region_name"],
            "gene_ids": [lookup["Parent"], *[x["primary_id"] for x in raw["hgnc"] if x.get("dbname") == "HGNC"]],
            "strand": strand, "biotype": lookup["biotype"],
            "mane": "SELECT" if "MANE_Select" in mane_types else "PLUS_CLINICAL" if "MANE_Plus_Clinical" in mane_types else "NONE",
            "mane_records": lookup.get("MANE", []), "exons": exons,
            "canonical": bool(lookup.get("is_canonical")), "appris": lookup.get("appris"),
            "protein_accession": translation["id"],
            "cds_start": cds_start, "cds_end": cds_end, "coding_segments": segments,
            "cdna": cdna, "cds": cds, "protein": protein, "protein_length": len(protein),
            "junctions": [{"upstream_exon": left["exon_id"], "downstream_exon": right["exon_id"],
                           "mrna_position": left["mrna_end"],
                           "upstream_genomic": mrna_to_genomic(exons, strand, left["mrna_end"]),
                           "downstream_genomic": mrna_to_genomic(exons, strand, right["mrna_start"])}
                          for left, right in zip(exons, exons[1:])]}


class TranscriptReferenceProvider:
    def __init__(self, cache=None, release=None, fetch_json=None, rest_url=None):
        self.cache = Path(cache or os.environ.get("HELPER_TRANSCRIPT_CACHE", Path.home() / ".cache/helper/transcripts"))
        self.release = str(release or os.environ.get("HELPER_ENSEMBL_RELEASE", ""))
        self.fetch_json = fetch_json or self._fetch_json
        self.rest_url = rest_url or os.environ.get("HELPER_ENSEMBL_REST_URL", "")

    def _host(self, assembly):
        return self.rest_url.rstrip("/") or (
            "https://rest.ensembl.org" if assembly == "GRCh38" else "https://grch37.rest.ensembl.org")

    def gene_transcripts(self, gene, assembly, fetch=False):
        """Cache a release-qualified expanded gene, including noncoding members.

        The catalog establishes completeness; VEP consequence rows alone cannot.
        It shares the transcript cache directory and never substitutes releases.
        """
        result = {"source_id": "ensembl_gene_transcripts", "status": "AVAILABLE", "data": None,
                  "release": self.release or None, "cache_policy": VERSION}
        try:
            if not re.fullmatch(r"ENSG[0-9]+(?:\.[0-9]+)?", gene):
                raise ValueError("An exact Ensembl gene identifier is required")
            if assembly not in ("GRCh37", "GRCh38") or not self.release.isdigit():
                raise ValueError("Explicit assembly and annotation Ensembl release required")
            key = {"schema": VERSION, "assembly": assembly, "gene": gene, "release": self.release}
            path = self.cache / (digest(key)["value"] + ".json")
            if path.is_file():
                cached = json.loads(path.read_text())
                if cached["key"] != key or cached["digest"] != digest(cached["raw"]):
                    raise ValueError("Gene catalog cache identity/checksum mismatch")
                raw, urls, acquired_at = cached["raw"], cached["urls"], cached["acquired_at"]
            elif fetch:
                raw, urls = {}, {}

                def read(name, endpoint, **params):
                    urls[name] = self._host(assembly) + endpoint + "?" + urlencode({"content-type": "application/json", **params})
                    raw[name] = self.fetch_json(urls[name])
                    return raw[name]

                if read("release_before", "/info/data") != {"releases": [int(self.release)]}:
                    raise ValueError("Annotation release is unavailable on this Ensembl host; configure its matching archive")
                read("lookup", "/lookup/id/" + gene.split(".")[0], expand=1, mane=1)
                read("release_after", "/info/data")
                acquired_at = now()
            else:
                result["missing"] = "Gene transcript catalog is absent from the local Ensembl cache"
                return result
            lookup = raw["lookup"]
            if (lookup["id"] != gene.split(".")[0] or lookup["assembly_name"] != assembly
                    or lookup["object_type"] != "Gene" or lookup["species"] != "homo_sapiens"
                    or raw["release_before"] != raw["release_after"]
                    or raw["release_before"] != {"releases": [int(self.release)]}
                    or ("." in gene and str(lookup["version"]) != gene.rsplit(".", 1)[1])):
                raise ValueError("Gene identity/assembly/release mismatch")
            transcripts, seen = [], set()
            for tx in lookup["Transcript"]:
                accession = tx["id"] + "." + str(tx["version"])
                if (not re.fullmatch(r"ENST[0-9]+\.[0-9]+", accession) or accession in seen
                        or tx.get("Parent") != lookup["id"] or tx.get("assembly_name") != assembly
                        or tx.get("seq_region_name") != lookup["seq_region_name"]
                        or tx.get("strand") != lookup["strand"]):
                    raise ValueError("Gene transcript membership or identity mismatch")
                seen.add(accession)
                mane = {m["type"] for m in tx.get("MANE", [])}
                exons, cursor = [], 1
                for exon in sorted(tx.get("Exon", []), key=lambda e: e["start"], reverse=tx["strand"] == -1):
                    length = exon["end"] - exon["start"] + 1
                    if length <= 0:
                        raise ValueError("Invalid gene transcript exon")
                    exons.append({"genomic_start": exon["start"], "genomic_end": exon["end"],
                                  "mrna_start": cursor, "mrna_end": cursor + length - 1})
                    cursor += length
                transcripts.append({"transcript": accession, "biotype": tx.get("biotype"),
                                    "mane": "SELECT" if "MANE_Select" in mane else "PLUS_CLINICAL" if "MANE_Plus_Clinical" in mane else "NONE",
                                    "canonical": bool(tx.get("is_canonical")), "appris": tx.get("appris"),
                                    "strand": "+" if tx["strand"] == 1 else "-", "exons": exons,
                                    "has_translation": bool(tx.get("Translation")),
                                    "start": tx.get("start"), "end": tx.get("end")})
            if not transcripts:
                raise ValueError("Empty gene transcript catalog")
            if not path.is_file():
                self.cache.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", dir=self.cache, delete=False) as stream:
                    json.dump({"key": key, "raw": raw, "urls": urls, "acquired_at": acquired_at, "digest": digest(raw)}, stream)
                    temporary = Path(stream.name)
                temporary.replace(path)
            result.update(status="CACHED", acquired_at=acquired_at,
                          data={"gene": lookup["id"], "assembly": assembly, "chromosome": lookup["seq_region_name"],
                                "annotation_release": self.release, "transcripts": transcripts,
                                "source_urls": urls, "artifact_digest": digest(raw), "complete": True})
        except HTTPError as exc:
            result.update(status="ERROR", missing="Ensembl gene request failed with HTTP " + str(exc.code))
        except (URLError, TimeoutError, ConnectionError):
            result.update(status="UNREACHABLE", missing="Ensembl gene catalog could not be retrieved")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            result.update(status="ERROR", missing="Gene catalog unavailable: " + str(exc))
        return result

    @staticmethod
    def _fetch_json(url):
        request = Request(url, headers={"Accept": "application/json", "Content-Type": "application/json"})
        with urlopen(request, timeout=20) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("Transcript response exceeds targeted retrieval limit")
        return json.loads(data)

    def get(self, transcript, assembly, fetch=False):
        result = {"source_id": "ensembl_transcript", "status": "AVAILABLE", "data": None,
                  "release": self.release or None, "acquired_at": None, "cache_policy": VERSION}
        try:
            if not re.fullmatch(r"ENST[0-9]+\.[0-9]+", transcript):
                raise ValueError("An exact versioned Ensembl transcript is required; no RefSeq substitution")
            if assembly not in ("GRCh37", "GRCh38") or not self.release.isdigit():
                raise ValueError("Explicit GRCh37/GRCh38 and HELPER_ENSEMBL_RELEASE required")
            key = {"schema": VERSION, "assembly": assembly, "transcript": transcript, "release": self.release}
            path = self.cache / (digest(key)["value"] + ".json")
            if path.is_file():
                cached = json.loads(path.read_text())
                if cached["key"] != key or cached["digest"] != digest(cached["raw"]):
                    raise ValueError("Transcript cache identity/checksum mismatch")
                raw, acquired_at, urls = cached["raw"], cached["acquired_at"], cached["urls"]
                result["status"] = "CACHED"
            elif fetch:
                host = self._host(assembly)
                accession = transcript.split(".")[0]
                raw, urls = {}, {}

                def read(name, endpoint, **params):
                    url = host + endpoint + "?" + urlencode({"content-type": "application/json", **params})
                    urls[name] = url
                    raw[name] = self.fetch_json(url)
                    return raw[name]

                read("release_before", "/info/data")
                if raw["release_before"] != {"releases": [int(self.release)]}:
                    raise ValueError("Configured release is unavailable on this Ensembl host")
                lookup = read("lookup", "/lookup/id/" + accession, expand=1, mane=1)
                if str(lookup.get("version")) != transcript.rsplit(".", 1)[1] or lookup.get("assembly_name") != assembly:
                    raise ValueError("Requested transcript version/assembly unavailable; no latest-version substitution")
                read("cdna", "/sequence/id/" + accession, type="cdna")
                read("cds", "/sequence/id/" + accession, type="cds")
                read("protein", "/sequence/id/" + lookup["Translation"]["id"], type="protein")
                try:
                    read("hgnc", "/xrefs/id/" + lookup["Parent"], external_db="HGNC")
                except OSError:
                    # The Ensembl gene remains identified. HGNC contexts will
                    # explicitly fail their identity check if xrefs are missing.
                    raw["hgnc"] = []
                    raw["hgnc_missing"] = "HGNC cross-reference retrieval failed; no equivalence inferred"
                read("release_after", "/info/data")
                acquired_at = now()
            else:
                result["missing"] = "Exact transcript/assembly/release is absent from the local cache; targeted fetch not enabled"
                return result
            reference = qualify(raw, transcript, assembly, self.release)
            reference.update(source_urls=urls, acquired_at=acquired_at, artifact_digest=digest(raw),
                             limitations=[raw["hgnc_missing"]] if raw.get("hgnc_missing") else [],
                             coordinate_convention="1-based inclusive; transcript 5-prime to 3-prime; CDS includes stop")
            if result["status"] != "CACHED":
                self.cache.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", dir=self.cache, delete=False) as stream:
                    json.dump({"key": key, "raw": raw, "urls": urls, "acquired_at": acquired_at, "digest": digest(raw)}, stream)
                    temporary = Path(stream.name)
                temporary.replace(path)
                result["status"] = "CACHED"
            result.update(data=reference, acquired_at=acquired_at)
        except HTTPError as exc:
            result.update(status="ERROR", missing="Ensembl targeted request failed with HTTP " + str(exc.code))
        except (URLError, TimeoutError, ConnectionError):
            result.update(status="UNREACHABLE", missing="Ensembl targeted request could not be completed")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            result.update(status="ERROR", missing="Transcript reference unavailable: " + str(exc))
        return result
