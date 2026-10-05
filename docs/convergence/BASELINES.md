# ODYN AI vNext convergence baselines

This file is machine-checked by `scripts/convergence/bootstrap_vnext.sh`.

- ODYN stable branch: `codex/termux-five-goals`
- ODYN baseline SHA: `df56169a5f472ca4156e8f8a77a75b89baa93733`
- Snapshot branch: `baseline/odyn-pre-vnext`
- Integration branch: `integration/odyn-vnext`
- Historical common ancestor with Hermes: `6fa1701bd3d9dd41923adc30fe55ec3f02c693ce`
- Previous imported upstream snapshot in this repository: `5e1005e46d3b919daa1336b4398d0b5430a4fd03`
- Upstream repository: `NousResearch/hermes-agent`
- Upstream vNext pin at start of reconstruction: `93c9360a8da592cee43e8895403e91c7a920b0ce`

## Non-negotiable invariants

1. The repository default branch is not changed during vNext construction.
2. `codex/termux-five-goals` remains untouched until the final cutover gate passes.
3. vNext is reconstructed from the pinned current upstream tree; it is not produced by a giant merge of the divergent histories.
4. ODYN-owned cognition, trust-boundary code, Android/mobile runtime, local inference and device capabilities are preserved or explicitly classified before any removal.
5. Reasoning is not authorization. Candidate output is not permission. Retrieved/tool data is untrusted input. Approval is scoped and single-use.
6. Rebranding and Polish localization must preserve compatibility aliases during migration.
7. No self-evolution path may directly push to the production/default branch.

The bootstrap job generates the exhaustive path manifests and records every reconstruction conflict under `docs/convergence/`.
