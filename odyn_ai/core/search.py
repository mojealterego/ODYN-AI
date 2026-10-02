from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str

class OdynInternetAccess:
    async def search_web(self, query: str, max_results: int = 5) -> list[SearchResult]:
        query = query.strip()
        if not query:
            return []
        return await asyncio.to_thread(self._search_sync, query, max(1, min(max_results, 20)))

    @staticmethod
    def _search_sync(query: str, max_results: int) -> list[SearchResult]:
        try:
            from ddgs import DDGS
            rows: list[dict[str, Any]] = DDGS().text(query, region="pl-pl", safesearch="moderate", max_results=max_results)
            return [SearchResult(str(r.get("title") or "Bez tytułu"), str(r.get("href") or r.get("url") or ""), str(r.get("body") or r.get("snippet") or "")) for r in rows if r.get("href") or r.get("url")]
        except Exception as exc:
            raise RuntimeError(f"Wyszukiwanie Internetu nie powiodło się: {exc}") from exc

    @staticmethod
    def format_context(results: list[SearchResult]) -> str:
        if not results:
            return "Brak wyników wyszukiwania."
        return "\n".join(
            [f"Źródło {i}: {r.title}\nURL: {r.url}\nOpis: {r.snippet}" for i, r in enumerate(results, 1)]
        )
