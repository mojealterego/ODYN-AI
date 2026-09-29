import unittest
from pathlib import Path


class OdynExportUiContractTests(unittest.TestCase):
    def test_ide_contains_export_controls(self):
        ui = Path("odyn_ai/ui/index.html").read_text(encoding="utf-8")
        self.assertIn('id="export-filename"', ui)
        self.assertIn('id="export-format"', ui)
        self.assertIn('id="export-report"', ui)
        self.assertIn('data-export-format="pdf"', ui)
        self.assertIn('data-export-format="docx"', ui)
        self.assertIn('data-export-format="xlsx"', ui)

    def test_ui_uses_agent_report_export_api(self):
        js = Path("odyn_ai/ui/app.js").read_text(encoding="utf-8")
        self.assertIn("/api/agents/", js)
        self.assertIn("/reports/export", js)
        self.assertIn("export-format", js)
        self.assertIn("export-filename", js)


if __name__ == "__main__":
    unittest.main()
