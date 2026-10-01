"""Capability registry and guarded MAS bootstrap for Nexus Core.

External laboratories are represented as *declared capabilities*. A URL alone
never means that an API is authenticated, reachable, or supported. Provider
adapters must explicitly mark a capability as available after verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable


class CapabilityStatus(StrEnum):
    DECLARED = "declared"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    DISABLED = "disabled"


@dataclass(frozen=True)
class ExternalCapability:
    name: str
    url: str
    kind: str
    status: CapabilityStatus = CapabilityStatus.DECLARED
    available: bool = False
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class SovereignBootReport:
    healthy: bool
    missing_plugins: tuple[str, ...]
    warnings: tuple[str, ...]
    checked_capabilities: tuple[str, ...]


class CapabilitiesRegistry:
    """Central MAS capability registry.

    The registry describes what the system knows how to use. It does not turn
    closed/beta web applications into unofficial APIs and does not execute
    arbitrary plugin code during bootstrap.
    """

    REQUIRED_PLUGINS = ("github_agent", "media_studio")

    def __init__(
        self,
        *,
        capability_probe: Callable[[ExternalCapability], bool] | None = None,
    ) -> None:
        self.loaded_plugins: dict[str, object] = {}
        self.external_tools = self._initialize_external_labs()
        self._capability_probe = capability_probe

    @staticmethod
    def _initialize_external_labs() -> dict[str, ExternalCapability]:
        declarations = {
            "image_fx": "https://labs.google/tools/imagefx",
            "text_fx": "https://labs.google/tools/textfx",
            "project_genie": "https://labs.google/projectgenie",
            "science_computational": "https://labs.google/science/#computational-discovery",
            "science_hypothesis": "https://labs.google/science/#hypothesis-generation",
            "science_literature": "https://labs.google/science/#literature-insights",
            "eloquent_dev": "https://ai.google.dev/edge/eloquent",
            "vantage_research": "https://research.google.com/p/vantage",
            "opal_landing": "https://opal.google/landing/?source=labs",
            "jules_dev": "https://jules.google/",
            "stax_with_google": "https://stax.withgoogle.com/",
            "stitch_with_google": "https://stitch.withgoogle.com/",
            "flow_music": "https://www.flowmusic.app/",
        }
        return {
            name: ExternalCapability(
                name=name,
                url=url,
                kind="external_lab",
            )
            for name, url in declarations.items()
        }

    def register_imperium_plugin(self, name: str, instance: object) -> None:
        if not name or not name.strip():
            raise ValueError("plugin name jest wymagane.")
        self.loaded_plugins[name] = instance

    def get_plugin(self, name: str) -> object | None:
        return self.loaded_plugins.get(name)

    def mark_capability_available(
        self,
        name: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ExternalCapability:
        capability = self.external_tools.get(name)
        if capability is None:
            raise KeyError(f"Nieznana capability: {name}")

        updated = ExternalCapability(
            name=capability.name,
            url=capability.url,
            kind=capability.kind,
            status=CapabilityStatus.AVAILABLE,
            available=True,
            metadata=metadata,
        )
        self.external_tools[name] = updated
        return updated

    def execute_sovereign_boot(self) -> SovereignBootReport:
        """Validate required local plugins before declaring the MAS healthy."""
        missing = tuple(
            name for name in self.REQUIRED_PLUGINS
            if name not in self.loaded_plugins
        )
        warnings = tuple(
            f"Capability {name} is declared but not connected."
            for name, capability in self.external_tools.items()
            if not capability.available
        )

        if self._capability_probe is not None:
            for name, capability in tuple(self.external_tools.items()):
                try:
                    if self._capability_probe(capability):
                        self.mark_capability_available(name)
                except Exception as exc:
                    warnings += (f"Capability {name} probe failed: {exc}",)

        # Recompute warnings after optional probes.
        warnings = tuple(
            f"Capability {name} is declared but not connected."
            for name, capability in self.external_tools.items()
            if not capability.available
        )

        return SovereignBootReport(
            healthy=not missing,
            missing_plugins=missing,
            warnings=warnings,
            checked_capabilities=tuple(self.external_tools),
        )
