"""Extracts text from PDFs and splits into overlapping fixed-size chunks."""

import io

from pypdf import PdfReader


def parse_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def chunk_document(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Fixed-size character chunker with overlap to avoid splitting mid-rule."""
    if not text.strip():
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks
