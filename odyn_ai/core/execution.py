from __future__ import annotations

from dataclasses import dataclass, field
import asyncio
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Mapping


@dataclass(frozen=True)
class ExecutionRequest:
    platform: str
    action: str
    files: Mapping[str, str]
    timeout: float = 300.0


@dataclass
class ExecutionResult:
    platform: str
    action: str
    command: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    workspace: str
    artifact: str | None = None
    duration_ms: int = 0
    ok: bool = False
    diagnostics: list[str] = field(default_factory=list)


class ExecutionPolicy:
    """Deny-by-default process policy for generated projects."""

    allowed_platforms = {"web", "android"}
    allowed_actions = {"run", "build", "test"}

    def validate(self, request: ExecutionRequest) -> None:
        if request.platform not in self.allowed_platforms:
            raise ValueError("Nieobsługiwana platforma wykonawcza.")
        if request.action not in self.allowed_actions:
            raise ValueError("Nieobsługiwana akcja wykonawcza.")
        if not 0 < request.timeout <= 900:
            raise ValueError("Limit wykonania musi mieścić się w zakresie 1–900 sekund.")
        for raw in request.files:
            path = PurePosixPath(raw)
            if path.is_absolute() or ".." in path.parts or raw.startswith(("~", "/")):
                raise ValueError(f"Niebezpieczna ścieżka workspace: {raw}")
            if len(raw) > 240:
                raise ValueError("Ścieżka pliku jest zbyt długa.")


class ExecutionEngine:
    """Materializes an AppBuilder project, executes its platform toolchain and returns diagnostics."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or os.getenv("ODYN_EXECUTION_DIR", tempfile.gettempdir())).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.policy = ExecutionPolicy()

    @staticmethod
    def _command(platform: str, action: str) -> list[str]:
        if platform == "web":
            return {
                "run": ["npm", "run", "dev", "--", "--host", "127.0.0.1"],
                "build": ["npm", "run", "build"],
                "test": ["npm", "test"],
            }[action]
        return {
            "run": ["./gradlew", ":app:installDebug"],
            "build": ["./gradlew", "assembleDebug"],
            "test": ["./gradlew", "test"],
        }[action]

    @staticmethod
    def _artifact(platform: str, action: str, root: Path) -> str | None:
        if action != "build":
            return None
        if platform == "web":
            candidate = root / "dist"
        else:
            candidates = list((root / "app" / "build" / "outputs" / "apk").rglob("*.apk"))
            candidate = candidates[0] if candidates else None
        return str(candidate.relative_to(root)) if candidate and candidate.exists() else None

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.policy.validate(request)
        command = self._command(request.platform, request.action)
        with tempfile.TemporaryDirectory(prefix="odyn-exec-", dir=self.base_dir) as temp:
            root = Path(temp)
            for raw_path, content in request.files.items():
                target = root / PurePosixPath(raw_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            if request.platform == "android":
                wrapper = root / "gradlew"
                if wrapper.exists():
                    wrapper.chmod(wrapper.stat().st_mode | 0o111)
            start = asyncio.get_running_loop().time()
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=root,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self._environment(),
                )
                try:
                    stdout_b, stderr_b = await asyncio.wait_for(process.communicate(), timeout=request.timeout)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    raise
                exit_code = process.returncode
            except FileNotFoundError as exc:
                exit_code = None
                stdout_b = b""
                stderr_b = str(exc).encode()
            except asyncio.TimeoutError:
                exit_code = -1
                stdout_b = b""
                stderr_b = f"Przekroczono limit {request.timeout:g} s.".encode()
            duration_ms = int((asyncio.get_running_loop().time() - start) * 1000)
            stdout = stdout_b.decode("utf-8", errors="replace")[-20000:]
            stderr = stderr_b.decode("utf-8", errors="replace")[-20000:]
            artifact = self._artifact(request.platform, request.action, root)
            diagnostics = []
            if exit_code is None:
                diagnostics.append("Narzędzie toolchain nie jest dostępne w środowisku wykonawczym.")
            elif exit_code != 0:
                diagnostics.append("Proces zakończył się kodem innym niż zero.")
            elif request.action == "build" and artifact is None:
                diagnostics.append("Build zakończył się kodem 0, ale nie znaleziono oczekiwanego artefaktu.")
            return ExecutionResult(
                platform=request.platform,
                action=request.action,
                command=command,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                workspace=str(root),
                artifact=artifact,
                duration_ms=duration_ms,
                ok=exit_code == 0 and (request.action != "build" or artifact is not None),
                diagnostics=diagnostics,
            )

    @staticmethod
    def _environment() -> dict[str, str]:
        env = os.environ.copy()
        # Generated builds must not inherit interactive terminal behaviour.
        env["CI"] = "1"
        env["GIT_TERMINAL_PROMPT"] = "0"
        return env
