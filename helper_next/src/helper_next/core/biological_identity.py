"""Offline biological identities; no cache writes or implicit fetching.

RESOLVED identifies a qualified context, not a clinical interpretation. Every
UNRESOLVED result has a null reference and retains its original input. Existing
SQL IDs, transcript cache keys and mechanism snapshot hashes are untouched.
"""
import re
import sqlite3

from helper_variants import indexer
from helper_variants.liftover import ASSEMBLY_ACCESSIONS, _assembly, _chromosome
from helper_next.core import acmg_reference, acmg_transcripts
from helper_next.core import acmg_mechanism_normalizer as mechanism
from helper_next.core.acmg_digest import digest


CONTRACT_VERSION = "helper-biological-identity-1"
ALLELE_CONTRACT_VERSION = "helper-genomic-allele-2"
__all__ = ["CONTRACT_VERSION", "ALLELE_CONTRACT_VERSION", "allele_refs", "allele_refs_batch", "transcript_context_ref", "association_ref"]


def _result(field, original, identity=None, reason="", **context):
    prefixes = {"allele_ref": "ga2:", "transcript_context_ref": "tc1:", "association_ref": "gd1:"}
    version = ALLELE_CONTRACT_VERSION if field == "allele_ref" else CONTRACT_VERSION
    payload = dict(contract=version, kind=field, **identity) if identity is not None else None
    return dict(contract_version=version,
                status="RESOLVED" if identity is not None else "UNRESOLVED",
                reason=reason, original=original, identity=payload,
                **{field: prefixes[field] + digest(payload)["value"] if payload is not None else None},
                **context)


def _positive_integer(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r"[0-9]+", str(value)) or int(value) < 1:
        raise ValueError("A positive integer is required")
    return int(value)


def _allele_contig(build, chromosome, fasta):
    """Use declared primary accessions; never guess alt/decoy/mitochondrial identity."""
    name = _chromosome(chromosome)
    primary = {label: accession for label, accession in ASSEMBLY_ACCESSIONS[build].items() if label != "MT"}
    label = next((label for label, accession in primary.items() if name in (label, accession)), None)
    if label is not None:
        qualified = primary[label]
        candidates = {chromosome.strip(), label, "chr" + label, qualified}
    else:
        if any(name == accession for other in ASSEMBLY_ACCESSIONS.values()
               for label, accession in other.items() if label != "MT"):
            raise ValueError("Primary chromosome accession does not match the declared assembly")
        if not re.fullmatch(r"(?:(?:NC|NG|NT|NW)_[0-9]+|[A-Z]{1,2}[0-9]+)\.[1-9][0-9]*", name):
            raise ValueError("Non-primary/mitochondrial contigs require an explicit versioned genomic accession; no alias equivalence inferred")
        qualified = name
        candidates = {chromosome.strip(), qualified, "chr" + qualified}
    if fasta is None:
        return qualified, None
    matches = candidates.intersection(fasta.contigs)
    if len(matches) != 1:
        raise ValueError("Qualified contig is absent or has ambiguous aliases in the local FASTA")
    return qualified, matches.pop()


def allele_refs_batch(alleles, *, record=None, checksum_reference=True):
    """Same ga2 results, sharing reference resources only for this operation.

    Keep all per-allele REF and normalization checks. File handles, FAI contents,
    declared reference metadata and qualified contigs expire with the batch.
    Browsing can omit the whole-file checksum; its provenance then has no digest.
    """
    contexts = {}
    try:
        return [allele_refs(*allele, record=record, _contexts=contexts,
                            checksum_reference=checksum_reference) for allele in alleles]
    finally:
        for context in contexts.values():
            fasta = context.get("fasta")
            if fasta is not None:
                fasta.close()


def allele_refs(assembly, chromosome, position, reference, alternates, *, record=None, _contexts=None,
                checksum_reference=True):
    """One result per comma-separated VCF ALT, in original order (1-based index).

    Hash the declared assembly, qualified contig and normalized VCF allele,
    independently of FASTA files. A local reference verifies REF and left-aligns
    indels; SNVs without one carry explicit UNVERIFIED reference provenance.
    """
    if _contexts is None:
        return allele_refs_batch([(assembly, chromosome, position, reference, alternates)], record=record,
                                 checksum_reference=checksum_reference)[0]
    alternatives = alternates.split(",") if isinstance(alternates, str) else [alternates]
    results = []
    for alt_index, alternate in enumerate(alternatives, 1):
        original = dict(assembly=assembly, chromosome=chromosome, position=position,
                        reference=reference, alternate=alternate, alt_index=alt_index)
        fasta = None
        provenance = dict(source_file=None, digest=None, ref_status="UNVERIFIED", normalization="NOT_PERFORMED")
        try:
            build = _assembly(assembly)
            pos = _positive_integer(position)
            if not isinstance(chromosome, str) or not chromosome.strip():
                raise ValueError("An explicit chromosome/contig is required")
            if not isinstance(reference, str) or not isinstance(alternate, str):
                raise ValueError("VCF REF and ALT must be sequence strings")
            ref, alt = reference.upper(), alternate.upper()
            if not re.fullmatch(r"[ACGT]+", ref) or not re.fullmatch(r"[ACGT]+", alt):
                raise ValueError("Only sequence-resolved A/C/G/T alleles are supported; symbolic/SV/CNV alleles remain local")
            if ref == alt:
                raise ValueError("REF and ALT do not describe a change")
            if build not in _contexts:
                selected, config = acmg_reference.reference_record(build, record)
                _contexts[build] = dict(selected=selected, config=config, contigs={})
            context = _contexts[build]
            selected = context["selected"]
            provenance["source_file"] = selected.get("run_config", {}).get("reference_fasta") or None
            if "fasta" not in context:
                context["fasta"] = indexer.open_reference(selected, build)
            fasta = context["fasta"]
            if chromosome not in context["contigs"]:
                context["contigs"][chromosome] = _allele_contig(build, chromosome, fasta)
            contig, local_contig = context["contigs"][chromosome]
            if fasta is None:
                if len(ref) != 1 or len(alt) != 1:
                    raise ValueError("Local reference FASTA/.fai is required for sufficient indel/complex-allele normalization")
                pos, ref, alt = indexer.normalize_allele(pos, ref, alt)
                provenance["normalization"] = "SNV_NO_ALIGNMENT_REQUIRED"
                reason = "Declared assembly/contig identify the SNV; REF is UNVERIFIED without local FASTA/.fai"
            else:
                if "metadata" not in context:
                    resolved = str(fasta.path.resolve())
                    checksum = (acmg_reference.reference_checksum(fasta, build, selected, context["config"])
                                if checksum_reference else None)
                    context["metadata"] = dict(source_file=resolved,
                        digest={"algorithm": "sha256", "value": checksum} if checksum else None)
                provenance.update(context["metadata"], resolved_contig=local_contig)
                # Check the ORIGINAL REF too; trimming must not hide a mismatch.
                if fasta.sequence(local_contig, pos, len(ref)) != ref:
                    provenance["ref_status"] = "MISMATCH"
                    raise ValueError("Original REF does not match the reference FASTA")
                provenance["ref_status"] = "VERIFIED"
                pos, ref, alt = indexer.normalize_allele(pos, ref, alt, local_contig, fasta)
                qualified = dict(assembly=build, chromosome=local_contig, position=pos, reference=ref, alternate=alt)
                verification = acmg_reference.verify(qualified, record, _reference=context,
                                                     checksum_reference=checksum_reference)
                if verification is None:
                    raise ValueError("Local reference verification could not be completed")
                provenance.update(verification, normalization="REFERENCE_NORMALIZED")
                reason = "Original REF and normalized allele verified; FASTA metadata retained only as provenance"
            identity = dict(assembly=build, chromosome=contig, position=pos, reference=ref, alternate=alt)
            results.append(_result("allele_ref", original, identity,
                                   reason, reference_provenance=provenance))
        except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            provenance["error"] = str(exc)
            results.append(_result("allele_ref", original, reason=str(exc), reference_provenance=provenance))
    return results


def transcript_context_ref(transcript, assembly, release, *, namespace="Ensembl", raw=None):
    """Qualify an already acquired Ensembl bundle; never open a provider or URL.

    ``raw`` is the existing transcript artifact's raw response bundle, as used
    by TranscriptReferenceProvider/qualify. Missing versions or reference data
    remain unresolved; no latest/RefSeq substitution is permitted.
    """
    original = dict(namespace=namespace, transcript=transcript, assembly=assembly, release=release)
    try:
        if not isinstance(namespace, str) or namespace.casefold() != "ensembl":
            raise ValueError("Only the existing Ensembl namespace is supported; no RefSeq equivalence inferred")
        if not isinstance(transcript, str) or not re.fullmatch(r"ENST[0-9]+\.[1-9][0-9]*", transcript):
            raise ValueError("An exact versioned Ensembl transcript accession is required")
        build = _assembly(assembly)
        release = str(_positive_integer(release))
        if raw is None:
            raise ValueError("An already acquired Ensembl reference bundle is required for qualification")
        qualified = acmg_transcripts.qualify(raw, transcript, build, release)
        identity = dict(qualified["transcript"], assembly=build, ensembl_release=release)
        return _result("transcript_context_ref", original, identity,
                       "Accession/version, assembly and release qualified by the existing Ensembl validator",
                       artifact_digest=digest(raw))
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return _result("transcript_context_ref", original, reason=str(exc))


def association_ref(gene, disease, allelic_requirement=None, *, verified_gene_ids=(), registry=None):
    """Identify a source-anchored association, without rewriting disease anchors.

    ``verified_gene_ids`` must come from the caller's qualified reference or
    curated source; no online gene-ID verification or symbol mapping is done.
    An explicitly supplied ontology registry contributes read-only mapping
    context, never a new anchor or an interpretation-policy version to the hash.
    """
    original = dict(gene=gene, disease=disease, allelic_requirement=allelic_requirement)
    try:
        if not isinstance(gene, str) or ":" not in gene:
            raise ValueError("A namespaced stable gene identifier is required; symbols are insufficient")
        gene_id = mechanism.curie(gene, gene=True)
        if not re.fullmatch(r"(?:HGNC|NCBI_GENE):[1-9][0-9]*|ENSEMBL:ENSG[0-9]+", gene_id):
            raise ValueError("An HGNC, NCBI_GENE or Ensembl stable gene identifier is required")
        if isinstance(verified_gene_ids, str) or not verified_gene_ids:
            raise ValueError("Gene identity has not been verified by the calling source/reference")
        if gene_id not in {mechanism.curie(value, gene=True) for value in verified_gene_ids}:
            raise ValueError("Gene identifier is absent from the caller's verified gene identifiers")
        if not isinstance(disease, str) or ":" not in disease:
            raise ValueError("A namespaced disease identifier is required; names are insufficient")
        disease_id = mechanism.curie(disease)
        if not re.fullmatch(r"(?:MONDO|OMIM|ORPHA):[0-9]+", disease_id) or int(disease_id.split(":")[1]) < 1:
            raise ValueError("A MONDO, OMIM or ORPHA source disease identifier is required")
        if allelic_requirement is not None and not isinstance(allelic_requirement, str):
            raise ValueError("Allelic requirement must be a source term or None (UNKNOWN)")
        identity = dict(gene=gene_id, disease=disease_id,
                        allelic_requirement=mechanism.allelic(allelic_requirement))
        mapping = registry.pin().lookup(disease_id) if registry is not None else {"status": "NOT_REQUESTED"}
        return _result("association_ref", original, identity,
                       "Verified gene identifier and original disease anchor retained; ontology aliases are not merged",
                       disease_mapping=mapping)
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        return _result("association_ref", original, reason=str(exc))
