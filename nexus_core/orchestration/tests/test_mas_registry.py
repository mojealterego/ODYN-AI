from __future__ import annotations

from nexus_core.orchestration.mas_registry import (
    CapabilitiesRegistry,
    CapabilityStatus,
)


def test_registry_exposes_declared_external_capabilities_without_claiming_connectivity() -> None:
    registry = CapabilitiesRegistry()

    capability = registry.external_tools["science_hypothesis"]

    assert capability.name == "science_hypothesis"
    assert capability.kind == "external_lab"
    assert capability.status is CapabilityStatus.DECLARED
    assert capability.url.startswith("https://")
    assert capability.available is False


def test_plugins_are_registered_and_retrievable() -> None:
    registry = CapabilitiesRegistry()
    plugin = object()

    registry.register_imperium_plugin("github_agent", plugin)

    assert registry.get_plugin("github_agent") is plugin


def test_sovereign_boot_reports_missing_strategic_capabilities() -> None:
    registry = CapabilitiesRegistry()

    report = registry.execute_sovereign_boot()

    assert report.healthy is False
    assert "github_agent" in report.missing_plugins
    assert "media_studio" in report.missing_plugins


def test_sovereign_boot_passes_when_required_plugins_are_registered() -> None:
    registry = CapabilitiesRegistry()
    registry.register_imperium_plugin("github_agent", object())
    registry.register_imperium_plugin("media_studio", object())

    report = registry.execute_sovereign_boot()

    assert report.healthy is True
    assert report.missing_plugins == ()


def test_plugin_registration_rejects_empty_names() -> None:
    registry = CapabilitiesRegistry()

    try:
        registry.register_imperium_plugin("", object())
    except ValueError as exc:
        assert "name" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
