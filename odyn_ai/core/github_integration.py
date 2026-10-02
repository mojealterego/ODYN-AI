from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping

import httpx


@dataclass(frozen=True)
class GitHubCommitResult:
    repository: str
    branch: str
    commit_sha: str
    url: str


class GitHubIntegration:
    """GitHub Contents/Git Data API integration using a token kept outside project data."""

    def __init__(self, token: str | None = None, api_base: str = "https://api.github.com") -> None:
        self.token = token or os.getenv("ODYN_GITHUB_TOKEN")
        self.api_base = api_base.rstrip("/")

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise PermissionError("Brak ODYN_GITHUB_TOKEN. GitHub integration działa tylko po świadomym skonfigurowaniu tokena.")
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def commit_files(
        self,
        repository: str,
        files: Mapping[str, str],
        message: str,
        branch: str = "main",
        create_branch: bool = False,
    ) -> GitHubCommitResult:
        if not repository or "/" not in repository:
            raise ValueError("Repository musi mieć format owner/name.")
        if not files:
            raise ValueError("Brak plików do wysłania.")
        if not message.strip():
            raise ValueError("Commit message jest wymagany.")
        headers = self._headers()
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            repo_url = f"{self.api_base}/repos/{repository}"
            repo_response = await client.get(repo_url, headers=headers)
            repo_response.raise_for_status()
            default_branch = repo_response.json().get("default_branch", "main")
            base_branch = branch or default_branch
            if create_branch:
                base_ref = await client.get(f"{repo_url}/git/ref/heads/{base_branch}", headers=headers)
                base_ref.raise_for_status()
                sha = base_ref.json()["object"]["sha"]
                await client.post(
                    f"{repo_url}/git/refs",
                    headers=headers,
                    json={"ref": f"refs/heads/{branch}", "sha": sha},
                )
            ref = await client.get(f"{repo_url}/git/ref/heads/{base_branch}", headers=headers)
            ref.raise_for_status()
            parent_sha = ref.json()["object"]["sha"]
            commit = await client.get(f"{repo_url}/git/commits/{parent_sha}", headers=headers)
            commit.raise_for_status()
            base_tree = commit.json()["tree"]["sha"]
            tree_items = []
            for path, content in files.items():
                if not path or path.startswith("/") or ".." in path.split("/"):
                    raise ValueError(f"Niebezpieczna ścieżka GitHub: {path}")
                blob = await client.post(
                    f"{repo_url}/git/blobs",
                    headers=headers,
                    json={"content": content, "encoding": "utf-8"},
                )
                blob.raise_for_status()
                tree_items.append({"path": path, "mode": "100644", "type": "blob", "sha": blob.json()["sha"]})
            tree = await client.post(
                f"{repo_url}/git/trees",
                headers=headers,
                json={"base_tree": base_tree, "tree": tree_items},
            )
            tree.raise_for_status()
            commit_response = await client.post(
                f"{repo_url}/git/commits",
                headers=headers,
                json={"message": message, "tree": tree.json()["sha"], "parents": [parent_sha]},
            )
            commit_response.raise_for_status()
            commit_sha = commit_response.json()["sha"]
            update_ref = await client.patch(
                f"{repo_url}/git/refs/heads/{base_branch}",
                headers=headers,
                json={"sha": commit_sha},
            )
            update_ref.raise_for_status()
            return GitHubCommitResult(
                repository=repository,
                branch=base_branch,
                commit_sha=commit_sha,
                url=f"https://github.com/{repository}/commit/{commit_sha}",
            )
