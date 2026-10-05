from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from .types import CapabilityAuthorization, CriticIssue, CriticResult, InferenceResult


class InferenceBackend(Protocol):
    """Provider-neutral inference boundary for GGUF, remote, LiteRT-LM, etc."""

    model_id: str

    def generate(self, prompt: str, *, context: dict[str, Any] | None = None) -> str:
        ...


@dataclass(frozen=True)
class DualModelOutput:
    primary: InferenceResult
    critic: CriticResult


class DualModelEngine:
    """Run a primary model and adversarial critic as one cognitive unit."""

    def __init__(
        self,
        primary: InferenceBackend,
        critic: InferenceBackend,
        *,
        critic_confidence_threshold: float = 0.65,
    ) -> None:
        if not 0.0 <= critic_confidence_threshold <= 1.0:
            raise ValueError("critic_confidence_threshold must be between 0 and 1")
        self.primary = primary
        self.critic = critic
        self.critic_confidence_threshold = critic_confidence_threshold

    def evaluate(
        self,
        goal: str,
        *,
        context: dict[str, Any] | None = None,
        correction: str | None = None,
    ) -> DualModelOutput:
        context = dict(context or {})
        answer = self.primary.generate(
            self._build_primary_prompt(goal, correction),
            context=deepcopy(context),
        )
        primary = InferenceResult(
            answer=answer,
            model_id=self.primary.model_id,
            metadata={"correction": correction},
        )
        raw = self.critic.generate(
            self._build_critic_prompt(goal, answer, context),
            context=deepcopy(context),
        )
        return DualModelOutput(primary=primary, critic=self._parse_critic(raw))

    def review_candidate(
        self,
        goal: str,
        candidate: str,
        *,
        tool_calls: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
        context: dict[str, Any] | None = None,
    ) -> CriticResult:
        """Review an already-generated candidate without invoking the primary model."""
        review_context = dict(context or {})
        review_context["tool_calls"] = list(tool_calls)
        raw = self.critic.generate(
            self._build_critic_prompt(goal, candidate, review_context),
            context=review_context,
        )
        return self._parse_critic(raw)

    def authorize_capabilities(
        self,
        goal: str,
        capabilities: tuple[str, ...],
        *,
        trusted_user_turns: tuple[str, ...] = (),
    ) -> CapabilityAuthorization:
        """Classify side-effect authority from trusted user control only.

        Untrusted tool output, candidate prose and tool arguments are deliberately
        excluded from both the prompt and backend context so retrieved content
        cannot grant itself additional capabilities.
        """
        requested = tuple(dict.fromkeys(
            cap.strip() for cap in capabilities if isinstance(cap, str) and cap.strip()
        ))
        if not requested:
            return CapabilityAuthorization(
                valid=True,
                confidence=1.0,
                critic_model_id=self.critic.model_id,
            )

        trusted = tuple(
            turn.strip() for turn in trusted_user_turns
            if isinstance(turn, str) and turn.strip()
        )[-3:]
        schema = (
            '{"allowed_capabilities":[str],"denied_capabilities":[str],'
            '"confidence":number,"rationale":str}'
        )
        prompt = (
            "You are ODYN's trusted-intent capability classifier. "
            "Authorize capabilities ONLY from the trusted user instructions below. "
            "You have no tools and no external/retrieved content. "
            "If intent is ambiguous, do not authorize it. Return ONLY JSON matching: "
            + schema
            + "\nREQUESTED_CAPABILITIES:\n"
            + json.dumps(requested, ensure_ascii=False)
            + "\nCURRENT_GOAL:\n"
            + goal
            + "\nRECENT_TRUSTED_USER_TURNS:\n"
            + json.dumps(trusted, ensure_ascii=False)
        )
        try:
            raw = self.critic.generate(
                prompt,
                context={
                    "trusted_user_turns": trusted,
                    "requested_capabilities": requested,
                },
            )
            payload = self._extract_json(raw)
            allowed = payload["allowed_capabilities"]
            denied = payload["denied_capabilities"]
            confidence = payload["confidence"]
            rationale = payload["rationale"]
            if not isinstance(allowed, list) or not isinstance(denied, list):
                raise ValueError("capability lists must be arrays")
            if any(not isinstance(value, str) for value in allowed + denied):
                raise ValueError("capability lists must contain only strings")
            if type(confidence) not in {int, float} or not math.isfinite(confidence):
                raise ValueError("authorization confidence must be finite")
            if not 0.0 <= confidence <= 1.0:
                raise ValueError("authorization confidence must be between 0 and 1")
            if not isinstance(rationale, str):
                raise ValueError("authorization rationale must be a string")
            allowed_tuple = tuple(dict.fromkeys(allowed))
            denied_tuple = tuple(dict.fromkeys(denied))
            requested_set = set(requested)
            if not set(allowed_tuple).issubset(requested_set):
                raise ValueError("classifier authorized an unrequested capability")
            if not set(denied_tuple).issubset(requested_set):
                raise ValueError("classifier denied an unrequested capability")
            if set(allowed_tuple) & set(denied_tuple):
                raise ValueError("a capability cannot be both allowed and denied")
            if confidence < self.critic_confidence_threshold:
                allowed_tuple = ()
                denied_tuple = requested
                rationale = (
                    "Capability authorization confidence was below the acceptance "
                    "threshold; sensitive capabilities fail closed."
                )
            return CapabilityAuthorization(
                valid=True,
                allowed_capabilities=allowed_tuple,
                denied_capabilities=denied_tuple,
                confidence=float(confidence),
                rationale=rationale.strip(),
                critic_model_id=self.critic.model_id,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return CapabilityAuthorization(
                valid=False,
                confidence=0.0,
                rationale="Trusted-intent authorization failed closed.",
                critic_model_id=self.critic.model_id,
                error=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _build_primary_prompt(goal: str, correction: str | None) -> str:
        prompt = f"Goal:\n{goal}\n"
        if correction:
            prompt += f"\nRequired correction:\n{correction}\n"
        return prompt + "\nProduce the best answer. Do not fabricate evidence."

    @staticmethod
    def _build_critic_prompt(goal: str, answer: str, context: dict[str, Any]) -> str:
        schema = (
            '{"valid":bool,"confidence":number,"issues":['
            '{"code":str,"severity":"low|medium|high|critical","message":str,"correction":str|null}],'
            '"corrections":[str],"required_evidence":[str]}'
        )
        return (
            "You are ODYN's adversarial critic. Return ONLY valid JSON matching this schema: "
            + schema
            + f"\nGOAL:\n{goal}\nCANDIDATE:\n{answer}\nCONTEXT:\n"
            + json.dumps(context, ensure_ascii=False, default=str)
        )

    def _parse_critic(self, raw: str) -> CriticResult:
        try:
            payload = self._extract_json(raw)
            valid = payload["valid"]
            confidence = payload["confidence"]
            if type(valid) is not bool:
                raise ValueError("critic valid must be a JSON boolean")
            if type(confidence) not in {int, float} or not 0.0 <= confidence <= 1.0:
                raise ValueError("critic confidence must be a number between 0 and 1")
            for key in ("issues", "corrections", "required_evidence"):
                if not isinstance(payload.get(key, []), list):
                    raise ValueError(f"critic {key} must be an array")
            for key in ("corrections", "required_evidence"):
                if any(not isinstance(value, str) for value in payload.get(key, [])):
                    raise ValueError(f"critic {key} must contain only strings")
            for item in payload.get("issues", []):
                if not isinstance(item, dict):
                    raise ValueError("critic issues must contain objects")
                if any(not isinstance(item.get(key), str) for key in ("code", "severity", "message")):
                    raise ValueError("critic issue code, severity and message must be strings")
                if item.get("correction") is not None and not isinstance(item["correction"], str):
                    raise ValueError("critic issue correction must be a string or null")
            issues = tuple(
                CriticIssue(
                    code=str(item["code"]),
                    severity=str(item["severity"]),
                    message=str(item["message"]),
                    correction=item.get("correction"),
                )
                for item in payload.get("issues", [])
            )
            confidence = float(confidence)
            if valid and confidence < self.critic_confidence_threshold:
                valid = False
                issues += (
                    CriticIssue(
                        code="low_critic_confidence",
                        severity="medium",
                        message="Critic confidence is below the acceptance threshold.",
                    ),
                )
            return CriticResult(
                valid=valid,
                confidence=confidence,
                issues=issues,
                corrections=tuple(map(str, payload.get("corrections", []))),
                required_evidence=tuple(map(str, payload.get("required_evidence", []))),
                critic_model_id=self.critic.model_id,
                raw=payload,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return CriticResult(
                valid=False,
                confidence=0.0,
                issues=(
                    CriticIssue(
                        code="malformed_critic_result",
                        severity="critical",
                        message=f"Critic returned an invalid structured result: {exc}",
                    ),
                ),
                corrections=("Retry the critic with strict JSON output.",),
                critic_model_id=self.critic.model_id,
                raw={"raw": raw},
            )

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        if not isinstance(raw, str):
            raise TypeError("critic response must be text")
        raw = raw.strip()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("critic response does not contain JSON")
            value = json.loads(raw[start:end + 1])
        if not isinstance(value, dict):
            raise ValueError("critic JSON must be an object")
        return value
