"""Extracts tabular content from XLSX documents (e.g. CII tables, schedules)."""

from openpyxl import load_workbook


def parse_xlsx(content: bytes) -> list[dict]:
    raise NotImplementedError(
        "TODO: load_workbook(io.BytesIO(content)) and return rows as dicts"
    )
