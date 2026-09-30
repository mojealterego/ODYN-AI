from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from odyn_ai.core.search import OdynInternetAccess, SearchResult


@dataclass
class LLMModelMetadata:
    model_id: str
    tags: list[str]
    downloads: int
    is_mounted: bool = False
    source: str = "huggingface"


@dataclass
class TechReconData:
    competitor_name: str
    discovered_features: list[str]
    mcp_servers_found: list[str]
    sources: list[str] = field(default_factory=list)


@dataclass
class RoadmapDirective:
    version: str
    architecture_changes: list[str]
    code_mutations_required: list[dict[str, str]]
    evidence: list[str] = field(default_factory=list)


class ModelRepository(Protocol):
    def scan_for_obliterate_models(self, limit: int = 5) -> list[LLMModelMetadata]: ...
    def download_and_mount_model(self, model_id: str, filename: str) -> bool: ...


class WebResearch(Protocol):
    async def search_web(self, query: str, max_results: int = 5) -> list[SearchResult]: ...


class GitLabRepository(Protocol):
    def commit_dgm_mutation(
        self, branch: str, commit_message: str, actions: list[dict[str, str]]
    ) -> bool: ...


class HuggingFaceClient:
    OBLITERATE_TAG = "obliterate"

    def __init__(self, token: str | None, storage_path: str) -> None:
        self.token = token
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

    def _api(self):
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise RuntimeError("Brak huggingface_hub.") from exc
        return HfApi(token=self.token or None)

    def scan_for_obliterate_models(self, limit: int = 5) -> list[LLMModelMetadata]:
        limit = max(1, min(limit, 100))
        models = self._api().list_models(
            tags=[self.OBLITERATE_TAG],
            sort="createdAt",
            direction=-1,
            limit=limit,
        )
        return [
            LLMModelMetadata(
                model_id=model.modelId,
                tags=list(getattr(model, "tags", []) or []),
                downloads=int(getattr(model, "downloads", 0) or 0),
            )
            for model in models
            if self.OBLITERATE_TAG in (getattr(model, "tags", []) or [])
            or self.OBLITERATE_TAG in model.modelId.lower()
        ]

    def download_and_mount_model(self, model_id: str, filename: str) -> bool:
        try:
            from huggingface_hub import hf_hub_download

            filepath = hf_hub_download(
                repo_id=model_id,
                filename=filename,
                cache_dir=self.storage_path,
            )
            logging.info("Model pobrany: %s -> %s", model_id, filepath)
            return True
        except Exception:
            logging.exception("Nie udało się pobrać modelu %s", model_id)
            return False


class InternetModelDiscovery:
    def __init__(self, internet: WebResearch | None = None) -> None:
        self.internet = internet or OdynInternetAccess()

    async def search_obliterate_models(self, max_results: int = 10) -> list[SearchResult]:
        queries = (
            '"obliterate" GGUF model',
            '"obliterate" LLM model Hugging Face',
            '"obliterate" model GGUF GitHub',
        )
        results: list[SearchResult] = []
        seen: set[str] = set()
        for query in queries:
            for result in await self.internet.search_web(query, max_results=max_results):
                if result.url and result.url not in seen:
                    seen.add(result.url)
                    results.append(result)
        return results


class ModelScoutAgent:
    def __init__(
        self,
        hf_client: ModelRepository,
        internet: WebResearch | None = None,
    ) -> None:
        self.hf_client = hf_client
        self.web = InternetModelDiscovery(internet)

    async def execute(
        self,
        limit: int = 5,
        download: bool = True,
    ) -> list[LLMModelMetadata]:
        models = await asyncio.to_thread(
            self.hf_client.scan_for_obliterate_models, limit
        )
        web_results = await self.web.search_obliterate_models(max_results=5)
        known_ids = {m.model_id.lower() for m in models}

        for result in web_results:
            if "obliterate" not in f"{result.title} {result.snippet}".lower():
                continue
            candidate = result.url.rsplit("/", 1)[-1].strip()
            if candidate and candidate.lower() not in known_ids:
                models.append(
                    LLMModelMetadata(
                        model_id=candidate,
                        tags=["obliterate"],
                        downloads=0,
                        source=result.url,
                    )
                )
                known_ids.add(candidate.lower())
            if len(models) >= limit:
                break

        models = models[:limit]
        if not download:
            return models

        # Only Hugging Face candidates are downloadable automatically. Web
        # discovery is intentionally evidence-only until a concrete repository
        # and file have been verified.
        for model in models:
            if model.source != "huggingface":
                continue
            filename = f"{model.model_id.split('/')[-1]}-Q4_K_M.gguf"
            model.is_mounted = await asyncio.to_thread(
                self.hf_client.download_and_mount_model,
                model.model_id,
                filename,
            )
        return models


class TechReconAgent:
    def __init__(self, internet: WebResearch | None = None) -> None:
        self.internet = internet or OdynInternetAccess()

    async def execute(
        self,
        topics: list[str] | None = None,
        max_results_per_topic: int = 5,
    ) -> list[TechReconData]:
        topics = topics or [
            "AI coding agents",
            "autonomous AI agents",
            "MCP servers",
            "local LLM GGUF agents",
            "AI app builders",
        ]

        async def collect(topic: str) -> tuple[str, list[SearchResult]]:
            return topic, await self.internet.search_web(
                topic, max_results=max_results_per_topic
            )

        collected = await asyncio.gather(*(collect(topic) for topic in topics))
        recon: list[TechReconData] = []

        for topic, results in collected:
            features: list[str] = []
            mcp_servers: list[str] = []
            sources: list[str] = []

            for result in results:
                sources.append(result.url)
                text = f"{result.title} {result.snippet}".lower()
                if "mcp" in text:
                    mcp_servers.append(result.title)
                features.append(result.title)

            recon.append(
                TechReconData(
                    competitor_name=topic,
                    discovered_features=features,
                    mcp_servers_found=list(dict.fromkeys(mcp_servers)),
                    sources=list(dict.fromkeys(sources)),
                )
            )
        return recon


class StrategistAgent:
    async def execute(
        self,
        recon_data: list[TechReconData],
        version: str = "1.1.0-ODYN-EVOLUTION",
    ) -> RoadmapDirective:
        architecture_changes: list[str] = []
        evidence: list[str] = []
        for data in recon_data:
            architecture_changes.extend(data.discovered_features[:10])
            evidence.extend(data.sources[:10])

        return RoadmapDirective(
            version=version,
            architecture_changes=list(dict.fromkeys(architecture_changes)),
            code_mutations_required=[],
            evidence=list(dict.fromkeys(evidence)),
        )


class DGMUpdateAgent:
    def __init__(self, gitlab_client: GitLabRepository) -> None:
        self.gitlab_client = gitlab_client

    async def execute(
        self,
        roadmap: RoadmapDirective,
        branch: str = "odyn-evolution",
    ) -> bool:
        if not roadmap.code_mutations_required:
            logging.info("Brak zatwierdzonych mutacji kodu; nic nie commituję.")
            return True

        for action in roadmap.code_mutations_required:
            if action.get("action") not in {"create", "update", "delete", "move"}:
                raise ValueError(f"Nieobsługiwana akcja GitLab: {action.get('action')}")
            if not action.get("file_path"):
                raise ValueError("Każda mutacja GitLab wymaga file_path.")

        message = f"Auto-Update: ODYN Evolution {roadmap.version}"
        return await asyncio.to_thread(
            self.gitlab_client.commit_dgm_mutation,
            branch,
            message,
            roadmap.code_mutations_required,
        )


class GitLabUltimateClient:
    def __init__(self, url: str, token: str, project_id: int) -> None:
        try:
            import gitlab
        except ImportError as exc:
            raise RuntimeError("Brak python-gitlab.") from exc
        self.gl = gitlab.Gitlab(url.rstrip("/"), private_token=token)
        self.project = self.gl.projects.get(project_id)

    def commit_dgm_mutation(
        self,
        branch: str,
        commit_message: str,
        actions: list[dict[str, str]],
    ) -> bool:
        try:
            self.project.commits.create(
                {
                    "branch": branch,
                    "commit_message": commit_message,
                    "actions": actions,
                }
            )
            return True
        except Exception:
            logging.exception("Błąd podczas commita GitLab")
            return False


class AppForgeGenerator:
    def __init__(self, niche_apps_count: int = 33, dev_apps_count: int = 33) -> None:
        self.niche_apps_count = niche_apps_count
        self.dev_apps_count = dev_apps_count

    def generate_application_matrix(self) -> dict[str, Any]:
        return {
            "niche_apps": [
                f"NicheApp_{i}" for i in range(1, self.niche_apps_count + 1)
            ],
            "dev_apps": [
                f"DevApp_{i}" for i in range(1, self.dev_apps_count + 1)
            ],
            "game_builder_sdk": {
                "engine": "HTML5/Canvas + Python Backend",
                "modules": [
                    "PhysicsEngine",
                    "SpriteRenderer",
                    "StateOrchestrator",
                ],
            },
        }


class SwarmOrchestrator:
    def __init__(
        self,
        hf_client: ModelRepository,
        internet: WebResearch | None,
        gitlab_client: GitLabRepository,
        *,
        app_forge: AppForgeGenerator | None = None,
    ) -> None:
        self.scout = ModelScoutAgent(hf_client, internet)
        self.recon = TechReconAgent(internet)
        self.strategist = StrategistAgent()
        self.dgm_core = DGMUpdateAgent(gitlab_client)
        self.app_forge = app_forge or AppForgeGenerator()

    async def run_cycle(
        self,
        *,
        topics: list[str] | None = None,
        model_limit: int = 5,
        download_models: bool = False,
        mutation_branch: str = "odyn-evolution",
    ) -> dict[str, Any]:
        app_matrix = self.app_forge.generate_application_matrix()
        models = await self.scout.execute(model_limit, download_models)
        recon = await self.recon.execute(topics)
        roadmap = await self.strategist.execute(recon)
        updated = await self.dgm_core.execute(roadmap, mutation_branch)

        return {
            "application_matrix": app_matrix,
            "models": models,
            "recon": recon,
            "roadmap": roadmap,
            "updated": updated,
        }


def build_production_swarm() -> SwarmOrchestrator:
    hf_token = os.getenv("HF_TOKEN")
    gl_token = os.getenv("GL_TOKEN")
    gl_url = os.getenv("GL_URL", "https://gitlab.com")
    project_id = os.getenv("GL_PROJECT_ID")

    if not hf_token:
        raise RuntimeError("HF_TOKEN jest wymagany.")
    if not gl_token:
        raise RuntimeError("GL_TOKEN jest wymagany.")
    if not project_id:
        raise RuntimeError("GL_PROJECT_ID jest wymagany.")

    hf = HuggingFaceClient(hf_token, os.getenv("ODYN_MODELS_PATH", "./models_gguf"))
    gitlab = GitLabUltimateClient(gl_url, gl_token, int(project_id))
    return SwarmOrchestrator(hf, OdynInternetAccess(), gitlab)
