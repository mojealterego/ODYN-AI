from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

from scripts.convergence.reconstruct_policy import classify_path


NOUS_MATRIX = {
    "A_DIRECT": [
        "hermes-agent","hermes-agent-self-evolution","hermes-paperclip-adapter",
        "hermes-plugin-claude-subscription-directsdk","hermes-plugin-backsearch",
        "kanban-video-pipeline","agent-governance-toolkit","hermes-telegram-business",
        "hermes-example-plugins","NemoClaw","hermes-memory-wiki","hermes-compression-eval",
        "OpenShell","OpenShell-Community","hermes-plugin-snyk","hermes-plugin-sprites",
        "hermes-plugin-honcho","hermes-toolperf-evals","hermes-plugin-blender",
        "hermes-plugin-touchdesigner","hermes-nvidia","hermes-plugin-supermemory",
        "hermes-plugin-openviking","hermes-desktop-accent-picker","hermes-homeassistant",
        "hermes-e2e-evidence","hermes-plugin-holographic","hermes-plugin-mem0",
        "hermes-plugin-byterover","hermes-plugin-retaindb",
    ],
    "B_RESEARCH_INFERENCE": [
        "atropos","autoreason","Open-Reasoning-Tasks","nomos","pokemon-agent","nousflash-agents",
        "tinker-atropos","neural-steering","Gym","RL","Nemotron","tinker-nemogym","vllm",
        "nous-llama.cpp","Megatron-LM","Megatron-Bridge","ollama","speculators","llama.cpp",
        "Automodel","litellm","lm-eval-harness","lighteval","TextArena","openai-evals",
        "lm-evaluation-harness-pretraining",
    ],
    "C_SELECTIVE_INFRA": [
        "DisTrO","Hermes-Function-Calling","Obsidian","llm-abliteration","finetuning-subnet",
        "StripedHyenaTrainer","smc-inference-server","torchtitan","local_generative_agents",
        "wandb-rs","forge-api-demo","llm-chain","harbor-fork","cline","axolotl-func-calling",
        "nanotron","funcchain","kaida","datatrove","iroh","solana-flake","ink","DeepEP",
        "jedi","logfire-rust","tch-rs","kaida-gencritique","yellowstone-grpc","infini-attention",
        "iroh-blobs","hf-hub","harbor","iroh-gossip","iroh-fake-store","Liger-Kernel","wterm",
        "pico","scaling-transformer","curve25519-dalek","nccl-tests","misaki","torchtitan_tests",
        "LeastLoadedEP","image-size",
    ],
    "D_OUT_OF_CORE": [
        "autonovel","Hermes-Bot-Mode","huskyholdem-bench","storywriter","storywriter-frontend",
        "creative-writing-bench","yhack","longform-writing-bench","forge-feedback","eqbench3",
    ],
}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, stdout=subprocess.PIPE, text=True).stdout


def tree_paths(commit: str) -> set[str]:
    return {line for line in git("ls-tree", "-r", "--name-only", commit).splitlines() if line}


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--odyn", required=True)
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--previous-upstream", required=True)
    parser.add_argument("--out", default="docs/convergence")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    odyn = tree_paths(args.odyn)
    upstream = tree_paths(args.upstream)

    odyn_unique = sorted(odyn - upstream)
    upstream_new = sorted(upstream - odyn)

    classified = [
        {"path": path, "classification": classify_path(path).value}
        for path in odyn_unique
    ]
    counts = Counter(item["classification"] for item in classified)
    write_json(
        out / "ODYN_UNIQUE_FILES.json",
        {
            "schema_version": 1,
            "odyn_sha": args.odyn,
            "upstream_sha": args.upstream,
            "count": len(classified),
            "classification_counts": dict(sorted(counts.items())),
            "files": classified,
        },
    )
    write_json(
        out / "UPSTREAM_NEW_FILES.json",
        {
            "schema_version": 1,
            "odyn_sha": args.odyn,
            "upstream_sha": args.upstream,
            "count": len(upstream_new),
            "files": upstream_new,
        },
    )

    stat = git("diff", "--stat", args.previous_upstream, args.upstream)
    (out / "UPSTREAM_DELTA.md").write_text(
        "# Upstream delta\n\n"
        f"Previous imported upstream: `{args.previous_upstream}`\n\n"
        f"Pinned vNext upstream: `{args.upstream}`\n\n"
        "## Diffstat\n\n```text\n" + stat + "```\n",
        encoding="utf-8",
    )

    lines = [
        "# NousResearch ecosystem matrix",
        "",
        "This matrix is an integration boundary, not a dependency list.",
        "",
    ]
    for category, repos in NOUS_MATRIX.items():
        lines.extend([f"## {category} ({len(repos)})", "", ", ".join(f"`{name}`" for name in repos), ""])
    lines.append(f"Total classified repositories: **{sum(map(len, NOUS_MATRIX.values()))}**")
    (out / "NOUS_ECOSYSTEM_MATRIX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
