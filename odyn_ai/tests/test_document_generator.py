import tempfile
import unittest
from pathlib import Path

from odyn_ai.core.document_generator import OdynDocumentBuilder


class DocumentGeneratorTests(unittest.TestCase):
    def test_generates_pdf_with_polish_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = OdynDocumentBuilder(tmp).generate_pdf(
                "Raport ODYN",
                "Zażółć gęślą jaźń. Pamięć epizodyczna.",
                "raport",
            )
            output = Path(path)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 100)

    def test_generates_docx_with_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = OdynDocumentBuilder(tmp).generate_docx(
                "Raport ODYN",
                "Pierwszy akapit.\n\nDrugi akapit.",
                "raport",
            )
            from docx import Document
            doc = Document(path)
            self.assertEqual(doc.paragraphs[0].text, "Raport ODYN")
            self.assertIn("Pierwszy akapit.", [p.text for p in doc.paragraphs])
            self.assertIn("Drugi akapit.", [p.text for p in doc.paragraphs])

    def test_generates_formatted_xlsx(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = OdynDocumentBuilder(tmp).generate_xlsx(
                [["Nazwa", "Wartość"], ["ODYN", 42]],
                "dane",
            )
            from openpyxl import load_workbook
            wb = load_workbook(path)
            ws = wb["ODYN"]
            self.assertEqual(ws["A1"].value, "Nazwa")
            self.assertTrue(ws["A1"].font.bold)
            self.assertEqual(ws["B2"].value, 42)
            self.assertEqual(ws.freeze_panes, "A2")


    def test_rejects_path_traversal_and_normalizes_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = OdynDocumentBuilder(tmp)
            path = builder.generate_docx("Tytuł", "Treść", "../raport.docx")
            self.assertEqual(Path(path).parent, Path(tmp))
            self.assertEqual(Path(path).name, "raport.docx")

    def test_xlsx_escapes_formula_like_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = OdynDocumentBuilder(tmp).generate_xlsx(
                [["Nazwa"], ["=2+2"], ["@cmd"]],
                "bezpieczne",
            )
            from openpyxl import load_workbook
            wb = load_workbook(path, data_only=False)
            ws = wb["ODYN"]
            self.assertEqual(ws["A2"].value, "'=2+2")
            self.assertEqual(ws["A3"].value, "'@cmd")

    def test_xlsx_uses_requested_sheet_name_and_can_disable_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = OdynDocumentBuilder(tmp).generate_xlsx(
                [["=1+1"], ["wartość"]],
                "dane",
                sheet_name="Raport ODYN",
                header=False,
            )
            from openpyxl import load_workbook
            wb = load_workbook(path, data_only=False)
            ws = wb["Raport ODYN"]
            self.assertEqual(ws["A1"].value, "'=1+1")
            self.assertIsNone(ws.freeze_panes)

    def test_pdf_has_odyn_footer_and_page_numbering(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = "\n".join(["Raport testowy"] * 90)
            path = OdynDocumentBuilder(tmp).generate_pdf("Raport ODYN", content, "raport")
            raw = Path(path).read_bytes()
            self.assertIn(b"ODYN AI", raw)
            self.assertIn(b"1 /", raw)

    def test_docx_supports_h1_h2_h3_hierarchy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = OdynDocumentBuilder(tmp).generate_docx(
                "Raport ODYN",
                "# Rozdział\nTreść\n## Sekcja\nOpis\n### Podsekcja\nSzczegóły",
                "hierarchia",
            )
            from docx import Document
            doc = Document(path)
            headings = [(p.style.name, p.text) for p in doc.paragraphs if p.style.name.startswith("Heading")]
            self.assertIn(("Heading 1", "Rozdział"), headings)
            self.assertIn(("Heading 2", "Sekcja"), headings)
            self.assertIn(("Heading 3", "Podsekcja"), headings)

    def test_xlsx_creates_styled_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = OdynDocumentBuilder(tmp).generate_xlsx(
                [["Nazwa", "Wartość"], ["ODYN", 42]], "tabela"
            )
            from openpyxl import load_workbook
            wb = load_workbook(path)
            ws = wb["ODYN"]
            self.assertEqual(len(ws.tables), 1)
            self.assertEqual(ws.tables["ODYNTable"].ref, "A1:B2")
            self.assertTrue(ws["A1"].fill.fgColor.rgb or ws["A1"].fill.fgColor.indexed)


if __name__ == "__main__":
    unittest.main()
