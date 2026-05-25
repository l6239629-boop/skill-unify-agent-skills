#!/usr/bin/env python3
"""Create one central Desktop Skill library and point agent skills dirs to it."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_SHARED_DIR = "~/Desktop/SharedSkills"
SELF_SKILL_NAME = "unify-agent-skills"

DEFAULT_TARGETS = {
    "codex": "~/.codex/skills",
    "claude-code": "~/.claude/skills",
    "cursor": "~/.cursor/skills",
    "gemini-cli": "~/.gemini/skills",
    "openclaw": "~/.openclaw/skills",
    "opencode": "~/.opencode/skills",
    "qoder": "~/.qoder/skills",
    "qwen-code": "~/.qwen/skills",
    "trae": "~/.trae/skills",
}


@dataclass(frozen=True)
class Target:
    name: str
    path: Path
    reason: str


def expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path))).absolute()


def parse_target(value: str) -> Target:
    if "=" not in value:
        raise argparse.ArgumentTypeError("targets must use name=/absolute/or/~/path")
    name, raw_path = value.split("=", 1)
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError("target name cannot be empty")
    return Target(name=name, path=expand(raw_path.strip()), reason="explicit")


def backup_path(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.with_name(f"{path.name}.backup-{stamp}")


def same_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except FileNotFoundError:
        return False


def current_skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def discover_targets(explicit: list[Target], only_targets: bool) -> list[Target]:
    targets: dict[Path, Target] = {}
    if not only_targets:
        for name, raw_path in DEFAULT_TARGETS.items():
            path = expand(raw_path)
            if path.exists() or path.parent.exists():
                reason = "existing directory" if path.exists() else "existing parent"
                targets[path] = Target(name=name, path=path, reason=reason)
    for target in explicit:
        targets[target.path] = target
    return sorted(targets.values(), key=lambda item: (item.name, str(item.path)))


def skill_entries(shared_dir: Path) -> list[Path]:
    if not shared_dir.exists():
        return []
    return sorted(
        item
        for item in shared_dir.iterdir()
        if (
            item.is_dir()
            and not item.name.startswith(".")
            and ".backup-" not in item.name
            and (item / "SKILL.md").exists()
        )
    )


def copy_skill_tree(source: Path, dest: Path) -> None:
    shutil.copytree(
        source,
        dest,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def launch_manager(shared_dir: Path, force: bool) -> str:
    manager_dir = shared_dir / ".skill-manager"
    marker = manager_dir / "manager-opened.json"
    if marker.exists() and not force:
        return "manager already opened before"

    script = shared_dir / SELF_SKILL_NAME / "scripts" / "skill_manager_server.py"
    if not script.exists():
        return f"manager server missing at {script}"

    manager_dir.mkdir(parents=True, exist_ok=True)
    log_path = manager_dir / "server-launch.log"
    with log_path.open("a", encoding="utf-8") as log:
        subprocess.Popen(
            [sys.executable, str(script), "--shared-dir", str(shared_dir), "--port", "0", "--open"],
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    marker.write_text(
        jsonish({"opened_at": datetime.now().isoformat(timespec="seconds"), "log": str(log_path)}),
        encoding="utf-8",
    )
    return f"manager launch requested; log={log_path}"


def jsonish(data: dict[str, str]) -> str:
    lines = ["{"]
    for index, (key, value) in enumerate(data.items()):
        comma = "," if index < len(data) - 1 else ""
        lines.append(f'  "{key}": "{value}"{comma}')
    lines.append("}")
    return "\n".join(lines)


def ensure_shared_dir(shared_dir: Path, apply: bool) -> str:
    if shared_dir.exists():
        return "exists"
    if apply:
        shared_dir.mkdir(parents=True, exist_ok=True)
        return "created"
    return "would-create"


def ensure_self_skill(shared_dir: Path, apply: bool, refresh: bool) -> str:
    source = current_skill_root()
    dest = shared_dir / SELF_SKILL_NAME

    if same_path(source, dest):
        return "already-running-from-shared-library"

    if dest.exists() or dest.is_symlink():
        if refresh:
            if apply:
                moved = backup_path(dest)
                shutil.move(str(dest), str(moved))
                copy_skill_tree(source, dest)
                return f"refreshed-from-current-copy; backup={moved}"
            return "would-refresh-from-current-copy"
        return "existing-shared-copy-will-be-used"

    if apply:
        copy_skill_tree(source, dest)
        return "installed-current-skill-into-shared-library"
    return "would-install-current-skill-into-shared-library"


def migrate_existing_entries(target: Path, shared_dir: Path, apply: bool) -> list[str]:
    messages: list[str] = []
    if not target.exists() or target.is_symlink() or not target.is_dir():
        return messages

    for child in sorted(target.iterdir(), key=lambda item: item.name):
        if child.name in {".DS_Store"}:
            continue
        dest = shared_dir / child.name
        if same_path(child, dest):
            messages.append(f"{child.name}: already central")
        elif dest.exists() or dest.is_symlink():
            messages.append(f"{child.name}: kept original in backup because central copy exists")
        elif apply:
            shutil.move(str(child), str(dest))
            messages.append(f"{child.name}: moved into central library")
        else:
            messages.append(f"{child.name}: would move into central library")
    return messages


def apply_target_symlink(target: Target, shared_dir: Path, apply: bool, keep_backup: bool) -> list[str]:
    messages: list[str] = []
    path = target.path
    parent = path.parent

    if path.is_symlink() and same_path(path, shared_dir):
        return ["skills directory already points to central library"]

    if apply:
        parent.mkdir(parents=True, exist_ok=True)

    messages.extend(migrate_existing_entries(path, shared_dir, apply))

    if path.exists() or path.is_symlink():
        if apply:
            if path.is_symlink():
                if keep_backup:
                    moved = backup_path(path)
                    shutil.move(str(path), str(moved))
                    messages.append(f"previous symlink backed up to {moved}")
                else:
                    path.unlink()
                    messages.append("previous symlink removed")
            else:
                moved = backup_path(path)
                shutil.move(str(path), str(moved))
                messages.append(f"previous skills folder backed up to {moved}")
        else:
            messages.append("would replace skills directory with symlink")
    else:
        messages.append("would create skills symlink" if not apply else "creating skills symlink")

    if apply:
        path.symlink_to(shared_dir, target_is_directory=True)
        messages.append("skills directory now points to central library")

    return messages


def run(args: argparse.Namespace) -> int:
    shared_dir = expand(args.shared_dir)
    apply = args.mode == "apply"
    targets = discover_targets(args.target, args.only_targets)

    print(f"Central Skill library: {shared_dir}")
    print(f"Mode: {args.mode}")
    print(f"Shared directory: {ensure_shared_dir(shared_dir, apply)}")
    print(f"Self skill: {ensure_self_skill(shared_dir, apply, args.refresh_self)}")

    if shared_dir.exists():
        skills = skill_entries(shared_dir)
        if skills:
            print("Central skills: " + ", ".join(skill.name for skill in skills))
        else:
            print("Central skills: none yet")

    if not targets:
        print("No target skill directories discovered. Pass --target name=/path/to/skills.")
        return 1 if apply else 0

    for target in targets:
        print(f"\nTarget: {target.name} -> {target.path} ({target.reason})")
        for message in apply_target_symlink(target, shared_dir, apply, args.keep_old_symlink_backup):
            print(f"  {message}")

    if apply and not args.no_open_manager:
        print(f"\nManager: {launch_manager(shared_dir, args.open_manager)}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared-dir", default=DEFAULT_SHARED_DIR, help="central Skill library")
    parser.add_argument("--mode", choices=["plan", "apply"], default="plan")
    parser.add_argument(
        "--target",
        action="append",
        type=parse_target,
        default=[],
        help="extra agent skills path as name=/path/to/skills; repeatable",
    )
    parser.add_argument(
        "--only-targets",
        action="store_true",
        help="use only explicit --target values and skip default discovery",
    )
    parser.add_argument(
        "--refresh-self",
        action="store_true",
        help="replace the central copy of this skill with the currently running copy",
    )
    parser.add_argument(
        "--keep-old-symlink-backup",
        action="store_true",
        help="move old non-central symlinks to a backup path instead of unlinking them",
    )
    parser.add_argument(
        "--open-manager",
        action="store_true",
        help="open the local manager even if it was opened before",
    )
    parser.add_argument(
        "--no-open-manager",
        action="store_true",
        help="do not auto-open the local manager after apply",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
