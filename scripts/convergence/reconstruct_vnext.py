from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.convergence.reconstruct_policy import MigrationClass, classify_path


@dataclass
class PortRecord:
    path: str
    classification: str
    action: str
    source_base: str
    source_head: str
    conflict: bool = False
    detail: str = ""


def _git(*args: str, check: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )


def _blob(commit: str, path: str) -> bytes | None:
    probe = _git("cat-file", "-e", f"{commit}:{path}", check=False)
    if probe.returncode != 0:
        return None
    return _git("show", f"{commit}:{path}", text=False).stdout


def _mode(commit: str, path: str) -> str | None:
    result = _git("ls-tree", commit, "--", path, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.split(None, 1)[0]


def _changed_paths(base: str, head: str) -> list[tuple[str, str]]:
    raw = _git(
        "diff",
        "--name-status",
        "--no-renames",
        "-z",
        base,
        head,
        text=False,
    ).stdout
    fields = raw.split(b"\0")
    out: list[tuple[str, str]] = []
    i = 0
    while i + 1 < len(fields) and fields[i]:
        status = fields[i].decode("ascii", "replace")
        path = fields[i + 1].decode("utf-8", "surrogateescape")
        out.append((status[:1], path))
        i += 2
    return out


def _write(path: str, data: bytes, mode: str | None) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    if mode == "100755":
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    _git("add", "-f", "--", path)


def _remove(path: str) -> None:
    target = Path(path)
    if target.exists() or target.is_symlink():
        target.unlink()
    _git("add", "-A", "--", path)


def _is_text(data: bytes) -> bool:
    if b"\0" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _merge_text(source: bytes, base: bytes, current: bytes) -> tuple[bytes, bool, str]:
    with tempfile.TemporaryDirectory(prefix="odyn-port-") as tmp:
        root = Path(tmp)
        source_file = root / "source"
        base_file = root / "base"
        current_file = root / "current"
        source_file.write_bytes(source)
        base_file.write_bytes(base)
        current_file.write_bytes(current)
        proc = subprocess.run(
            [
                "git",
                "merge-file",
                "-p",
                "--diff3",
                str(source_file),
                str(base_file),
                str(current_file),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode == 0:
            return proc.stdout, False, "clean three-way merge"
        return source, True, f"three-way conflict ({proc.returncode}); preserved ODYN/source variant"


def apply_overlay(base: str, source: str, label: str) -> list[PortRecord]:
    records: list[PortRecord] = []
    for status, path in _changed_paths(base, source):
        classification = classify_path(path)
        if classification not in {MigrationClass.KEEP, MigrationClass.PORT}:
            records.append(
                PortRecord(
                    path=path,
                    classification=classification.value,
                    action="deferred",
                    source_base=base,
                    source_head=source,
                    detail=f"{label}: upstream-owned/rewrite surface left on current upstream",
                )
            )
            continue

        source_blob = _blob(source, path)
        base_blob = _blob(base, path)
        current_path = Path(path)
        current_blob = current_path.read_bytes() if current_path.exists() else None

        if status == "D" or source_blob is None:
            if current_blob is None:
                action = "already-absent"
                detail = f"{label}: source deletion already reflected"
                conflict = False
            elif base_blob is not None and current_blob == base_blob:
                _remove(path)
                action = "deleted"
                detail = f"{label}: applied source deletion; current matched base"
                conflict = False
            else:
                action = "kept-current"
                detail = f"{label}: deletion conflicts with newer current content"
                conflict = True
            records.append(
                PortRecord(path, classification.value, action, base, source, conflict, detail)
            )
            continue

        mode = _mode(source, path)
        if current_blob is None:
            _write(path, source_blob, mode)
            records.append(
                PortRecord(path, classification.value, "added", base, source, False, f"{label}: source-only file")
            )
            continue

        if current_blob == source_blob:
            records.append(
                PortRecord(path, classification.value, "identical", base, source, False, f"{label}: already identical")
            )
            continue

        if base_blob is None:
            _write(path, source_blob, mode)
            records.append(
                PortRecord(
                    path,
                    classification.value,
                    "source-wins",
                    base,
                    source,
                    True,
                    f"{label}: independently-added path collision; preserved ODYN/source variant",
                )
            )
            continue

        if current_blob == base_blob:
            _write(path, source_blob, mode)
            records.append(
                PortRecord(path, classification.value, "ported", base, source, False, f"{label}: current matched base")
            )
            continue

        if source_blob == base_blob:
            records.append(
                PortRecord(path, classification.value, "kept-current", base, source, False, f"{label}: source unchanged from base")
            )
            continue

        if _is_text(source_blob) and _is_text(base_blob) and _is_text(current_blob):
            merged, conflict, detail = _merge_text(source_blob, base_blob, current_blob)
            _write(path, merged, mode)
            records.append(
                PortRecord(path, classification.value, "merged" if not conflict else "source-wins", base, source, conflict, f"{label}: {detail}")
            )
        else:
            _write(path, source_blob, mode)
            records.append(
                PortRecord(
                    path,
                    classification.value,
                    "source-wins",
                    base,
                    source,
                    True,
                    f"{label}: binary/non-UTF8 concurrent change; preserved ODYN/source variant",
                )
            )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconstruct ODYN vNext on a current upstream working tree.")
    parser.add_argument("--odyn-base", required=True)
    parser.add_argument("--common-base", required=True)
    parser.add_argument("--review-base", required=True)
    parser.add_argument("--review-head", required=True)
    parser.add_argument("--trust-head", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    records: list[PortRecord] = []
    records.extend(apply_overlay(args.common_base, args.odyn_base, "ODYN stable"))
    records.extend(apply_overlay(args.review_base, args.review_head, "bounded cognitive review"))
    records.extend(apply_overlay(args.odyn_base, args.trust_head, "ODYN trust boundary"))

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "odyn_base": args.odyn_base,
        "common_base": args.common_base,
        "review_base": args.review_base,
        "review_head": args.review_head,
        "trust_head": args.trust_head,
        "records": [asdict(item) for item in records],
        "conflicts": [asdict(item) for item in records if item.conflict],
        "counts": {
            "total": len(records),
            "ported_or_merged": sum(item.action in {"added", "ported", "merged", "source-wins", "deleted"} for item in records),
            "deferred": sum(item.action == "deferred" for item in records),
            "conflicts": sum(item.conflict for item in records),
        },
    }
    report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _git("add", "--", str(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
