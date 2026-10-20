"""CSV / XLSX export. Cells that start with = + - @ are prefixed with ' to prevent spreadsheet formula injection."""
from __future__ import annotations

import csv
import io

COLUMNS = [("att_date", "Date"), ("att_time", "Time"), ("person_id", "ID"), ("person_name", "Name"),
           ("department", "Department/Class"), ("status", "Status"), ("source", "Source"),
           ("confidence", "Match similarity"), ("note", "Note"), ("marked_by", "Marked by")]


def safe_cell(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def _values(row: dict) -> list:
    out = []
    for key, _ in COLUMNS:
        v = row.get(key)
        out.append("" if v is None else (round(v, 3) if isinstance(v, float) else safe_cell(v)))
    return out


def to_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([h for _, h in COLUMNS])
    for r in rows:
        w.writerow(_values(r))
    return ("\ufeff" + buf.getvalue()).encode("utf-8")          # BOM so Excel opens UTF-8 names correctly


def to_xlsx(rows: list[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.append([h for _, h in COLUMNS])
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append(_values(r))
    for i, (_, h) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[chr(64 + i)].width = max(12, len(h) + 4)
    ws.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
