from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .normalize import is_heading, heading_level


@dataclass(frozen=True)
class Segment:
    doc_id: str
    page_number: int  # 1-based
    segment_index: int  # within page
    segment_type: str  # heading|paragraph|list|other
    section_path: str  # "A > B > C" (can be empty)
    text: str


def _split_blocks(page_text: str) -> List[str]:
    # Blocks split by blank lines; stable behavior
    parts = [p.strip() for p in (page_text or "").split("\n\n")]
    return [p for p in parts if p]


def _is_list_block(block: str) -> bool:
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    # bullet-like start for most lines
    def bulletish(s: str) -> bool:
        return s.startswith(("-", "*", "•")) or (len(s) > 2 and s[0].isdigit() and s[1] in [".", ")"])
    hits = sum(1 for ln in lines if bulletish(ln))
    return hits >= max(2, int(0.6 * len(lines)))


def segment_document_pages(doc_id: str, pages_norm: List[str]) -> List[Segment]:
    """
    Build segments across pages while tracking a simple heading hierarchy (section_path).
    """
    segs: List[Segment] = []
    heading_stack: List[str] = []

    for p_idx, page in enumerate(pages_norm, start=1):
        blocks = _split_blocks(page)
        local_idx = 0
        for b in blocks:
            local_idx += 1
            b_clean = b.strip()
            stype = "paragraph"

            if is_heading(b_clean):
                stype = "heading"
                lvl = heading_level(b_clean)
                # adjust stack depth deterministically
                if lvl <= 1:
                    heading_stack = [b_clean]
                else:
                    heading_stack = heading_stack[: max(0, lvl - 1)]
                    heading_stack.append(b_clean)
            elif _is_list_block(b_clean):
                stype = "list"
            else:
                stype = "paragraph"

            section_path = " > ".join(heading_stack) if heading_stack else ""
            segs.append(
                Segment(
                    doc_id=doc_id,
                    page_number=p_idx,
                    segment_index=local_idx,
                    segment_type=stype,
                    section_path=section_path,
                    text=b_clean,
                )
            )
    return segs
