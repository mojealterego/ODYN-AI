import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from odyn_ai.api.document_api_models import DocumentExportRequest, SpreadsheetExportRequest, ReportExportRequest
from odyn_ai.api import server


class DocumentExportApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_pdf_endpoint_returns_downloadable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(server, "documents", server.OdynDocumentBuilder(tmp)):
                response = await server.export_pdf(
                    DocumentExportRequest(
                        title="Raport ODYN",
                        content="Zażółć gęślą jaźń.",
                        filename="../raport",
                    )
                )
                self.assertEqual(response.media_type, "application/pdf")
                self.assertEqual(Path(response.path).name, "raport.pdf")
                self.assertTrue(Path(response.path).is_file())

    async def test_docx_endpoint_returns_downloadable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(server, "documents", server.OdynDocumentBuilder(tmp)):
                response = await server.export_docx(
                    DocumentExportRequest(
                        title="Raport ODYN",
                        content="Treść dokumentu.",
                        filename="raport",
                    )
                )
                self.assertEqual(
                    response.media_type,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
                self.assertTrue(Path(response.path).is_file())

    async def test_xlsx_endpoint_returns_downloadable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(server, "documents", server.OdynDocumentBuilder(tmp)):
                response = await server.export_xlsx(
                    SpreadsheetExportRequest(
                        data=[["Nazwa", "Wartość"], ["ODYN", 42]],
                        filename="dane",
                        sheet_name="Raport",
                    )
                )
                self.assertEqual(
                    response.media_type,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                self.assertTrue(Path(response.path).is_file())

    async def test_report_endpoint_exports_selected_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(server, "documents", server.OdynDocumentBuilder(tmp)):
                response = await server.export_report(
                    ReportExportRequest(
                        format="docx",
                        title="Raport agenta ODYN",
                        filename="raport-agenta",
                        content="# Wnioski\nRaport wygenerowany przez agenta.",
                    )
                )
                self.assertEqual(
                    response.media_type,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
                self.assertEqual(Path(response.path).name, "raport-agenta.docx")

    async def test_http_export_returns_downloadable_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(server, "documents", server.OdynDocumentBuilder(tmp)):
                transport = httpx.ASGITransport(app=server.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://odyn.test") as client:
                    response = await client.post(
                        "/api/reports/export",
                        json={
                            "format": "pdf",
                            "title": "Raport HTTP",
                            "content": "Treść raportu.",
                            "filename": "raport-http",
                        },
                    )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["content-type"], "application/pdf")
                self.assertIn("attachment", response.headers["content-disposition"])
                self.assertGreater(len(response.content), 100)


if __name__ == "__main__":
    unittest.main()
