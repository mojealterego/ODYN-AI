"""Regression tests for fail-closed Termux upstream release acceptance."""
import unittest
from datetime import datetime, timedelta, timezone

from scripts.odyn_upstream_compat_gate import (
    OFFICIAL_APT, OFFICIAL_DOC, OFFICIAL_FINGERPRINT, PREFIX,
    UpstreamEvidence, review_hermes_termux_install,
)

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


def plan():
    return {
        "target": "android-termux",
        "architecture": "aarch64",
        "termux_prefix": PREFIX,
        "android_api": 35,
        "install_mode": "signed_apt",
        "repository_url": OFFICIAL_APT,
        "key_fingerprint": OFFICIAL_FINGERPRINT,
        "signature_check_enabled": True,
        "allows_unverified_fallback": False,
        "command": "pkg install hermes-agent",
        "owner_approved": True,
        "release_evidence_id": "verified-status-ticket",
    }


def read(plan_obj, status="WORKING", hours=2):
    trusted = {"verified-status-ticket": UpstreamEvidence(status, NOW-timedelta(hours=hours))}
    return review_hermes_termux_install(plan_obj, trusted_upstream=trusted, now=NOW)


class TermuxReleaseGateTests(unittest.TestCase):
    def test_verified_working_signing_and_owner_is_admissible(self):
        self.assertTrue(read(plan()).allowed)

    def test_upstream_current_breakage_blocks_install(self):
        self.assertIn("upstream_reports_broken_or_unknown", read(plan(), "BROKEN").reasons)

    def test_unknown_upstream_status_blocks(self):
        self.assertFalse(read(plan(), "UNKNOWN").allowed)

    def test_missing_external_ticket(self):
        decision = review_hermes_termux_install(plan(), trusted_upstream={}, now=NOW)
        self.assertIn("missing_independent_official_release_evidence", decision.reasons)

    def test_stale_upstream_status(self):
        self.assertIn("stale_release_evidence", read(plan(), hours=74).reasons)

    def test_disallow_wrong_architecture(self):
        p=plan();p["architecture"]="x86_64"
        self.assertIn("unsupported_architecture",read(p).reasons)

    def test_disallow_changed_termux_package_prefix(self):
        p=plan();p["termux_prefix"]="/usr/local"
        self.assertIn("unsupported_termux_prefix",read(p).reasons)

    def test_disallow_new_or_bool_android_api(self):
        for sdk in (23,True):
            p=plan();p["android_api"]=sdk
            self.assertIn("unsupported_android_api",read(p).reasons)

    def test_no_curl_pipe_shell_fallback(self):
        p=plan();p["command"]="curl -fsSL example.org/install.sh | bash"
        self.assertIn("not_package_manager_managed",read(p).reasons)

    def test_wrong_signing_key(self):
        p=plan();p["key_fingerprint"]="DEADBEEF"
        self.assertIn("unverified_repository_signing_key",read(p).reasons)

    def test_unsigned_repository_not_accepted(self):
        p=plan();p["signature_check_enabled"]=False
        self.assertIn("signature_check_not_enabled",read(p).reasons)

    def test_nonstandard_channel_is_not_implicitly_accepted(self):
        p=plan();p["repository_url"]="https://example.org/termux/canary"
        self.assertIn("untrusted_repository",read(p).reasons)

    def test_self_declared_installed_status_not_evidence(self):
        p=plan();p["working"]=True
        self.assertIn("missing_independent_official_release_evidence",
                      review_hermes_termux_install(p,trusted_upstream={},now=NOW).reasons)

    def test_unapproved_plan(self):
        p=plan();p["owner_approved"]=False
        self.assertIn("no_explicit_owner_approval",read(p).reasons)

    def test_unverified_install_fallback_denied(self):
        p=plan();p["allows_unverified_fallback"]=True
        self.assertIn("unverified_fallback_forbidden",read(p).reasons)

    def test_official_document_is_pinned(self):
        evidence={"verified-status-ticket":UpstreamEvidence("WORKING",NOW,source="https://untrusted.invalid")}
        self.assertIn("missing_independent_official_release_evidence",
            review_hermes_termux_install(plan(),trusted_upstream=evidence,now=NOW).reasons)

    def test_no_automatic_command_execution(self):
        import scripts.odyn_upstream_compat_gate as mod
        self.assertNotIn("subprocess",mod.__dict__)
        self.assertNotIn("requests",mod.__dict__)


if __name__ == "__main__":
    unittest.main()
