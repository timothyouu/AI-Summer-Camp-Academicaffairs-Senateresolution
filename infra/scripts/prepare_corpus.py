"""Stage the supplied corpus under Bedrock KB prefixes and optionally upload it.

The source tree is never modified. Every source has an explicit destination and
metadata record so adding a new file fails loudly until its classification is
reviewed.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = REPO_ROOT / "data" / "corpus"
MANAGED_CORPUS_PREFIXES = {"handbook", "cba", "resolutions", "synthetic"}


@dataclass(frozen=True)
class CorpusSource:
    relative_path: str
    prefix: str
    doc_type: str
    topic: str


CORPUS_SOURCES = (
    CorpusSource("CSUB University_Handbook_2025.pdf", "handbook", "university_handbook", "campus policy"),
    CorpusSource("Unit 3 CBA 2022-2026.pdf", "cba", "collective_bargaining_agreement", "cba/labor"),
    CorpusSource("A Guide to CalPERS Employment After Retirement.pdf", "cba", "retirement_reference", "cba/labor"),
    CorpusSource("csub-ferp-faq-extract.md", "cba", "campus_guidance", "cba/labor"),
    CorpusSource("synthetic-resolution-ai-policy.md", "synthetic", "synthetic_resolution", "senate procedures"),
    CorpusSource("synthetic-procedures-schools-departments.md", "synthetic", "synthetic_procedure", "senate procedures"),
    CorpusSource("synthetic-handbook-gecco.md", "synthetic", "synthetic_handbook", "committees"),
    CorpusSource("synthetic-appendix-ati-accessibility.md", "synthetic", "synthetic_appendix", "accessibility"),
    CorpusSource("synthetic-handbook-service-credit.md", "synthetic", "synthetic_handbook", "tenure & promotion"),
    CorpusSource("rtp/RES252610 - The Unit RTP and PTR Committee Composition Process and Related Handbook Changes.pdf", "resolutions", "senate_resolution", "tenure & promotion"),
    CorpusSource("rtp/RES252645 - Periodic Evaluation of Temporary Faculty - Handbook Change.pdf", "resolutions", "senate_resolution", "tenure & promotion"),
    CorpusSource("rtp/RES252644 - Guidance on WPAF Contents and Timelines for Review - Handbook Change.pdf", "resolutions", "senate_resolution", "tenure & promotion"),
    CorpusSource("rtp/Guidance - Formation of Unit Committees (3.14.25).pdf", "resolutions", "campus_guidance", "committees"),
    CorpusSource("rtp/RES252632 - Required Unit RTP Criteria Elements and Guidance on Unit RTP Criteria Revision - Handbook Changes.pdf", "resolutions", "senate_resolution", "tenure & promotion"),
    CorpusSource("rtp/Resource Article - Good Practice in Tenure Evaluation (ACE, AAUP, UE; 2000).pdf", "resolutions", "reference_article", "tenure & promotion"),
    CorpusSource("rtp/Guidance - Eligibility for Unit Review Committee Service (9.23.25).pdf", "resolutions", "campus_guidance", "tenure & promotion"),
)


def _metadata(source: CorpusSource, filename: str) -> dict[str, object]:
    values = {
        "source": Path(filename).stem,
        "section": "Document",
        "doc_type": source.doc_type,
        "topic": source.topic,
    }
    return {
        "metadataAttributes": {
            key: {
                "value": {"type": "STRING", "stringValue": value},
                "includeForEmbedding": key in {"source", "doc_type", "topic"},
            }
            for key, value in values.items()
        }
    }


def validate_manifest(source_root: Path) -> None:
    discovered = {
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*")
        if path.is_file()
    }
    declared = {source.relative_path for source in CORPUS_SOURCES}
    missing = sorted(declared - discovered)
    unclassified = sorted(discovered - declared)
    invalid_prefixes = sorted({source.prefix for source in CORPUS_SOURCES} - MANAGED_CORPUS_PREFIXES)
    destinations = [(source.prefix, Path(source.relative_path).name) for source in CORPUS_SOURCES]
    duplicate_destinations = sorted({item for item in destinations if destinations.count(item) > 1})
    if missing or unclassified or invalid_prefixes or duplicate_destinations:
        details = []
        if missing:
            details.append(f"missing declared files: {missing}")
        if unclassified:
            details.append(f"unclassified files: {unclassified}")
        if invalid_prefixes:
            details.append(f"prefixes outside the managed KB set: {invalid_prefixes}")
        if duplicate_destinations:
            details.append(f"duplicate staged destinations: {duplicate_destinations}")
        raise ValueError("Corpus manifest mismatch; " + "; ".join(details))


def build_staging_tree(source_root: Path, staging_root: Path) -> None:
    validate_manifest(source_root)
    for source in CORPUS_SOURCES:
        source_path = source_root / source.relative_path
        destination = staging_root / source.prefix / source_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        metadata_path = destination.with_name(destination.name + ".metadata.json")
        metadata_path.write_text(
            json.dumps(_metadata(source, destination.name), indent=2) + "\n",
            encoding="utf-8",
        )


def upload_corpus(bucket: str, source_root: Path) -> None:
    destination = bucket if bucket.startswith("s3://") else f"s3://{bucket}"
    with tempfile.TemporaryDirectory(prefix="policy-intelligence-corpus-") as temporary:
        staging_root = Path(temporary)
        build_staging_tree(source_root, staging_root)
        subprocess.run(
            ["aws", "s3", "sync", str(staging_root), destination.rstrip("/") + "/"],
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", help="CorpusBucketName stack output; omit to validate and preview only.")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    validate_manifest(source_root)
    if args.bucket:
        upload_corpus(args.bucket, source_root)
        print(f"Uploaded {len(CORPUS_SOURCES)} sources plus metadata sidecars to {args.bucket}.")
        return
    for source in CORPUS_SOURCES:
        print(f"{source.relative_path} -> {source.prefix}/{Path(source.relative_path).name}")


if __name__ == "__main__":
    main()
