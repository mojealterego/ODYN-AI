from __future__ import annotations

from dataclasses import dataclass
import re

from odyn_ai.config import SYSTEM_PROMPTS
from odyn_ai.core.search import OdynInternetAccess
from odyn_ai.core.state import JsonStore


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    prompt: str
    can_search: bool = False
    mode: str = "no_code"
    code: str = ""


class AgentManager:
    def __init__(self, data_dir: str | None = None) -> None:
        self.internet = OdynInternetAccess()
        self._store = JsonStore("agents", data_dir)
        self._agents = {
            "odyn_glowny": AgentDefinition("odyn_glowny", "ODYN AI — Ogólny", SYSTEM_PROMPTS["default"], False, "no_code", ""),
            "odyn_koder": AgentDefinition("odyn_koder", "ODYN AI — Koder", SYSTEM_PROMPTS["coder"], False, "no_code", ""),
            "odyn_czarny_kruk": AgentDefinition(
                "odyn_czarny_kruk",
                "ODYN AI — Czarny Kruk",
                SYSTEM_PROMPTS["researcher"],
                True,
                "no_code",
                "",
            ),
        }
        for item in self._store.load([]):
            try:
                value = AgentDefinition(**item)
                if value.agent_id not in self._agents:
                    self._agents[value.agent_id] = value
            except (TypeError, ValueError):
                continue

    def _persist(self) -> None:
        custom = [
            {"agent_id": a.agent_id, "name": a.name, "prompt": a.prompt,
             "can_search": a.can_search, "mode": a.mode, "code": a.code}
            for agent_id, a in self._agents.items()
            if agent_id not in {"odyn_glowny", "odyn_koder", "odyn_czarny_kruk"}
        ]
        self._store.save(custom)

    def list_agents(self) -> list[dict[str, object]]:
        return [{"id": a.agent_id, "name": a.name, "can_search": a.can_search, "mode": a.mode} for a in self._agents.values()]

    def get(self, agent_id: str) -> AgentDefinition:
        return self._agents.get(agent_id, self._agents["odyn_glowny"])

    def create(self, agent_id: str, name: str, prompt: str, can_search: bool = False) -> AgentDefinition:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", agent_id):
            raise ValueError("Identyfikator agenta może zawierać wyłącznie małe litery, cyfry, myślniki i podkreślenia.")
        if not name.strip() or not prompt.strip():
            raise ValueError("Nazwa agenta i instrukcja agenta są wymagane.")
        value = AgentDefinition(agent_id, name.strip(), prompt.strip(), can_search, "no_code", "")
        self._agents[agent_id] = value
        self._persist()
        return value

    def create_code(self, agent_id: str, name: str, source: str) -> AgentDefinition:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", agent_id):
            raise ValueError("Identyfikator agenta może zawierać wyłącznie małe litery, cyfry, myślniki i podkreślenia.")
        if not name.strip() or not source.strip():
            raise ValueError("Nazwa agenta i kod agenta są wymagane.")
        value = AgentDefinition(agent_id, name.strip(), name.strip(), False, "code", source)
        self._agents[agent_id] = value
        self._persist()
        return value

    async def preprocess(self, messages: list[dict[str, str]], agent_id: str) -> list[dict[str, str]]:
        agent = self.get(agent_id)
        if not agent.can_search:
            return messages

        last = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        triggers = (
            "wyszukaj",
            "internet",
            "najnowsze",
            "sprawdź",
            "sprawdz",
            "aktualne",
            "dzisiaj",
            "co to jest",
            "kto to",
        )
        if not any(trigger in last.lower() for trigger in triggers):
            return messages

        query = re.sub(
            r"(?i)\b(wyszukaj(?: w internecie)?|sprawdź(?: w sieci)?|sprawdz(?: w sieci)?)\b",
            "",
            last,
        ).strip()
        if not query:
            return messages

        context = self.internet.format_context(await self.internet.search_web(query))
        return [*messages[:-1], {"role": "system", "content": context}, messages[-1]]
