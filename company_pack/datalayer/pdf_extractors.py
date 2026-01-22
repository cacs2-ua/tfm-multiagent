from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ExtractorInfo:
    name: str
    version: str


class PDFExtractionError(Exception):
    pass


class PyPDFExtractor:
    """
    Digital text extractor (born-digital PDFs).
    Uses pypdf's page.extract_text().
    """

    def __init__(self) -> None:
        try:
            import pypdf  # type: ignore
        except Exception as e:
            raise PDFExtractionError(
                "pypdf is required for PDF extraction. Install: pip install pypdf"
            ) from e
        self._pypdf = pypdf

    def info(self) -> ExtractorInfo:
        try:
            v = getattr(self._pypdf, "__version__", "unknown")
        except Exception:
            v = "unknown"
        return ExtractorInfo(name="pypdf", version=str(v))

    def extract_pages(self, pdf_path: Path) -> List[str]:
        try:
            reader = self._pypdf.PdfReader(str(pdf_path))
        except Exception as e:
            raise PDFExtractionError(f"Failed to open PDF: {pdf_path.name}: {e}") from e

        pages: List[str] = []
        for i, page in enumerate(reader.pages):
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            pages.append(txt)
        return pages

    def get_pdf_title(self, pdf_path: Path) -> Optional[str]:
        # Best-effort metadata read
        try:
            reader = self._pypdf.PdfReader(str(pdf_path))
            md = getattr(reader, "metadata", None)
            if md and getattr(md, "title", None):
                t = str(md.title).strip()
                return t if t else None
        except Exception:
            return None
        return None


def default_extractor_chain() -> List[PyPDFExtractor]:
    # Later you can add pdfplumber/unstructured/OCR plugins here
    return [PyPDFExtractor()]
