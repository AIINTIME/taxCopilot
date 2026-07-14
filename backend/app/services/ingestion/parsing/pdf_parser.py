"""Extracts text content from PDF documents (statutory notifications, 26AS, etc.)."""

from pypdf import PdfReader


def parse_pdf(content: bytes) -> str:
    raise NotImplementedError(
        "TODO: PdfReader(io.BytesIO(content)) and concatenate page text"
    )
