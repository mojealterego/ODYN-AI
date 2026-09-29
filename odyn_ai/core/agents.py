from __future__ import annotations
from dataclasses import dataclass
import re
from odyn_ai.config import SYSTEM_PROMPTS
from odyn_ai.core.search import OdynInternetAccess

@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    prompt: str
    can_search: bool = False

class AgentManager:
    def __init__(self) -> None:
        self.internet = OdynInternetAccess()
        self._agents = {
            "odyn_glowny": AgentDefinition("odyn_glowny", "ODYN AI — Ogólny", SYSTEM_PROMPTS["default"]),
            "odyn_koder": AgentDefinition("odyn_koder", "ODYN AI — Koder", SYSTEM_PROMPTS["coder"]),
            "odyn_czarny_kruk": AgentDefinition("odyn_czarny_kruk", "ODYN AI — Czarny Kruk", SYSTEM_PROMPTS["researcher"], True),
        }

    def list_agents(self) -> list[dict[str, object]]:
        return [{"id": a.agent_id, "name": a.name, "can_search": a.can_search} for a in self._agents.values()]

    def get(self, agent_id: str) -> AgentDefinition:
        return self._agents.get(agent_id, self._agents["odyn_glowny"])

    def create(self, agent_id: str, name: str, prompt: str, can_search: bool = False) -> AgentDefinition:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", agent_id):
            raise ValueError("agent_id musi być bezpiecznym identyfikatorem")
        if not name.strip() or not prompt.strip():
            raise ValueError("name i prompt są wymagane")
        value = AgentDefinition(agent_id, name.strip(), prompt.strip(), can_search)
        self._agents[agent_id] = value
        return value

    async def preprocess(self, messages: list[dict[str, str]], agent_id: str) -> list[dict[str, str]]:
        agent = self.get(agent_id)
        if not agent.can_search:
            return messages
        last = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        triggers = ("wyszukaj", "internet", "najnowsze", "sprawdź", "sprawdz", "aktualne", "dzisiaj", "co to jest", "kto to")
        if not any(t in last.lower() for t in triggers):
            return messages
        query = re.sub(r"(?i)\b(wyszukaj(?: w internecie)?|sprawdź(?: w sieci)?|sprawdz(?: w sieci)?)\b", "", last).strip()
        if not query:
            return messages
        context = self.internet.format_context(await self.internet.search_web(query))
        return [*messages[:-1], {"role": "system", "content": context}, messages[-1]]
