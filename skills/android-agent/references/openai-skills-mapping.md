# OpenAI Skills Mapping

This document maps the OpenAI plugin Skills model onto Hermes Agent without duplicating runtime responsibilities.

| OpenAI concept | Hermes Android implementation |
|---|---|
| `SKILL.md` | `skills/*/SKILL.md` for procedural guidance; `DESCRIPTION.md` remains for Hermes skill discovery metadata where used |
| `references/` | Skill-local supporting documentation under `skills/android-agent/references/` |
| `assets/` | Optional skill-local templates/static resources |
| `scripts/` | Optional deterministic processing helpers |
| MCP server | Hermes MCP integration and configured external tool servers |
| Agent runtime | Hermes Agent runtime plus the Android `HermesRuntimeService` execution surface |
| User interface | Native Android application under `android/app` |
| Authentication | Existing Android/runtime authentication boundaries; secrets remain external to source |
| Validation | Gradle/Kotlin tests, Android tests, runtime smoke tests, and tool-result verification |

## Boundary

Do not put the complete agent runtime inside the Android UI layer. Android should provide the user interface, lifecycle-aware execution surface, secure local state, and narrowly scoped device capabilities. Agent planning/orchestration remains in the runtime.

## MCP boundary

MCP supplies live data and controlled actions. Skills specify when and how those tools should be used. A skill must not fabricate an MCP result and must not embed an MCP endpoint unless that endpoint is actually configured and authorized.

## Plugin packaging

The OpenAI plugin manifest format described in the external documentation is a submission/package concern. It should be introduced only when this repository has a real plugin MCP deployment and an authoritative server URL. Until then, this mapping is intentionally dependency-free rather than containing a placeholder endpoint.
