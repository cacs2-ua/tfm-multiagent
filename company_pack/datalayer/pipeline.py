from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from importlib import metadata as importlib_metadata

from ..models import CompanyPack
from .pdf_extractors import PDFExtractionError, default_extractor_chain
from .normalize import detect_common_headers_footers, normalize_page_text
from .segment import segment_document_pages
from .chunk import chunk_segments
from .utils import sha256_file, stable_id, write_json_stable, write_jsonl_stable, safe_rmtree


PIPELINE_VERSION = "0.1.0"


@dataclass(frozen=True)
class DocumentRecord:
    doc_id: str
    source_path: str  # relative path inside pack
    file_hash: str
    file_size: int
    doc_title: str
    page_count: int
    extractor_name: str
    extractor_version: str
    topic: str
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_path": self.source_path,
            "file_hash": self.file_hash,
            "file_size": self.file_size,
            "doc_title": self.doc_title,
            "page_count": self.page_count,
            "extractor": {"name": self.extractor_name, "version": self.extractor_version},
            "topic": self.topic,
            "warnings": self.warnings,
        }


def _topic_from_relpath(rel: Path) -> str:
    # docs/<topic>/file.pdf => topic
    parts = rel.as_posix().split("/")
    if len(parts) >= 2 and parts[0] == "docs":
        # topic is immediate folder under docs (if any)
        if len(parts) >= 3:
            return parts[1].strip() or "generic"
    return "generic"


def ingest_company_pack(
    pack: CompanyPack,
    *,
    out_dir: Path,
    overwrite: bool = True,
) -> Dict[str, Path]:
    """
    Full deterministic ingestion:
      PDFs -> per-page raw text -> normalized pages -> segments -> TextUnits (jsonl)
      + manifest + ingestion_report

    Returns important output paths.
    """
    out_dir = Path(out_dir).expanduser().resolve()

    if out_dir.exists():
        if not overwrite:
            raise ValueError(f"out_dir already exists: {out_dir}")
        safe_rmtree(out_dir)

    out_dir.mkdir(parents=True, exist_ok=True)

    extractor_chain = default_extractor_chain()

    pdfs = pack.list_pdfs()
    # deterministic: sorted already by list_pdfs()
    docs: List[DocumentRecord] = []
    all_units: List[Dict[str, Any]] = []

    total_pages = 0
    warnings: List[str] = []
    errors: List[str] = []

    for pdf_path in pdfs:
        try:
            rel = pdf_path.relative_to(pack.root)
        except Exception:
            rel = Path("docs") / pdf_path.name

        file_hash = sha256_file(pdf_path)
        file_size = int(pdf_path.stat().st_size)

        doc_id = stable_id(
            "doc",
            [pack.manifest.company_id, rel.as_posix(), file_hash],
            n=16,
        )

        topic = _topic_from_relpath(rel)
        doc_title = pdf_path.stem

        raw_pages: Optional[List[str]] = None
        used_extractor = None
        used_version = None

        # Fallback chain (currently only pypdf, but structured for extension)
        for ex in extractor_chain:
            try:
                info = ex.info()
                raw_pages = ex.extract_pages(pdf_path)
                t = ex.get_pdf_title(pdf_path)
                if t:
                    doc_title = t
                used_extractor = info.name
                used_version = info.version
                break
            except Exception as e:
                warnings.append(f"{rel.as_posix()}: extractor_failed: {e}")
                continue

        if raw_pages is None or used_extractor is None or used_version is None:
            errors.append(f"{rel.as_posix()}: all extractors failed")
            continue

        page_count = len(raw_pages)
        total_pages += page_count

        # Header/footer model per document
        hf = detect_common_headers_footers(raw_pages, min_ratio=0.6)

        # Write per-page raw + normalized text
        raw_dir = out_dir / "docs" / doc_id / "pages_raw"
        norm_dir = out_dir / "docs" / doc_id / "pages_normalized"
        raw_dir.mkdir(parents=True, exist_ok=True)
        norm_dir.mkdir(parents=True, exist_ok=True)

        pages_norm: List[str] = []
        for i, raw in enumerate(raw_pages, start=1):
            raw_file = raw_dir / f"page_{i:04d}.txt"
            norm_file = norm_dir / f"page_{i:04d}.txt"
            raw_file.write_text((raw or "") + "\n", encoding="utf-8", newline="\n")

            norm = normalize_page_text(raw or "", hf)
            pages_norm.append(norm)
            norm_file.write_text(norm + "\n", encoding="utf-8", newline="\n")

        # Segmentation
        segments = segment_document_pages(doc_id, pages_norm)

        # Chunking uses retrieval config (section 7 ties to retrieval)
        units = chunk_segments(
            company_id=pack.manifest.company_id,
            doc_id=doc_id,
            doc_title=doc_title,
            language=pack.metadata.primary_language,
            topic=topic,
            segments=segments,
            chunk_size=int(pack.retrieval.chunk_size),
            chunk_overlap=int(pack.retrieval.chunk_overlap),
        )

        docs.append(
            DocumentRecord(
                doc_id=doc_id,
                source_path=rel.as_posix(),
                file_hash=file_hash,
                file_size=file_size,
                doc_title=doc_title,
                page_count=page_count,
                extractor_name=used_extractor,
                extractor_version=used_version,
                topic=topic,
                warnings=[],
            )
        )

        for u in units:
            all_units.append(u.to_dict())

    # Deterministic output ordering:
    # - docs already in sorted pdf order
    # - chunks produced in order
    manifest = {
        "schema_version": 1,
        "company_id": pack.manifest.company_id,
        "pipeline_version": PIPELINE_VERSION,
        "platform_version": pack.manifest.compatibility.min_platform_version,
        "config_snapshot": {
            "retrieval": {
                "chunk_size": pack.retrieval.chunk_size,
                "chunk_overlap": pack.retrieval.chunk_overlap,
                "top_k": pack.retrieval.top_k,
                "filters": pack.retrieval.filters,
                "schema_version": pack.retrieval.schema_version,
            },
            "metadata": {
                "sector": pack.metadata.sector,
                "primary_language": pack.metadata.primary_language,
            },
        },
        "dependencies": {
            "pypdf": _safe_pkg_version("pypdf"),
        },
        "documents": [d.to_dict() for d in docs],
    }

    # NOTE: manifest is stable (no timestamps) for reproducibility
    write_json_stable(out_dir / "manifest.json", manifest)
    write_jsonl_stable(out_dir / "text_units.jsonl", all_units)

    report = {
        "company_id": pack.manifest.company_id,
        "pipeline_version": PIPELINE_VERSION,
        "docs_found": len(pdfs),
        "docs_processed": len(docs),
        "pages_processed": total_pages,
        "text_units_created": len(all_units),
        "warnings": sorted(warnings),
        "errors": sorted(errors),
    }
    write_json_stable(out_dir / "ingestion_report.json", report)

    return {
        "out_dir": out_dir,
        "manifest": out_dir / "manifest.json",
        "text_units": out_dir / "text_units.jsonl",
        "report": out_dir / "ingestion_report.json",
    }


def _safe_pkg_version(name: str) -> str:
    try:
        return str(importlib_metadata.version(name))
    except Exception:
        return "unknown"
