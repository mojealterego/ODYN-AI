"""MAS capability registry tests."""

from __future__ import annotations

from nexus_core.orchestration.mas_registry import CapabilitiesRegistry


def test_probe_can_promote_only_verified_capability() -> None:
    registry = CapabilitiesRegistry(
        capability_probe=lambda capability: capability.name == "science_hypothesis"
    )

    report = registry.execute_sovereign_boot()

    assert registry.external_tools["science_hypothesis"].available is True
    assert registry.external_tools["image_fx"].available is False
    assert "science_hypothesis" in report.checked_capabilities


def test_boot_does_not_execute_registered_plugins() -> None:
    calls: list[str] = []

    class Plugin:
        def __call__(self) -> None:
            calls.append("executed")

    registry = CapabilitiesRegistry()
    registry.register_imperium_plugin("github_agent", Plugin())
    registry.register_imperium_plugin("media_studio", object())

    report = registry.execute_sovereign_boot()

    assert report.healthy is True
    assert calls == []
