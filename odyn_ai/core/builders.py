from __future__ import annotations
from dataclasses import asdict, dataclass
from uuid import uuid4

@dataclass
class AppDefinition:
    app_id: str
    name: str
    description: str
    agent_id: str
    language: str = "pl"

class AppBuilder:
    def __init__(self) -> None:
        self._apps: dict[str, AppDefinition] = {}
    def list_apps(self) -> list[dict[str, object]]:
        return [asdict(a) for a in self._apps.values()]
    def create(self, name: str, description: str, agent_id: str, language: str = "pl") -> dict[str, object]:
        if not name.strip():
            raise ValueError("Nazwa aplikacji jest wymagana")
        app = AppDefinition(f"app_{uuid4().hex[:12]}", name.strip(), description.strip(), agent_id, language if language in {"pl", "en"} else "pl")
        self._apps[app.app_id] = app
        return asdict(app)
