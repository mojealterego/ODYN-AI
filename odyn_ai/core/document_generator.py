from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Sequence

from docx import Document
from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.styles import Font


class OdynDocumentBuilder:
    """Native export of ODYN results to PDF, DOCX and XLSX."""

    def __init__(self, output_dir: str = "exports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, filename: str, extension: str) -> Path:
        safe_name = Path(filename).name
        if safe_name.lower().endswith(extension):
            safe_name = safe_name[: -len(extension)]
        return self.output_dir / f"{safe_name}{extension}"

    def _find_unicode_font(self) -> str | None:
        candidates = (
            os.getenv("ODYN_PDF_FONT"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        )
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return candidate
        return None

    def generate_pdf(self, title: str, content: str, filename: str) -> str:
        filepath = self._path(filename, ".pdf")
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.add_page()

        font = self._find_unicode_font()
        if font:
            pdf.add_font("ODYN", "", font)
            pdf.add_font("ODYN", "B", font)
            pdf.set_font("ODYN", "B", 16)
        else:
            # Fallback for environments without an installed Unicode font.
            pdf.set_font("Helvetica", "B", 16)

        pdf.cell(0, 10, text=title, new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(4)
        pdf.set_font("ODYN" if font else "Helvetica", size=11)

        for paragraph in content.split("\n"):
            if paragraph.strip():
                pdf.multi_cell(0, 7, text=paragraph)
            else:
                pdf.ln(4)

        pdf.output(str(filepath))
        return str(filepath)

    def generate_docx(self, title: str, content: str, filename: str) -> str:
        filepath = self._path(filename, ".docx")
        doc = Document()
        doc.add_heading(title, level=0)

        for paragraph in content.split("\n"):
            doc.add_paragraph(paragraph)

        doc.save(filepath)
        return str(filepath)

    def generate_xlsx(
        self,
        data: Sequence[Sequence[object]],
        filename: str,
        *,
        sheet_name: str = "ODYN",
        header: bool = True,
    ) -> str:
        filepath = self._path(filename, ".xlsx")
        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name[:31] or "ODYN"

        for row in data:
            ws.append(list(row))

        if header and ws.max_row:
            for cell in ws[1]:
                cell.font = Font(bold=True)

        ws.freeze_panes = "A2" if header and ws.max_row > 1 else None
        ws.auto_filter.ref = ws.dimensions if header and ws.max_row > 1 else None

        for column in ws.columns:
            values = [str(cell.value or "") for cell in column]
            width = min(max(len(value) for value in values) + 2, 60)
            ws.column_dimensions[column[0].column_letter].width = max(width, 10)

        wb.save(filepath)
        return str(filepath)
