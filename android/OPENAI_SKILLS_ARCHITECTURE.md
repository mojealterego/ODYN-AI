# OpenAI Skills Architecture for Hermes Android

## Status

This is the Android integration contract for OpenAI Skills. The current OpenAI Skills API treats a skill as a versioned bundle: skills can be created and listed, immutable versions can be created, a default version can be selected, and skill content can be downloaded as a bundle.

Hermes therefore treats `SKILL.md` as the portable procedural entry point while keeping version identity, content digest, and execution policy explicit. A local Hermes skill and an OpenAI-hosted skill must not silently diverge.

## Runtime topology

```text
Android UI
   |
   v
Android agent facade
   |
   +--> local device capability adapters
   |
   +--> remote Hermes API / Responses-compatible provider
   |
   +--> on-device model backends
   |
   v
Hermes Agent runtime
   |
   +--> Skill Registry
   |      |
   |      +--> local SKILL.md bundles
   |      +--> version/digest metadata
   |      +--> deterministic lexical selection
   |      +--> validation/security gates
   |
   +--> instruction composer
   |
   +--> Tool Router
          |
          +--> built-in tools
          +--> configured MCP tools
          +--> Android capability adapters
```

## Responsibilities

### Android

- Present chat, execution state, tool activity, errors, and recovery state.
- Manage Android lifecycle and foreground execution where required.
- Request and enforce OS permissions.
- Expose narrow device capabilities through audited adapters.
- Store only required local state and credentials using Android-secure storage.
- Never embed provider API keys in the APK.

### Hermes runtime

- Discover, validate, cache, and select skills.
- Preserve skill name/version/content digest for observability and reproducibility.
- Perform planning and tool orchestration.
- Maintain conversation/session state.
- Enforce tool and command policies.
- Execute configured MCP integrations where supported by the runtime.
- Return verifiable results to the Android client.

### Skills

A Skill is procedural guidance, not an execution channel. Skill content can influence model behavior, so the runtime must treat skill files as trusted-but-audited instructions and must make instruction priority explicit: user instructions remain higher priority than skill guidance.

The implementation therefore enforces:

- bounded file sizes;
- safe lowercase skill identifiers;
- root containment/path traversal protection;
- deterministic discovery order;
- SHA-256 content identity;
- bounded selection count;
- no implicit script execution;
- no fabricated tool/MCP results;
- secret-pattern checks in CI;
- provenance comments when skill instructions are composed.

### MCP

MCP is the controlled execution boundary for external capabilities. A skill may describe when an MCP tool should be selected, but the skill does not replace the MCP server or manufacture its results.

The current embedded Android path documents external MCP stdio/SSE/HTTP execution as unavailable. Do not enable it merely by adding a skill; it requires a lifecycle-safe Android MCP transport implementation and explicit validation.

## Skill bundle contract

```text
skills/<name>/
├── SKILL.md
├── DESCRIPTION.md          # optional Hermes discovery metadata
├── references/              # optional
├── assets/                  # optional
└── scripts/                 # optional; never implicitly executed
```

`SKILL.md` must define trigger conditions, input assumptions, workflow, tool boundaries, security constraints, validation, failure behavior, output expectations, and stop conditions.

For OpenAI-hosted deployment, preserve the same logical bundle and version identity. OpenAI exposes immutable Skill versions and a default-version pointer, so deployments should pin or record the selected version instead of assuming that `latest` is immutable.

## Validation gates

A feature is not considered integrated merely because files exist. The minimum evidence for a production change is:

1. Skill discovery succeeds.
2. Metadata is deterministic and contains a content digest.
3. The intended workflow activates for a representative direct request.
4. An indirect equivalent request activates the same workflow when appropriate.
5. Incomplete input follows the defined follow-up path.
6. Unsupported operations do not activate the skill or do not execute an unavailable tool.
7. Android build/lint/tests pass for affected code.
8. Device lifecycle behavior is validated for long-running work.
9. Secrets are absent from source, logs, packaged resources, and test fixtures.
10. OpenAI-hosted deployment, when used, records skill ID + immutable version + local content digest.

## CI gates

`skills-quality.yml` validates the Android Agent skill and runs the dependency-free Python unit tests. The validator is intentionally scoped to the production Android skill first; existing legacy skills are not silently rewritten or declared compliant by association.

## Current limitation

The existing Android application already supports embedded local and remote model paths, but its documented embedded runtime does not execute external MCP stdio/SSE/HTTP sessions. The implementation therefore builds the real Skill discovery/selection/security layer without falsely claiming live external MCP execution. The next transport layer must be added only after its Android lifecycle, cancellation, permission, and security model are implemented and tested.
