from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class MCPWorkerLimits:
    memory: str = "256m"
    cpus: str = "1"
    pids: int = 64
    timeout: int = 30


class DockerMCPWorker:
    """Fail-closed Docker worker with network-none and a host capability broker."""

    def __init__(
        self,
        *,
        image: str = "odyn-ai-mcp-worker:latest",
        docker_binary: str = "docker",
        limits: MCPWorkerLimits | None = None,
    ) -> None:
        self.image = image
        self.docker_binary = docker_binary
        self.limits = limits or MCPWorkerLimits()

    def require_available(self) -> None:
        if shutil.which(self.docker_binary) is None:
            raise PermissionError("Docker MCP Worker jest niedostępny.")

    def build_command(self) -> list[str]:
        self.require_available()
        return [
            self.docker_binary, "run", "--rm", "-i",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--security-opt=seccomp=builtin",
            "--pids-limit", str(self.limits.pids),
            "--memory", self.limits.memory,
            "--cpus", self.limits.cpus,
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
            "--user", "65532:65532",
            self.image,
            "python", "-m", "odyn_ai.core.mcp_worker",
        ]

    def execute(
        self,
        request: dict,
        *,
        broker: Callable[[dict], dict],
    ) -> dict:
        self.require_available()
        process = subprocess.Popen(
            self.build_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            process.stdin.close()
            line = process.stdout.readline()
            if not line:
                stderr = process.stderr.read()
                raise RuntimeError(f"MCP Worker nie zwrócił żądania brokera: {stderr[-1000:]}")
            message = json.loads(line)
            if message.get("type") == "error":
                raise PermissionError(message.get("error", "Worker odrzucił operację."))
            if message.get("type") != "broker_request":
                raise RuntimeError("Nieprawidłowa odpowiedź protokołu MCP Worker.")
            result = broker(message["request"])
            if process.poll() is None:
                process.terminate()
            return result
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
