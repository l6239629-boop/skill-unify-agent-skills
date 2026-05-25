#!/usr/bin/env python3
"""Local-only SharedSkills manager server."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


DEFAULT_SHARED_DIR = "~/Desktop/SharedSkills"
SELF_SKILL_ID = "unify-agent-skills"
EXCLUDED_TOP_LEVEL = {".skill-manager", ".disabled", ".backups"}


def expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path))).absolute()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def encode_id(skill_id: str) -> str:
    return base64.urlsafe_b64encode(skill_id.encode("utf-8")).decode("ascii").rstrip("=")


def decode_id(encoded: str) -> str:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode((encoded + padding).encode("ascii")).decode("utf-8")


def safe_join(root: Path, rel: str) -> Path:
    candidate = (root / rel).absolute()
    root_resolved = root.resolve()
    try:
        candidate_resolved = candidate.resolve()
    except FileNotFoundError:
        candidate_resolved = candidate.parent.resolve() / candidate.name
    if root_resolved != candidate_resolved and root_resolved not in candidate_resolved.parents:
        raise ValueError("path escapes shared directory")
    return candidate


def parse_frontmatter(skill_md: Path) -> dict[str, str]:
    try:
        text = skill_md.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in {"name", "description"}:
            data[key] = value
    return data


def hash_skill(path: Path) -> tuple[str, int, int, float, dict[str, dict]]:
    digest = hashlib.sha256()
    file_count = 0
    total_size = 0
    latest_mtime = 0.0
    file_hashes: dict[str, dict] = {}
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        if any(part == "__pycache__" for part in file_path.parts):
            continue
        try:
            rel = file_path.relative_to(path).as_posix()
            stat = file_path.stat()
            file_digest = hashlib.sha256()
            with file_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    file_digest.update(chunk)
            file_hash = file_digest.hexdigest()
            digest.update(rel.encode("utf-8"))
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(file_hash.encode("ascii"))
            file_hashes[rel] = {"hash": file_hash, "size": stat.st_size}
            file_count += 1
            total_size += stat.st_size
            latest_mtime = max(latest_mtime, stat.st_mtime)
        except OSError:
            continue
    return digest.hexdigest(), file_count, total_size, latest_mtime, file_hashes


class SkillManager:
    def __init__(self, shared_dir: Path):
        self.shared_dir = shared_dir
        self.manager_dir = shared_dir / ".skill-manager"
        self.disabled_dir = shared_dir / ".disabled"
        self.trash_dir = self.manager_dir / "trash"
        self.knowledge_dir = self.manager_dir / "knowledge-base"
        self.state_path = self.manager_dir / "state.json"
        self.events_path = self.manager_dir / "events.jsonl"
        self.manager_dir.mkdir(parents=True, exist_ok=True)
        self.disabled_dir.mkdir(parents=True, exist_ok=True)
        self.trash_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

    def is_excluded(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.shared_dir)
        except ValueError:
            return True
        return bool(rel.parts and rel.parts[0] in EXCLUDED_TOP_LEVEL)

    def active_skill_paths(self) -> list[Path]:
        result: list[Path] = []
        for skill_md in self.shared_dir.rglob("SKILL.md"):
            parent = skill_md.parent
            if self.is_excluded(parent):
                continue
            result.append(parent)
        return sorted(set(result), key=lambda item: item.relative_to(self.shared_dir).as_posix())

    def disabled_skill_paths(self) -> list[Path]:
        result: list[Path] = []
        for skill_md in self.disabled_dir.rglob("SKILL.md"):
            result.append(skill_md.parent)
        return sorted(set(result), key=lambda item: item.name)

    def skill_record(self, path: Path, status: str) -> dict:
        if status == "disabled":
            manifest = self.read_manifest(path)
            skill_id = manifest.get("original_id") or decode_id(path.name)
            rel_path = f".disabled/{path.name}"
        else:
            skill_id = path.relative_to(self.shared_dir).as_posix()
            rel_path = skill_id
        parts = skill_id.split("/")
        category = parts[0] if len(parts) > 1 else "SharedSkills"
        meta = parse_frontmatter(path / "SKILL.md")
        digest, file_count, total_size, latest_mtime, file_hashes = hash_skill(path)
        protected = skill_id == SELF_SKILL_ID or skill_id.startswith(".system/")
        return {
            "id": skill_id,
            "folder": path.name,
            "path": str(path),
            "relativePath": rel_path,
            "category": category,
            "projectName": category,
            "name": meta.get("name") or skill_id.split("/")[-1],
            "description": meta.get("description") or "",
            "status": status,
            "hash": digest,
            "fileCount": file_count,
            "sizeBytes": total_size,
            "modifiedAt": datetime.fromtimestamp(latest_mtime or path.stat().st_mtime).isoformat(timespec="seconds"),
            "protected": protected,
            "fileHashes": file_hashes,
            "versionCount": len(self.versions(skill_id, limit=100000)),
        }

    def load_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def save_state(self, state: dict) -> None:
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def version_file(self, skill_id: str) -> Path:
        folder = self.knowledge_dir / encode_id(skill_id)
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "versions.jsonl"

    def versions(self, skill_id: str, limit: int = 100) -> list[dict]:
        path = self.version_file(skill_id)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        result = []
        for line in lines[-limit:]:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return result

    def change_points(self, current: dict, previous: dict | None, reason: str) -> list[str]:
        if previous is None:
            return [f"Initial knowledge-base record for {current['id']}."]
        changes: list[str] = []
        if previous.get("status") != current.get("status"):
            changes.append(f"Status changed: {previous.get('status')} -> {current.get('status')}.")
        if previous.get("name") != current.get("name"):
            changes.append(f"Name changed: {previous.get('name') or '(empty)'} -> {current.get('name') or '(empty)'}.")
        if previous.get("description") != current.get("description"):
            changes.append("Description changed.")
        old_files = previous.get("fileHashes", {})
        new_files = current.get("fileHashes", {})
        added = sorted(set(new_files) - set(old_files))
        removed = sorted(set(old_files) - set(new_files))
        modified = sorted(
            name for name in set(old_files) & set(new_files)
            if old_files[name].get("hash") != new_files[name].get("hash")
        )
        if added:
            changes.append("Files added: " + ", ".join(added[:12]) + (" ..." if len(added) > 12 else ""))
        if removed:
            changes.append("Files removed: " + ", ".join(removed[:12]) + (" ..." if len(removed) > 12 else ""))
        if modified:
            changes.append("Files modified: " + ", ".join(modified[:12]) + (" ..." if len(modified) > 12 else ""))
        if not changes:
            changes.append(f"Version recorded after {reason}.")
        return changes

    def record_version(self, skill: dict, previous: dict | None, reason: str) -> None:
        existing = self.versions(skill["id"], limit=1)
        if existing and existing[-1].get("hash") == skill["hash"] and existing[-1].get("status") == skill["status"]:
            return
        version = {
            "version": len(self.versions(skill["id"], limit=100000)) + 1,
            "time": utc_now(),
            "skillId": skill["id"],
            "name": skill["name"],
            "status": skill["status"],
            "hash": skill["hash"],
            "fileCount": skill["fileCount"],
            "sizeBytes": skill["sizeBytes"],
            "reason": reason,
            "changePoints": self.change_points(skill, previous, reason),
        }
        with self.version_file(skill["id"]).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(version, ensure_ascii=False) + "\n")

    def append_event(self, event_type: str, skill_id: str, detail: str = "", actor: str = "scanner") -> None:
        event = {
            "time": utc_now(),
            "type": event_type,
            "skillId": skill_id,
            "detail": detail,
            "actor": actor,
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def scan(self, record_events: bool = True) -> dict:
        skills = [self.skill_record(path, "active") for path in self.active_skill_paths()]
        skills.extend(self.skill_record(path, "disabled") for path in self.disabled_skill_paths())
        current = {
            item["id"]: {
                "hash": item["hash"],
                "status": item["status"],
                "name": item["name"],
                "description": item["description"],
                "fileHashes": item["fileHashes"],
            }
            for item in skills
        }
        previous = self.load_state()
        for skill in skills:
            prev = previous.get(skill["id"]) if previous else None
            if prev is None:
                self.record_version(skill, None, "added")
            elif prev.get("hash") != skill["hash"] or prev.get("status") != skill["status"]:
                self.record_version(skill, prev, "changed")
        if previous and record_events:
            previous_ids = set(previous)
            current_ids = set(current)
            for skill_id in sorted(current_ids - previous_ids):
                self.append_event("added", skill_id)
            for skill_id in sorted(previous_ids - current_ids):
                self.append_event("removed", skill_id)
            for skill_id in sorted(previous_ids & current_ids):
                old = previous[skill_id]
                new = current[skill_id]
                if old.get("status") != new.get("status"):
                    self.append_event(new["status"], skill_id, f"{old.get('status')} -> {new.get('status')}")
                elif old.get("hash") != new.get("hash"):
                    self.append_event("modified", skill_id)
        self.save_state(current)
        for skill in skills:
            skill.pop("fileHashes", None)
            skill["versionCount"] = len(self.versions(skill["id"], limit=100000))
        return {"sharedDir": str(self.shared_dir), "skills": skills, "events": self.events(limit=50)}

    def events(self, limit: int = 200) -> list[dict]:
        if not self.events_path.exists():
            return []
        lines = self.events_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        result = []
        for line in lines[-limit:]:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return result

    def read_manifest(self, disabled_path: Path) -> dict:
        manifest = disabled_path / ".disabled-manifest.json"
        if not manifest.exists():
            return {}
        try:
            return json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def disable(self, skill_id: str) -> dict:
        if skill_id == SELF_SKILL_ID:
            raise ValueError("The manager skill cannot disable itself.")
        if skill_id.startswith(".system/"):
            raise ValueError("System skills are protected by default.")
        source = safe_join(self.shared_dir, skill_id)
        if not source.exists() or not (source / "SKILL.md").exists():
            raise ValueError("Active skill not found.")
        encoded = encode_id(skill_id)
        dest = self.disabled_dir / encoded
        if dest.exists():
            raise ValueError("A disabled copy already exists.")
        shutil.move(str(source), str(dest))
        (dest / ".disabled-manifest.json").write_text(
            json.dumps({"original_id": skill_id, "disabled_at": utc_now()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.append_event("disabled", skill_id, actor="user")
        return self.scan(record_events=False)

    def enable(self, skill_id: str) -> dict:
        encoded = encode_id(skill_id)
        source = self.disabled_dir / encoded
        if not source.exists():
            for candidate in self.disabled_dir.iterdir():
                if self.read_manifest(candidate).get("original_id") == skill_id:
                    source = candidate
                    break
        if not source.exists():
            raise ValueError("Disabled skill not found.")
        dest = safe_join(self.shared_dir, skill_id)
        if dest.exists():
            raise ValueError("Active destination already exists.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        manifest = source / ".disabled-manifest.json"
        if manifest.exists():
            manifest.unlink()
        shutil.move(str(source), str(dest))
        self.append_event("enabled", skill_id, actor="user")
        return self.scan(record_events=False)

    def delete(self, skill_id: str) -> dict:
        if skill_id == SELF_SKILL_ID:
            raise ValueError("The manager skill cannot delete itself.")
        if skill_id.startswith(".system/"):
            raise ValueError("System skills are protected by default.")
        active = safe_join(self.shared_dir, skill_id)
        encoded = encode_id(skill_id)
        source = active if active.exists() else self.disabled_dir / encoded
        if not source.exists():
            raise ValueError("Skill not found.")
        if (source / "SKILL.md").exists():
            status = "active" if source == active else "disabled"
            skill = self.skill_record(source, status)
            self.record_version(skill, self.load_state().get(skill_id), "deleted")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = self.trash_dir / f"{stamp}-{encode_id(skill_id)}"
        shutil.move(str(source), str(dest))
        self.append_event("deleted", skill_id, f"moved to {dest}", actor="user")
        return self.scan(record_events=False)

    def reveal(self, skill_id: str) -> dict:
        path = safe_join(self.shared_dir, skill_id)
        if not path.exists():
            path = self.disabled_dir / encode_id(skill_id)
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        elif os.name == "nt":
            subprocess.Popen(["explorer", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return {"ok": True}


def json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def make_handler(manager: SkillManager, static_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/skills":
                json_response(self, manager.scan())
                return
            if parsed.path == "/api/events":
                limit = int(parse_qs(parsed.query).get("limit", ["200"])[0])
                json_response(self, {"events": manager.events(limit=limit)})
                return
            parts = [unquote(part) for part in parsed.path.split("/") if part]
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "versions":
                json_response(self, {"skillId": parts[2], "versions": manager.versions(parts[2], limit=200)})
                return
            if parsed.path in {"/", "/index.html"}:
                self.serve_file(static_dir / "index.html")
                return
            self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            parts = [unquote(part) for part in parsed.path.split("/") if part]
            try:
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "disable":
                    json_response(self, manager.disable(parts[2]))
                elif len(parts) == 3 and parts[0] == "api" and parts[1] == "enable":
                    json_response(self, manager.enable(parts[2]))
                elif len(parts) == 3 and parts[0] == "api" and parts[1] == "delete":
                    json_response(self, manager.delete(parts[2]))
                elif len(parts) == 3 and parts[0] == "api" and parts[1] == "reveal":
                    json_response(self, manager.reveal(parts[2]))
                else:
                    self.send_error(404)
            except Exception as exc:
                json_response(self, {"error": str(exc)}, status=400)

        def serve_file(self, path: Path) -> None:
            if not path.exists():
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "text/plain")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve(args: argparse.Namespace) -> int:
    shared_dir = expand(args.shared_dir)
    static_dir = Path(__file__).resolve().parents[1] / "assets" / "manager"
    manager = SkillManager(shared_dir)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(manager, static_dir))
    host, port = server.server_address
    url = f"http://{host}:{port}/"
    (manager.manager_dir / "server.json").write_text(
        json.dumps({"url": url, "pid": os.getpid(), "startedAt": utc_now()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(url, flush=True)
    if args.open:
        threading.Timer(0.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared-dir", default=DEFAULT_SHARED_DIR)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="open the manager in the default browser")
    return parser


if __name__ == "__main__":
    raise SystemExit(serve(build_parser().parse_args()))
