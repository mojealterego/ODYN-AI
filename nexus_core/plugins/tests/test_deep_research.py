from __future__ import annotations

import asyncio
import unittest

from nexus_core.plugins.deep_research import DeepResearchEngine, ResearchResult


class FakeDDGS:
    def __init__(self, rows_by_query):
        self.rows_by_query = rows_by_query

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def text(self, query, max_results=5, **kwargs):
        for row in self.rows_by_query.get(query, [])[:max_results]:
            yield row


class DeepResearchTests(unittest.TestCase):
    def test_async_search_normalizes_and_deduplicates_urls(self):
        def factory():
            return FakeDDGS({
                "odyn": [
                    {"title": "A", "href": "https://example.com/a", "body": "first"},
                    {"title": "A duplicate", "href": "https://example.com/a", "body": "duplicate"},
                    {"title": "B", "href": "https://example.com/b", "body": "second"},
                ]
            })

        engine = DeepResearchEngine(ddgs_factory=factory)
        results = asyncio.run(engine.aget_results(" odyn ", max_results=5))

        self.assertEqual([r.url for r in results], ["https://example.com/a", "https://example.com/b"])
        self.assertIsInstance(results[0], ResearchResult)

    def test_pdf_query_is_scoped(self):
        seen = []

        def factory():
            class Capture(FakeDDGS):
                async def text(self, query, max_results=5, **kwargs):
                    seen.append(query)
                    for row in super().text(query, max_results=max_results, **kwargs):
                        yield row
            return Capture({})

        engine = DeepResearchEngine(ddgs_factory=factory)
        asyncio.run(engine.fetch_pdf_documents("quantum computing", max_results=3))
        self.assertEqual(seen, ["quantum computing filetype:pdf"])

    def test_multi_hop_expands_queries_from_search_results(self):
        async def factory():
            return FakeDDGS({
                "root": [{"title": "Root", "href": "https://a", "body": "new clue: llama.cpp"}],
                "new clue: llama.cpp": [{"title": "Hop", "href": "https://b", "body": "verified detail"}],
            })

        engine = DeepResearchEngine(ddgs_factory=factory)
        report = asyncio.run(engine.execute_rag_pipeline(["root"], max_hops=2, max_results=5))

        self.assertEqual(report.hops, 2)
        self.assertEqual({r.url for r in report.sources}, {"https://a", "https://b"})
        self.assertIn("verified detail", report.context)

    def test_empty_query_is_rejected(self):
        engine = DeepResearchEngine(ddgs_factory=lambda: FakeDDGS({}))
        with self.assertRaises(ValueError):
            asyncio.run(engine.aget_results("   "))


if __name__ == "__main__":
    unittest.main()
