"""Offline, fail-closed gate for a proposed Hermes Android Termux APT install.

A read-only compatibility check, not a package installer, signature verifier,
Android device probe, or substitute for the current official upstream docs.
Readiness attestations must come from outside the agent-proposed plan.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping

OFFICIAL_DOC = "https://hermes-agent.nousresearch.com/docs/getting-started/termux"
OFFICIAL_APT = "https://hermes-assets.nousresearch.com/releases/termux/stable"
OFFICIAL_FINGERPRINT = "C572B5FDD1A29CCFA9A912B6840B0848E139156D"
PREFIX = "/data/data/com.termux/files/usr"


@dataclass(frozen=True)
class UpstreamEvidence:
    """Evidence independently verified by operator outside generated install plan."""
    status: str
    checked_at: datetime
    source: str = OFFICIAL_DOC


@dataclass(frozen=True)
class InstallReview:
    allowed: bool
    reasons: tuple[str, ...]


def review_hermes_termux_install(
    plan: dict,
    *,
    trusted_upstream: Mapping[str, UpstreamEvidence],
    now: datetime,
) -> InstallReview:
    """Require a known-working freshly verified source and signed APT scope.

    This function NEVER downloads packages or authenticates a vendor account.
    """
    if not isinstance(plan, dict):
        raise TypeError("plan must be a dictionary")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    errors = []
    if plan.get("target") != "android-termux":
        errors.append("wrong_platform")
    if plan.get("architecture") != "aarch64":
        errors.append("unsupported_architecture")
    if plan.get("termux_prefix") != PREFIX:
        errors.append("unsupported_termux_prefix")
    sdk = plan.get("android_api")
    if type(sdk) is not int or sdk < 24:
        errors.append("unsupported_android_api")
    if plan.get("install_mode") != "signed_apt":
        errors.append("installer_must_be_signed_apt")
    if plan.get("repository_url") != OFFICIAL_APT:
        errors.append("untrusted_repository")
    if plan.get("key_fingerprint", "").replace(" ", "").upper() != OFFICIAL_FINGERPRINT:
        errors.append("unverified_repository_signing_key")
    if plan.get("signature_check_enabled") is not True:
        errors.append("signature_check_not_enabled")
    if plan.get("allows_unverified_fallback") is not False:
        errors.append("unverified_fallback_forbidden")
    if plan.get("command") != "pkg install hermes-agent":
        errors.append("not_package_manager_managed")
    if plan.get("owner_approved") is not True:
        errors.append("no_explicit_owner_approval")
    key = plan.get("release_evidence_id")
    evidence = trusted_upstream.get(key) if isinstance(key, str) else None
    if evidence is None or evidence.source != OFFICIAL_DOC:
        errors.append("missing_independent_official_release_evidence")
    else:
        if evidence.status != "WORKING":
            errors.append("upstream_reports_broken_or_unknown")
        ts = evidence.checked_at
        if ts.tzinfo is None or ts > now or now - ts > timedelta(hours=72):
            errors.append("stale_release_evidence")
    return InstallReview(not errors, tuple(dict.fromkeys(errors)))
