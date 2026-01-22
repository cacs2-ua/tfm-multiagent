from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from .segment import Segment
from .utils import sha256_text, stable_id


@dataclass(frozen=True)
class TextUnit:
    company_id: str
    doc_id: str
    doc_title: str
    chunk_id: str
    chunk_index: int
    page_start: int
    page_end: int
    section_path: str
    segment_types_included: List[str]
    content_type: str
    language: str
    text: str
    text_hash: str
    source_citation: str
    quality_score: float
    warnings: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "company_id": self.company_id,
            "doc_id": self.doc_id,
            "doc_title": self.doc_title,
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "section_path": self.section_path,
            "segment_types_included": self.segment_types_included,
            "content_type": self.content_type,
            "language": self.language,
            "text": self.text,
            "text_hash": self.text_hash,
            "source_citation": self.source_citation,
            "quality_score": self.quality_score,
            "warnings": self.warnings,
        }


def chunk_segments(
    *,
    company_id: str,
    doc_id: str,
    doc_title: str,
    language: str,
    topic: str,
    segments: List[Segment],
    chunk_size: int,
    chunk_overlap: int,
) -> List[TextUnit]:
    """
    Deterministic structure-aware chunking:
    - Prefer boundaries at headings and paragraph blocks
    - Respect chunk_size (characters) and chunk_overlap (characters, approximated via last segments)
    """
    units: List[TextUnit] = []
    buf: List[Segment] = []
    buf_len = 0

    def buf_types() -> List[str]:
        s: Set[str] = set(x.segment_type for x in buf)
        return sorted(s)

    def buf_section_path() -> str:
        # Most recent non-empty section_path in buffer
        for x in reversed(buf):
            if x.section_path:
                return x.section_path
        return ""

    def buf_pages() -> Tuple[int, int]:
        ps = min(x.page_number for x in buf) if buf else 1
        pe = max(x.page_number for x in buf) if buf else 1
        return ps, pe

    def estimate_quality(text: str) -> float:
        # simple deterministic proxy
        n = len(text.strip())
        if n <= 0:
            return 0.0
        if n < 200:
            return 0.4
        if n < 800:
            return 0.7
        return 0.9

    def flush(chunk_index: int) -> int:
        nonlocal buf, buf_len
        if not buf:
            return chunk_index

        text = "\n\n".join([x.text for x in buf]).strip()
        th = sha256_text(text)
        sec = buf_section_path()
        ps, pe = buf_pages()

        cid = stable_id(
            "chunk",
            [doc_id, str(chunk_index), sec, th[:12], f"{ps}-{pe}"],
            n=16,
        )

        citation = f"{doc_title}, p.{ps}" if ps == pe else f"{doc_title}, p.{ps}-{pe}"
        unit = TextUnit(
            company_id=company_id,
            doc_id=doc_id,
            doc_title=doc_title,
            chunk_id=cid,
            chunk_index=chunk_index,
            page_start=ps,
            page_end=pe,
            section_path=sec,
            segment_types_included=buf_types(),
            content_type=topic or "generic",
            language=language,
            text=text,
            text_hash=th,
            source_citation=citation,
            quality_score=estimate_quality(text),
            warnings=[],
        )
        units.append(unit)
        chunk_index += 1

        # Overlap by keeping last segments whose combined char length >= chunk_overlap
        if chunk_overlap > 0:
            keep: List[Segment] = []
            nchar = 0
            for seg in reversed(buf):
                keep.append(seg)
                nchar += len(seg.text) + 2
                if nchar >= chunk_overlap:
                    break
            buf = list(reversed(keep))
            buf_len = sum(len(x.text) + 2 for x in buf)
        else:
            buf = []
            buf_len = 0

        return chunk_index

    chunk_index = 0

    for seg in segments:
        seg_text = seg.text.strip()
        if not seg_text:
            continue

        # Force a boundary at heading changes: flush previous chunk, start new buffer with heading
        if seg.segment_type == "heading":
            if buf:
                chunk_index = flush(chunk_index)
            buf = [seg]
            buf_len = len(seg_text) + 2
            continue

        add_len = len(seg_text) + 2
        if buf and (buf_len + add_len) > chunk_size:
            chunk_index = flush(chunk_index)

        buf.append(seg)
        buf_len += add_len

    if buf:
        flush(chunk_index)

    return units
