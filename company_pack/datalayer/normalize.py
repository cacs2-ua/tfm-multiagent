from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
_MULTI_SPACE = re.compile(r"[ \t]+")
_BULLET = re.compile(r"^\s*(?:[-*•]|(\d+)[\.\)])\s+")
_HEADING_NUM = re.compile(r"^\s*(\d+(?:\.\d+)*)\b")
_HEADING_WORD = re.compile(r"^\s*(chapter|section)\b", re.IGNORECASE)

# Hyphenation at line breaks: infor-\nmation -> information
_DEHYPHEN = re.compile(r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ])-\n([A-Za-zÁÉÍÓÚÜÑáéíóúüñ])")


@dataclass(frozen=True)
class HeaderFooterModel:
    headers: Set[str]
    footers: Set[str]


def _clean_line(line: str) -> str:
    line = _CONTROL_CHARS.sub("", line)
    line = _MULTI_SPACE.sub(" ", line).strip()
    return line


def detect_common_headers_footers(pages_raw: List[str], *, min_ratio: float = 0.6) -> HeaderFooterModel:
    """
    Deterministic heuristic:
    - Take first non-empty line and last non-empty line of each page
    - Count frequencies
    - Mark as header/footer if appears on >= min_ratio of pages (and short enough)
    """
    first_lines: List[str] = []
    last_lines: List[str] = []

    for raw in pages_raw:
        lines = [_clean_line(x) for x in (raw or "").splitlines()]
        lines = [x for x in lines if x]
        if not lines:
            continue
        first_lines.append(lines[0])
        last_lines.append(lines[-1])

    def common(lines: List[str]) -> Set[str]:
        if not lines:
            return set()
        n = len(lines)
        freq: Dict[str, int] = {}
        for x in lines:
            if 0 < len(x) <= 120:
                freq[x] = freq.get(x, 0) + 1
        out = {k for k, c in freq.items() if (c / max(1, n)) >= min_ratio}
        return set(sorted(out))

    return HeaderFooterModel(headers=common(first_lines), footers=common(last_lines))


def normalize_page_text(raw_text: str, hf: HeaderFooterModel) -> str:
    """
    Deterministic normalization:
    - Unicode NFKC
    - Normalize newlines
    - Remove control chars
    - Remove frequent header/footer lines
    - Dehyphenation at line breaks (strict heuristic)
    - Collapse whitespace but preserve paragraph breaks
    - Join wrapped lines inside paragraphs, except bullet/list lines
    """
    t = raw_text or ""
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = unicodedata.normalize("NFKC", t)
    t = _CONTROL_CHARS.sub("", t)

    # Remove frequent header/footer: only if exact match on cleaned first/last non-empty lines
    lines0 = t.splitlines()
    cleaned = [_clean_line(x) for x in lines0]
    nonempty_idx = [i for i, x in enumerate(cleaned) if x]

    if nonempty_idx:
        i0 = nonempty_idx[0]
        i1 = nonempty_idx[-1]
        if cleaned[i0] in hf.headers:
            lines0[i0] = ""
        if cleaned[i1] in hf.footers:
            lines0[i1] = ""

    t = "\n".join(lines0)

    # Dehyphenate: infor-\nmation -> information
    t = _DEHYPHEN.sub(r"\1\2", t)

    # Rebuild paragraphs
    lines = [ _clean_line(x) for x in t.splitlines() ]
    # Keep blank lines as paragraph boundaries
    paras: List[str] = []
    buf: List[str] = []

    def flush_buf() -> None:
        nonlocal buf
        if not buf:
            return
        # If this looks like a list block (many bullet lines), preserve line breaks
        is_list_block = all(_BULLET.match(x) for x in buf if x)
        if is_list_block:
            paras.append("\n".join(buf).strip())
        else:
            paras.append(" ".join(buf).strip())
        buf = []

    for ln in lines:
        if not ln:
            flush_buf()
        else:
            buf.append(ln)
    flush_buf()

    # Re-join paragraphs with a single blank line for stability
    out = "\n\n".join([p for p in paras if p]).strip()
    return out


def is_heading(block: str) -> bool:
    b = block.strip()
    if not b:
        return False
    if len(b) > 120:
        return False
    # strong cues
    if _HEADING_NUM.match(b):
        return True
    if _HEADING_WORD.match(b):
        return True
    # all caps short line
    if b.isupper() and len(b) >= 4:
        return True
    return False


def heading_level(block: str) -> int:
    """
    Infer hierarchy from numbering:
      "1" -> 1, "1.2" -> 2, "1.2.3" -> 3, else 1
    """
    m = _HEADING_NUM.match(block.strip())
    if not m:
        return 1
    num = m.group(1)
    return num.count(".") + 1
