from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol, Sequence

from nexus_core.reasoning.cognitive_engine import AdversarialGateResult, CognitiveEngine, DecisionCycle

from .llm_dual_engine import DualModelEngine


class TemporalEvidenceRetriever(Protocol):
    def retrieve(
        self,
        query: str,
        *,
        valid_at: datetime,
        transaction_at: datetime,
        top_k: int = 8,
    ) -> Any: ...


@dataclass(frozen=True)
class CriticResult:
    decision: str
    confidence: float
    safety: float
    logic: float
    reason: str
    raw: str = ""

    @property
    def rejected(self) -> bool:
        return self.decision.casefold() in {"reject", "rejected", "odrzucono", "fail"}

    @classmethod
    def from_text(cls, text: str) -> "CriticResult":
        try:
            data = json.loads(text)
            decision = str(data.get("decision", "accept"))
            confidence = float(data.get("confidence", 0.0))
            safety = float(data.get("safety", 0.0))
            logic = float(data.get("logic", 0.0))
            reason = str(data.get("reason", ""))
        except (json.JSONDecodeError, TypeError, ValueError):
            normalized = text.casefold()
            rejected = any(marker in normalized for marker in ("odrzucono", "rejected", "critical", "błąd krytyczny", "fail"))
            decision = "reject" if rejected else "accept"
            confidence = 1.0 if rejected else 0.5
            safety = 0.0 if rejected else 0.5
            logic = 0.0 if rejected else 0.5
            reason = text.strip()
        return cls(
            decision=decision,
            confidence=max(0.0, min(1.0, confidence)),
            safety=max(0.0, min(1.0, safety)),
            logic=max(0.0, min(1.0, logic)),
            reason=reason,
            raw=text,
        )

    def gate_text(self) -> str:
        return "REJECT" if self.rejected else "PASS"


@dataclass(frozen=True)
class CognitiveInferenceResult:
    output: str
    critic: CriticResult
    gate: AdversarialGateResult
    decision: DecisionCycle
    context: str
    reflections: int


class CognitiveInferencePipeline:
    """Physical inference bridge: Dual GGUF -> Critic -> CognitiveEngine -> Reflexion."""

    def __init__(
        self,
        dual_engine: DualModelEngine,
        *,
        cognitive_engine: CognitiveEngine | None = None,
        temporal_retriever: TemporalEvidenceRetriever | None = None,
    ) -> None:
        self.dual = dual_engine
        self.cognitive = cognitive_engine or CognitiveEngine()
        self.temporal_retriever = temporal_retriever

    async def _critic(self, task: str, draft: str) -> CriticResult:
        raw = await self.dual.evaluate_critic(task, draft)
        return CriticResult.from_text(raw)

    async def _correct(
        self, task: str, draft: str, critic: CriticResult, evidence: str
    ) -> str:
        return await self.dual.correct_with_primary(
            task,
            draft,
            critic,
            evidence=evidence,
        )

    async def run(
        self,
        task: str,
        *,
        strategies: Sequence[str],
        fitness_fn: Callable[[str, str], float],
        temporal_evidence: str = "",
        temporal_valid_at: datetime | None = None,
        temporal_transaction_at: datetime | None = None,
        state_embedding: Sequence[float] = (1.0,),
        target_embedding: Sequence[float] = (1.0,),
        max_reflections: int = 1,
        search_depth: int = 1,
    ) -> CognitiveInferenceResult:
        if not task.strip():
            raise ValueError("task cannot be empty")
        if not strategies:
            raise ValueError("strategies cannot be empty")
        if max_reflections < 0:
            raise ValueError("max_reflections cannot be negative")

        await self.dual.start()
        evidence = temporal_evidence.strip()
        if self.temporal_retriever is not None:
            if temporal_valid_at is None or temporal_transaction_at is None:
                raise ValueError(
                    "temporal_valid_at and temporal_transaction_at are required "
                    "when temporal_retriever is configured"
                )
            temporal_result = self.temporal_retriever.retrieve(
                task,
                valid_at=temporal_valid_at,
                transaction_at=temporal_transaction_at,
            )
            evidence = str(getattr(temporal_result, "rag_context", "")).strip()
        context = evidence if evidence else "[TEMPORAL EVIDENCE]: none"

        draft = await self.dual.generate_primary(
            f"{task}\n\n{context}"
        )
        critic = await self._critic(task, draft)
        reflections = 0

        while True:
            decision = self.cognitive.decision_cycle(
                task,
                strategies,
                fitness_fn,
                context={"temporal_evidence": evidence, "critic_reason": critic.reason},
                critic_result=critic.gate_text(),
                state_embedding=state_embedding,
                target_embedding=target_embedding,
                search_depth=search_depth,
            )
            if not decision.gate.rejected:
                return CognitiveInferenceResult(
                    output=draft,
                    critic=critic,
                    gate=decision.gate,
                    decision=decision,
                    context=context,
                    reflections=reflections,
                )

            if reflections >= max_reflections:
                return CognitiveInferenceResult(
                    output=(
                        "Adversarial Gating Interwencja: "
                        "Odpowiedź zatrzymana przez moduł ewaluacyjny."
                    ),
                    critic=critic,
                    gate=decision.gate,
                    decision=decision,
                    context=context,
                    reflections=reflections,
                )

            draft = await self._correct(task, draft, critic, evidence)
            reflections += 1
            critic = await self._critic(task, draft)
