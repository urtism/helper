"""Exact transcript references from an installed offline VEP cache.

Only the region containing the allele is read. Perl's standard Storable reader
extracts the existing Ensembl objects as data; no VEP run or BioPerl is needed.
The same CDS/exon/protein qualification as REST references remains mandatory.
"""
import copy
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_transcripts import mrna_to_genomic, primary_chromosome, qualify


_EXTRACT = r'''
use strict; use warnings;
use Storable qw(thaw); use IO::Uncompress::Gunzip qw(gunzip); use JSON::PP;
my ($path, $chromosome, $gene) = @ARGV;
my $bytes; gunzip($path => \$bytes) or die "Cannot decompress VEP region";
die "Unsupported VEP serialization" unless substr($bytes, 0, 4) eq 'pst0';
my $region = thaw(substr($bytes, 4));
die "Invalid VEP region" unless ref($region) eq 'HASH' && ref($region->{$chromosome}) eq 'ARRAY';
sub utr {
    my ($value) = @_;
    return '' unless ref($value);
    return $value->{primary_seq}{seq} // '';
}
my @records;
for my $t (@{$region->{$chromosome}}) {
    next unless ($t->{_gene_stable_id} // '') eq $gene;
    next unless ($t->{stable_id} // '') =~ /^ENST[0-9]+$/;
    next unless ($t->{_source_cache} // 'Ensembl') eq 'Ensembl';
    my $facts = $t->{_variation_effect_feature_cache};
    next unless $facts && $t->{translation};
    die "Unsupported relative VEP coordinates" unless $t->{slice}{start} == 1 && $t->{slice}{strand} == 1;
    die "Unsupported VEP genetic code" unless ($facts->{codon_table} // 1) == 1;
    my @exons = map { {id => $_->{stable_id}, start => 0+$_->{start}, end => 0+$_->{end}, strand => 0+$_->{strand}} }
                    @{$facts->{sorted_exons} // []};
    push @records, {id => $t->{stable_id}, version => 0+$t->{version}, gene => $gene,
        chromosome => $t->{slice}{seq_region_name}, strand => 0+$t->{strand},
        biotype => $t->{biotype}, canonical => $t->{is_canonical} ? 1 : 0,
        hgnc => $t->{_gene_hgnc_id}, exons => \@exons,
        cds_start => 0+$t->{cdna_coding_start}, cds_end => 0+$t->{cdna_coding_end},
        cds => $facts->{translateable_seq}, protein => $facts->{peptide},
        five_prime_utr => utr($facts->{five_prime_utr}), three_prime_utr => utr($facts->{three_prime_utr}),
        protein_id => $t->{translation}{stable_id}, protein_version => 0+$t->{translation}{version}};
}
print encode_json(\@records);
'''


def _token(path):
    stat = path.stat()
    return stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@lru_cache(maxsize=16)
def _gene_records(chunk, token, gene, chromosome):
    path = Path(chunk)
    process = subprocess.run(["perl", "-e", _EXTRACT, chunk, chromosome, gene],
                             capture_output=True, text=True, timeout=15)
    if process.returncode:
        raise ValueError("VEP cache extraction failed: " + process.stderr.strip()[:300])
    if _token(path) != token:
        raise ValueError("VEP reference changed during extraction")
    return json.loads(process.stdout)


@lru_cache(maxsize=128)
def _reference(chunk, token, info_path, info_token, gene, chromosome, transcript, assembly, release):
    metadata = dict(line.split("\t", 1) for line in Path(info_path).read_text().splitlines() if "\t" in line)
    if metadata.get("assembly") != assembly or metadata.get("species") != "homo_sapiens":
        raise ValueError("VEP cache species/assembly mismatch")
    records = _gene_records(chunk, token, gene, chromosome)
    matches = [r for r in records if r["id"] + "." + str(r["version"]) == transcript]
    if len(matches) != 1:
        raise ValueError("Exact transcript/version is absent or ambiguous in the local VEP region")
    record = matches[0]
    exons, cursor = [], 1
    for exon in sorted(record["exons"], key=lambda e: e["start"], reverse=record["strand"] == -1):
        length = exon["end"] - exon["start"] + 1
        exons.append(dict(genomic_start=exon["start"], genomic_end=exon["end"], mrna_start=cursor,
                          mrna_end=cursor + length - 1))
        cursor += length
    strand = "+" if record["strand"] == 1 else "-"
    endpoints = [mrna_to_genomic(exons, strand, record[k]) for k in ("cds_start", "cds_end")]
    if None in endpoints or record["chromosome"] != chromosome:
        raise ValueError("VEP transcript boundaries/chromosome mismatch")
    lookup = dict(id=record["id"], version=record["version"], Parent=gene, species="homo_sapiens",
                  assembly_name=assembly, object_type="Transcript", seq_region_name=chromosome,
                  strand=record["strand"], biotype=record["biotype"], length=cursor - 1,
                  Exon=[dict(e, assembly_name=assembly, seq_region_name=chromosome) for e in record["exons"]],
                  Translation=dict(id=record["protein_id"], start=min(endpoints), end=max(endpoints),
                                   length=len(record["protein"])))
    cdna = record["five_prime_utr"] + record["cds"] + record["three_prime_utr"]
    hgnc = str(record.get("hgnc") or "").removeprefix("HGNC:")
    raw = dict(lookup=lookup, release_before={"releases": [int(release)]}, release_after={"releases": [int(release)]},
               cdna=dict(id=record["id"], seq=cdna), cds=dict(id=record["id"], seq=record["cds"]),
               protein=dict(id=record["protein_id"], seq=record["protein"]),
               hgnc=[dict(dbname="HGNC", primary_id="HGNC:" + hgnc)] if hgnc.isdigit() else [])
    reference = qualify(raw, transcript, assembly, release)
    if _token(Path(info_path)) != info_token:
        raise ValueError("VEP cache metadata changed during extraction")
    reference.update(artifact_digest=digest({"record": record, "metadata": metadata}),
                     source_urls={"vep_cache": Path(chunk).as_uri(), "vep_metadata": Path(info_path).as_uri()},
                     acquired_at=datetime.fromtimestamp(token[2] / 1e9, timezone.utc).isoformat(),
                     coordinate_convention="1-based inclusive; transcript 5-prime to 3-prime; CDS includes stop",
                     canonical=bool(record["canonical"]), reference_origin="LOCAL_VEP_CACHE")
    return reference


def local_transcript_reference(variant, gene, transcript, release, *, cache_root=None):
    """Read only configured/default VEP roots; never use paths supplied by a VCF."""
    result = {"source_id": "vep_transcript", "status": "NOT_AVAILABLE", "data": None}
    chromosome = str(primary_chromosome(variant["contig"]))
    assembly, release = variant["assembly"], str(release or "")
    if (not re.fullmatch(r"ENST[0-9]+\.[0-9]+", transcript or "")
            or not re.fullmatch(r"ENSG[0-9]+", gene or "") or not release.isdigit()
            or assembly not in {"GRCh37", "GRCh38"} or not re.fullmatch(r"[1-9]|1[0-9]|2[0-2]|X|Y", chromosome)):
        return result
    root = Path(cache_root or os.environ.get("HELPER_VEP_CACHE", Path.home() / ".vep")).expanduser().resolve()
    for species in ("homo_sapiens_merged", "homo_sapiens"):
        directory = root / species / (release + "_" + assembly)
        info = directory / "info.txt"
        if not info.is_file():
            continue
        for chunk in sorted((directory / chromosome).glob("*.gz")):
            span = re.fullmatch(r"([0-9]+)-([0-9]+)\.gz", chunk.name)
            if not span or not int(span[1]) <= variant["position"] <= int(span[2]):
                continue
            try:
                reference = _reference(str(chunk), _token(chunk), str(info), _token(info), gene, chromosome,
                                       transcript, assembly, release)
                return dict(result, status="CACHED", data=copy.deepcopy(reference))
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
                return dict(result, status="ERROR", missing="Local VEP reference unavailable: " + str(exc))
    return result
