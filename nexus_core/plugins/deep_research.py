from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass(frozen=True)
class ResearchResult:
    title: str
    url: str
    body: str
    query: str
    hop: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ResearchReport:
    query: str
    hops: int
    sources: tuple[ResearchResult, ...]
    context: str

class DeepResearchEngine:
    """Bounded asynchronous multi-hop web research and RAG acquisition."""

    def __init__(self, *, ddgs_factory: Callable[[], Any] | None = None,
                 region: str = "pl-pl", safesearch: str = "moderate") -> None:
        self._ddgs_factory = ddgs_factory
        self.region = region
        self.safesearch = safesearch

    def _factory(self) -> Callable[[], Any]:
        if self._ddgs_factory is not None:
            return self._ddgs_factory
        try:
            from ddgs import DDGS
        except ImportError as exc:
            raise RuntimeError("DeepResearchEngine wymaga opcjonalnej zależności 'ddgs'.") from exc
        return DDGS

    async def aget_results(self, query: str, max_results: int = 5, *, hop: int = 0) -> list[ResearchResult]:
        query = query.strip()
        if not query:
            raise ValueError("query cannot be empty")
        max_results = max(1, min(max_results, 50))

        def search_sync() -> list[ResearchResult]:
            with self._factory()() as ddgs:
                rows = list(ddgs.text(query, region=self.region, safesearch=self.safesearch, max_results=max_results))
            seen: set[str] = set()
            results: list[ResearchResult] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                url = str(row.get("href") or row.get("url") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                results.append(ResearchResult(
                    title=str(row.get("title") or "Bez tytułu").strip(),
                    url=url,
                    body=str(row.get("body") or row.get("snippet") or "").strip(),
                    query=query,
                    hop=hop,
                    metadata={k: v for k, v in row.items() if k not in {"title","href","url","body","snippet"}},
                ))
            return results

        return await asyncio.to_thread(search_sync)

    async def fetch_pdf_documents(self, topic: str, max_results: int = 5) -> list[ResearchResult]:
        topic = topic.strip()
        if not topic:
            raise ValueError("topic cannot be empty")
        return await self.aget_results(f"{topic} filetype:pdf", max_results)

    @staticmethod
    def _candidate_hop_queries(results: list[ResearchResult], *, max_queries: int) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()
        for result in results:
            words = result.body.split()
            phrase = " ".join(words[:8]).strip()
            if phrase and phrase not in seen:
                seen.add(phrase)
                candidates.append(phrase)
            if len(candidates) >= max_queries:
                break
        return candidates[:max_queries]

    async def execute_rag_pipeline(self, queries: list[str], *, max_hops: int = 2,
                                   max_results: int = 5, max_followup_queries: int = 4) -> ResearchReport:
        seeds = [q.strip() for q in queries if q.strip()]
        if not seeds:
            raise ValueError("queries cannot be empty")
        if max_hops < 1:
            raise ValueError("max_hops must be at least 1")

        frontier = seeds
        all_results: list[ResearchResult] = []
        seen_urls: set[str] = set()
        completed_hops = 0

        for hop in range(max_hops):
            if not frontier:
                break
            batches = await asyncio.gather(*(self.aget_results(q, max_results, hop=hop) for q in frontier))
            current: list[ResearchResult] = []
            for batch in batches:
                for result in batch:
                    if result.url in seen_urls:
                        continue
                    seen_urls.add(result.url)
                    current.append(result)
                    all_results.append(result)
            completed_hops = hop + 1
            if hop + 1 < max_hops:
                frontier = self._candidate_hop_queries(current, max_queries=max_followup_queries)

        parts = [f"ZEBRANY MATERIAŁ BADAWCZY RAG 2.0\nPYTANIE: {' | '.join(seeds)}"]
        for i, result in enumerate(all_results, 1):
            parts.append(f"\n[ŹRÓDŁO {i} | hop={result.hop}] {result.title}\nURL: {result.url}\nTreść: {result.body}")
        return ResearchReport(query=" | ".join(seeds), hops=completed_hops,
                              sources=tuple(all_results), context="".join(parts))

    async def search_news(self, query: str, max_results: int = 5) -> list[ResearchResult]:
        query = query.strip()
        if not query:
            raise ValueError("query cannot be empty")
        def search_sync() -> list[ResearchResult]:
            with self._factory()() as ddgs:
                rows = list(ddgs.news(query, region=self.region, safesearch=self.safesearch, max_results=max_results))
            return [ResearchResult(title=str(r.get("title") or "Bez tytułu"), url=str(r.get("url") or ""),
                                   body=str(r.get("body") or ""), query=query,
                                   metadata={"date": r.get("date"), "source": r.get("source")})
                    for r in rows if isinstance(r, dict) and r.get("url")]
        return await asyncio.to_thread(search_sync)
