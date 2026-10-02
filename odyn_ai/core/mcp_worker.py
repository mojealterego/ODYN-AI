from __future__ import annotations

"""Minimal capability worker protocol.

The worker has no network access. It receives a fixed MCP operation and emits a
single broker request. The parent Gateway remains the only network-capable side.
"""

import json
import sys


class WorkerProtocolError(ValueError):
    pass


def validate_request(request: dict) -> dict:
    if not isinstance(request, dict):
        raise WorkerProtocolError("Żądanie workera musi być obiektem JSON.")
    if request.get("version") != 1:
        raise WorkerProtocolError("Nieobsługiwana wersja protokołu workera.")
    if request.get("operation") != "tools/call":
        raise WorkerProtocolError("Worker obsługuje wyłącznie tools/call.")
    server = request.get("server")
    tool = request.get("tool")
    arguments = request.get("arguments", {})
    if not isinstance(server, str) or not server:
        raise WorkerProtocolError("Brak serwera MCP.")
    if not isinstance(tool, str) or not tool:
        raise WorkerProtocolError("Brak nazwy narzędzia.")
    if not isinstance(arguments, dict):
        raise WorkerProtocolError("Argumenty narzędzia muszą być obiektem JSON.")
    # Secrets never travel through the worker protocol.
    forbidden = {"secret", "token", "authorization", "password", "client_secret"}
    if forbidden.intersection(request) or any(key.lower() in forbidden for key in arguments):
        raise WorkerProtocolError("Sekrety nie mogą być przekazywane w payloadzie workera.")
    return {
        "version": 1,
        "operation": "tools/call",
        "server": server,
        "tool": tool,
        "arguments": arguments,
    }


def run_stdio() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = validate_request(json.loads(line))
            print(json.dumps({"type": "broker_request", "request": request}, ensure_ascii=False), flush=True)
        except (json.JSONDecodeError, WorkerProtocolError) as exc:
            print(json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_stdio())
