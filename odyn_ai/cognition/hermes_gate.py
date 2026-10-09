"""Bridge ODYN's critic-only review into the Hermes turn-gate contract."""
from __future__ import annotations

import json
from typing import Any

from .dual_model_engine import DualModelEngine
from .types import CriticIssue, CriticResult, DecisionAction, GateDecision


_READ_ONLY_TOOLS = frozenset({
    "clarify", "ha_get_state", "ha_list_entities", "ha_list_services",
    "read_file", "search_files", "session_search", "skill_view", "skills_list",
    "todo", "vision_analyze", "web_extract", "web_search", "browser_snapshot",
})

_TOOL_CAPABILITIES = {
    "browser_click": "browser_interaction",
    "browser_press": "browser_interaction",
    "browser_type": "browser_interaction",
    "cronjob": "scheduled_action",
    "delegate_task": "delegation",
    "execute_code": "command_execution",
    "ha_call_service": "external_side_effect",
    "memory": "persistent_memory",
    "mixture_of_agents": "delegation",
    "patch": "file_mutation",
    "rl_edit_config": "file_mutation",
    "rl_start_training": "external_side_effect",
    "rl_stop_training": "external_side_effect",
    "send_message": "external_messaging",
    "skill_manage": "skill_mutation",
    "terminal": "command_execution",
    "write_file": "file_mutation",
}


def _trusted_user_turns(messages: list[Any]) -> tuple[str, ...]:
    turns: list[str] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        if message.get("_flush_sentinel") or message.get("_camel_trust") == "system_control":
            continue
        content = message.get("_camel_operator_request") or message.get("content")
        if not isinstance(content, str):
            continue
        stripped = content.strip()
        if not stripped or stripped.lower().startswith("[system:"):
            continue
        turns.append(stripped)
    return tuple(turns[-3:])


def _untrusted_tool_sources(messages: list[Any]) -> tuple[str, ...]:
    call_sources: dict[str, str] = {}
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or ():
            if not isinstance(call, dict):
                continue
            function = call.get("function") or {}
            call_id = call.get("id")
            name = function.get("name") if isinstance(function, dict) else None
            if call_id and isinstance(name, str) and name:
                call_sources[str(call_id)] = name

    sources: list[str] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        name = message.get("name") or message.get("tool_name")
        if not name:
            name = call_sources.get(str(message.get("tool_call_id") or ""))
        if isinstance(name, str) and name and name != "clarify" and name not in sources:
            sources.append(name)
    return tuple(sources)


def _required_capabilities(calls: list[Any]) -> tuple[str, ...]:
    capabilities: list[str] = []
    for call in calls:
        if not isinstance(call, dict):
            capability = "external_side_effect"
        else:
            name = str(call.get("name") or "").strip()
            if not name or name in _READ_ONLY_TOOLS:
                continue
            capability = _TOOL_CAPABILITIES.get(name, "external_side_effect")
        if capability not in capabilities:
            capabilities.append(capability)
    return tuple(capabilities)


def _authorization_failure(
    base: CriticResult,
    *,
    code: str,
    message: str,
    critical: bool,
) -> CriticResult:
    return CriticResult(
        valid=False,
        confidence=0.0 if critical else base.confidence,
        issues=base.issues + (
            CriticIssue(
                code=code,
                severity="critical" if critical else "high",
                message=message,
                correction=None if critical else "Return to the trusted user goal and remove unauthorized side effects.",
            ),
        ),
        corrections=base.corrections + (() if critical else (
            "Remove tool capabilities that were not authorized by trusted user intent.",
        )),
        required_evidence=base.required_evidence,
        critic_model_id=base.critic_model_id,
        raw=dict(base.raw),
    )


class HermesDualModelGate:
    """Evaluate the exact Hermes candidate; never generate or dispatch tools."""

    def __init__(self, engine: DualModelEngine, *, max_attempts: int = 3) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.engine = engine
        self.max_attempts = max_attempts
        self._attempts: dict[str, int] = {}

    def evaluate_turn(self, candidate: Any, *, context: Any) -> GateDecision:
        messages = list(getattr(context, "messages", ()) or ())
        trusted_turns = _trusted_user_turns(messages)
        goal = trusted_turns[-1] if trusted_turns else ""
        task_key = str(getattr(context, "task_id", None) or getattr(context, "session_id", None) or "default")
        calls = list(getattr(candidate, "tool_calls", ()) or ())
        candidate_payload = {
            "content": getattr(candidate, "content", None),
            "tool_calls": calls,
            "finish_reason": getattr(candidate, "finish_reason", None),
        }
        result = self.engine.review_candidate(
            goal,
            json.dumps(candidate_payload, ensure_ascii=False, default=str),
            tool_calls=calls,
            context={"messages": messages, "task_id": task_key},
        )
        if result.required_evidence:
            return GateDecision(
                action=DecisionAction.RETRIEVE_EVIDENCE,
                reason="Critic requires additional evidence.",
                critic=result,
            )

        if result.valid and result.highest_severity == "low":
            capabilities = _required_capabilities(calls)
            untrusted_sources = _untrusted_tool_sources(messages)
            if capabilities and untrusted_sources:
                authorization = self.engine.authorize_capabilities(
                    goal,
                    capabilities,
                    trusted_user_turns=trusted_turns,
                )
                if not authorization.valid:
                    result = _authorization_failure(
                        result,
                        code="trusted_intent_authorization_failed",
                        message="Trusted-intent capability classification failed closed.",
                        critical=True,
                    )
                else:
                    allowed = set(authorization.allowed_capabilities)
                    missing = [cap for cap in capabilities if cap not in allowed]
                    if missing:
                        result = _authorization_failure(
                            result,
                            code="untrusted_capability_not_authorized",
                            message=(
                                "Untrusted tool data preceded a sensitive action and trusted "
                                "user intent did not authorize: " + ", ".join(missing)
                            ),
                            critical=False,
                        )
                    else:
                        self._attempts.pop(task_key, None)
                        return GateDecision(
                            action=DecisionAction.ACCEPT,
                            reason="Candidate and trusted-intent capability check accepted.",
                            critic=result,
                        )
            else:
                self._attempts.pop(task_key, None)
                return GateDecision(
                    action=DecisionAction.ACCEPT,
                    reason="Adversarial critic accepted the actual Hermes candidate.",
                    critic=result,
                )

        if result.highest_severity == "critical":
            self._attempts.pop(task_key, None)
            return GateDecision(
                action=DecisionAction.ESCALATE,
                reason="Critic identified a critical issue.",
                critic=result,
            )

        used = self._attempts.get(task_key, 0) + 1
        self._attempts[task_key] = used
        action = DecisionAction.CORRECT if used < self.max_attempts else DecisionAction.ESCALATE
        if action == DecisionAction.ESCALATE:
            self._attempts.pop(task_key, None)
        return GateDecision(
            action=action,
            reason="Candidate failed adversarial or trusted-intent review.",
            critic=result,
        )
