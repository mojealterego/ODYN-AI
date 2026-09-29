from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from odyn_ai.core.coding_agent import CodingAgent
from odyn_ai.core.execution import ExecutionEngine, ExecutionRequest
from odyn_ai.core.github_integration import GitHubIntegration


@dataclass
class PipelineResult:
    app_id: str
    ok: bool
    changes: list[dict[str, str]]
    test: dict[str, Any]
    build: dict[str, Any] | None
    github: dict[str, Any] | None
    stage: str
    diagnostics: list[str]


class AutonomousBuildOrchestrator:
    """ODYN's edit -> test -> build -> verify -> GitHub pipeline."""

    def __init__(self, apps, engine, coding_agent: CodingAgent, github: GitHubIntegration) -> None:
        self.apps = apps
        self.execution = engine
        self.coding_agent = coding_agent
        self.github = github

    async def run(
        self,
        app_id: str,
        instruction: str,
        timeout: float = 300,
        github_repository: str | None = None,
        github_branch: str = "main",
        github_message: str = "feat(odyn): autonomous project update",
    ) -> PipelineResult:
        project = self.apps.workspace(app_id)
        edited = await self.coding_agent.apply(project["platform"], instruction, project["files"])
        for path, content in edited["files"].items():
            if project["files"].get(path) != content:
                self.apps.write_file(app_id, path, content)

        test = await self.execution.execute(
            ExecutionRequest(project["platform"], "test", edited["files"], timeout)
        )
        if not test.ok:
            return PipelineResult(
                app_id, False, edited["changes"], asdict(test), None, None,
                "test", test.diagnostics + ["Build został zatrzymany, ponieważ testy nie przeszły."]
            )

        build = await self.execution.execute(
            ExecutionRequest(project["platform"], "build", edited["files"], timeout)
        )
        if not build.ok:
            return PipelineResult(
                app_id, False, edited["changes"], asdict(test), asdict(build), None,
                "build", build.diagnostics + ["Weryfikacja artefaktu nie powiodła się."]
            )

        github_result = None
        if github_repository:
            github_result = asdict(await self.github.commit_files(
                github_repository, edited["files"], github_message, github_branch, False
            ))

        return PipelineResult(
            app_id, True, edited["changes"], asdict(test), asdict(build),
            github_result, "verified", ["Testy PASS", "Build PASS", "Artefakt zweryfikowany."]
        )
