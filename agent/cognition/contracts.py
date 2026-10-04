"""Neutral contracts for pre-dispatch candidate review.

This module is intentionally transport-, provider-, and product-name agnostic.
It defines the narrow boundary between Hermes turn generation and future
cognitive review implementations. No tool authorization or execution lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol


class ReviewAction(str, Enum):
    """Possible outcomes of one candidate review round."""

    ACCEPT = "accept"
    CORRECT = "correct"
    RETRY = "retry"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class ReviewDecision:
    """Structured result returned by a candidate reviewer."""

    action: ReviewAction
    confidence: float
    reason: str
    issues: tuple[str, ...] = ()
    corrections: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("review confidence must be between 0 and 1")


@dataclass(frozen=True)
class CandidateSnapshot:
    """Read-only snapshot of one generated assistant candidate."""

    content: str | None
    tool_calls: tuple[Mapping[str, Any], ...] = ()
    finish_reason: str | None = None


@dataclass(frozen=True)
class ReviewContext:
    """Read-only context supplied to a candidate reviewer."""

    task_id: str | None = None
    session_id: str | None = None
    messages: tuple[Mapping[str, Any], ...] = ()


class CandidateReviewer(Protocol):
    """Minimal interface implemented by candidate review strategies."""

    def review(
        self,
        candidate: CandidateSnapshot,
        *,
        context: ReviewContext,
    ) -> ReviewDecision:
        """Return one structured review decision without executing tools."""
        ...
