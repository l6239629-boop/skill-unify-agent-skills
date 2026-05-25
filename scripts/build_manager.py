#!/usr/bin/env python3
"""Build a standalone SharedSkills manager HTML with all data embedded."""

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path))).absolute()


def encode_id(skill_id: str) -> str:
    import base64
    return base64.urlsafe_b64encode(skill_id.encode()).decode().rstrip("=")


def parse_frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    second = text.find("---", 3)
    if second == -1:
        return {}
    data = {}
    for line in text[3:second].splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key in ("name", "description"):
            data[key] = val
    return data


def dir_stats(path: Path) -> dict:
    """Compute file count, size, modification time, and a metadata hash."""
    file_count = 0
    total_size = 0
    latest_mtime = 0.0
    lines = []
    for fp in sorted(path.rglob("*")):
        if fp.is_file():
            if "__pycache__" in fp.parts:
                continue
            try:
                stat = fp.stat()
                rel = fp.relative_to(path).as_posix()
                lines.append(f"{rel}:{stat.st_size}:{stat.st_mtime}")
                file_count += 1
                total_size += stat.st_size
                latest_mtime = max(latest_mtime, stat.st_mtime)
            except OSError:
                continue
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    return {
        "hash": digest,
        "fileCount": file_count,
        "sizeBytes": total_size,
        "modifiedAt": datetime.fromtimestamp(latest_mtime or 0).isoformat(timespec="seconds"),
    }


def scan_skills(shared_dir: Path) -> list:
    """Scan SharedSkills directory for all active and disabled skills."""
    EXCLUDED = {".skill-manager", ".disabled", ".backups"}
    SELF = "unify-agent-skills"
    skills = []

    for skill_md in sorted(shared_dir.rglob("SKILL.md")):
        parent = skill_md.parent
        rel = parent.relative_to(shared_dir)
        parts = rel.parts
        if not parts:
            continue
        if parts[0] in EXCLUDED:
            continue
        if parts[0].startswith(".") and len(parts) == 1:
            continue

        skill_id = rel.as_posix()
        meta = parse_frontmatter(skill_md)
        stats = dir_stats(parent)
        category = parts[0] if len(parts) > 1 else "SharedSkills"
        protected = skill_id == SELF or skill_id.startswith(".system/")

        skills.append({
            "id": skill_id,
            "folder": parent.name,
            "path": str(parent),
            "relativePath": skill_id,
            "category": category,
            "projectName": category,
            "name": meta.get("name") or parent.name,
            "description": meta.get("description") or "",
            "status": "active",
            "hash": stats["hash"],
            "fileCount": stats["fileCount"],
            "sizeBytes": stats["sizeBytes"],
            "modifiedAt": stats["modifiedAt"],
            "protected": protected,
            "versionCount": 0,
        })

    # Handle symlinked directories at top level (rglob in Python <3.12 does not follow symlinks)
    for entry in sorted(shared_dir.iterdir()):
        if not entry.is_symlink():
            continue
        resolved = entry.resolve()
        if not resolved.is_dir():
            continue
        base_name = entry.name
        if base_name.startswith("."):
            continue
        for skill_md in sorted(resolved.rglob("SKILL.md")):
            parent = skill_md.parent
            try:
                rel = parent.relative_to(resolved)
            except ValueError:
                continue
            skill_id = f"{base_name}/{rel.as_posix()}" if rel.parts else base_name
            meta = parse_frontmatter(skill_md)
            stats = dir_stats(parent)
            category = base_name
            protected = False
            skills.append({
                "id": skill_id,
                "folder": parent.name,
                "path": str(parent),
                "relativePath": skill_id,
                "category": category,
                "projectName": category,
                "name": meta.get("name") or parent.name,
                "description": meta.get("description") or "",
                "status": "active",
                "hash": stats["hash"],
                "fileCount": stats["fileCount"],
                "sizeBytes": stats["sizeBytes"],
                "modifiedAt": stats["modifiedAt"],
                "protected": protected,
                "versionCount": 0,
            })

    # Disabled skills
    disabled_dir = shared_dir / ".disabled"
    if disabled_dir.is_dir():
        for entry in sorted(disabled_dir.iterdir()):
            if not entry.is_dir():
                continue
            skmd = entry / "SKILL.md"
            if not skmd.exists():
                continue
            meta = parse_frontmatter(skmd)
            stats = dir_stats(entry)

            skill_id = entry.name
            manifest = entry / ".disabled-manifest.json"
            if manifest.exists():
                try:
                    mdata = json.loads(manifest.read_text(encoding="utf-8"))
                    if mdata.get("original_id"):
                        skill_id = mdata["original_id"]
                except (OSError, json.JSONDecodeError):
                    pass

            skills.append({
                "id": skill_id,
                "folder": entry.name,
                "path": str(entry),
                "relativePath": f".disabled/{entry.name}",
                "category": ".disabled",
                "projectName": ".disabled",
                "name": meta.get("name") or entry.name,
                "description": meta.get("description") or "",
                "status": "disabled",
                "hash": stats["hash"],
                "fileCount": stats["fileCount"],
                "sizeBytes": stats["sizeBytes"],
                "modifiedAt": stats["modifiedAt"],
                "protected": False,
                "versionCount": 0,
            })

    # Version counts
    kb_dir = shared_dir / ".skill-manager" / "knowledge-base"
    if kb_dir.is_dir():
        for skill in skills:
            eid = encode_id(skill["id"])
            vf = kb_dir / eid / "versions.jsonl"
            if vf.exists():
                try:
                    skill["versionCount"] = len(vf.read_text(encoding="utf-8", errors="ignore").strip().splitlines())
                except OSError:
                    pass

    return skills


def load_events(shared_dir: Path, limit: int = 200) -> list:
    path = shared_dir / ".skill-manager" / "events.jsonl"
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        events = []
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events
    except OSError:
        return []


def load_all_versions(shared_dir: Path) -> dict:
    """Load version records for all skills, keyed by skill ID."""
    kb_dir = shared_dir / ".skill-manager" / "knowledge-base"
    result = {}
    if not kb_dir.is_dir():
        return result
    for sub in kb_dir.iterdir():
        if not sub.is_dir():
            continue
        vf = sub / "versions.jsonl"
        if not vf.exists():
            continue
        try:
            lines = vf.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
            versions = []
            for line in lines:
                try:
                    versions.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if versions:
                sid = versions[-1].get("skillId", sub.name)
                result[sid] = versions[-200:]
        except OSError:
            continue
    return result


# The HTML template uses __DATA_PLACEHOLDER__, __VERSIONS_PLACEHOLDER__, __SHARED_DIR_PLACEHOLDER__
# which are replaced by the build() function. The JS code reads the injected JSON objects
# and renders the full manager UI with complete i18n matching the original server version.
META_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SharedSkills Manager</title>
<style>
:root{--bg:#f7f8fb;--panel:#fff;--text:#1d2433;--muted:#667085;--line:#d8dee9;--accent:#126b5d;--accent-soft:#e3f4ef;--danger:#b42318;--warn:#9a6700;--shadow:0 10px 30px rgba(18,24,40,.08)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{padding:22px 28px 18px;background:var(--panel);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
h1{margin:0;font-size:22px;font-weight:700}
.sub{color:var(--muted);margin-top:4px;overflow-wrap:anywhere;font-size:12px}
main{padding:22px 28px 32px}
.toolbar{display:grid;grid-template-columns:minmax(180px,1fr) auto auto;gap:10px;margin-bottom:18px}
input,select,button{height:36px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--text);padding:0 10px;font:inherit}
button{cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px;font-weight:600}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
button.danger{color:var(--danger)}
button:disabled{opacity:.45;cursor:not-allowed}
.banner{background:#e3f4ef;border:1px solid var(--accent);border-radius:8px;padding:14px 18px;margin-bottom:18px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.banner-text{color:var(--accent);font-weight:600}
.banner-hint{color:var(--muted);font-size:12px}
.banner-hint code{background:var(--accent-soft);padding:1px 5px;border-radius:3px;font-size:11px}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:18px;align-items:start}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow);overflow:hidden}
table{width:100%;border-collapse:collapse}
th,td{padding:12px 14px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:12px;color:var(--muted);background:#fbfcfe;font-weight:700}
tr:last-child td{border-bottom:0}
th:nth-child(2),th:nth-child(3),th:nth-child(4){width:130px}
.name{font-weight:700}
.desc{color:var(--muted);margin-top:3px;max-width:680px}
.path{color:var(--muted);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;overflow-wrap:anywhere;margin-top:6px}
.badge{display:inline-flex;align-items:center;height:24px;padding:0 8px;border-radius:999px;font-size:12px;font-weight:700;background:var(--accent-soft);color:var(--accent)}
.badge.disabled{background:#fff4d6;color:var(--warn)}
.badge.protected{background:#eef2f6;color:#475467}
.actions{display:flex;flex-wrap:wrap;gap:8px}
.stats{white-space:nowrap}
.folder-row td{background:#f3f6f8;color:var(--text);font-weight:700;border-bottom:1px solid var(--line)}
.folder-pill{display:inline-flex;align-items:center;gap:8px;min-height:28px}
.folder-count{color:var(--muted);font-weight:600;font-size:12px}
.events{padding:14px;max-height:620px;overflow:auto}
.side-title{padding:14px 14px 0;margin:0;font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.versions{padding:14px;max-height:360px;overflow:auto;border-top:1px solid var(--line)}
.event{border-bottom:1px solid var(--line);padding:10px 0}
.event:last-child{border-bottom:0}
.event strong{display:block}
.event span{color:var(--muted);font-size:12px;overflow-wrap:anywhere}
.event ul{margin:8px 0 0 18px;padding:0;color:var(--muted)}
.empty{padding:32px;color:var(--muted);text-align:center}
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--text);color:#fff;padding:10px 20px;border-radius:8px;font-weight:600;font-size:13px;z-index:999;opacity:0;transition:opacity .25s;pointer-events:none}
.toast.show{opacity:1}
code.cmd{display:block;background:#1d2433;color:#e3f4ef;padding:10px 14px;border-radius:6px;font-size:12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;margin-top:8px;white-space:nowrap;overflow-x:auto}
@media(max-width:980px){header,main{padding-left:16px;padding-right:16px}.toolbar{grid-template-columns:1fr}.layout{grid-template-columns:1fr}table,thead,tbody,tr,th,td{display:block}thead{display:none}tr{border-bottom:1px solid var(--line)}td{border-bottom:0}}
</style>
</head>
<body>
<header><div><h1>SharedSkills Manager</h1><div class="sub" id="sharedDir"></div></div>
<div class="actions"><button id="langBtn">中文</button><button class="primary" id="rebuildBtn">Rebuild</button></div></header>
<main>
<div class="banner" id="banner" hidden>
<div><div class="banner-text" id="bannerText"></div><div class="banner-hint" id="bannerHint"></div></div>
<button id="bannerCopy" hidden></button>
</div>
<div class="toolbar">
<input id="search" placeholder="按名称、描述或路径搜索 Skill">
<select id="status"><option value="all">全部状态</option><option value="active">仅启用</option><option value="disabled">仅禁用</option></select>
<select id="sort"><option value="name">按名称排序</option><option value="modified">按修改时间排序</option><option value="status">按状态排序</option></select>
</div>
<section class="layout">
<div class="panel"><table><thead><tr><th>Skill</th><th>状态</th><th>统计</th><th>操作</th></tr></thead><tbody id="skillRows"></tbody></table><div class="empty" id="empty" hidden>没有匹配当前筛选条件的 Skill。</div></div>
<aside class="panel"><h2 class="side-title" id="sideEvents">改动记录</h2><div class="events" id="events"></div><h2 class="side-title" id="sideVersions">知识库</h2><div class="versions" id="versions"></div></aside>
</section>
</main>
<div class="toast" id="toast"></div>
<script>
// --- Injected data ---
var DATA = __DATA_PLACEHOLDER__;
var VERSIONS = __VERSIONS_PLACEHOLDER__;
var SHARED_DIR = __SHARED_DIR_PLACEHOLDER__;
// --- Constants ---
var SELF_ID = "unify-agent-skills";

// --- Full i18n matching original server version ---
var i18n = {
  en: {
    title: "SharedSkills Manager", rebuild: "Rebuild", refresh: "Refresh",
    search: "Search skills by name, description, or path",
    all: "All statuses", activeOnly: "Active only", disabledOnly: "Disabled only",
    sortName: "Sort by name", sortModified: "Sort by modified time", sortStatus: "Sort by status",
    folder: "Folder", rootFolder: "SharedSkills", skill: "Skill",
    status: "Status", stats: "Stats", actions: "Actions",
    activeLbl: "active", disabledLbl: "disabled", protected: "Protected",
    copyPath: "Copy Path", disable: "Disable", enable: "Enable", del: "Delete",
    versions: "Versions", events: "Events", knowledge: "Knowledge Base", files: "files",
    noDescription: "No description", noSkills: "No skills match the current filters.",
    noEvents: "No recorded changes yet.", noVersions: "No versions recorded yet.",
    selectSkill: "Select a skill to view its version knowledge base.",
    language: "中文", operationFailed: "Operation failed",
    snapshotBanner: "Snapshot from {time}",
    snapshotHint: 'Data is static. Run <code>python3 ~/Desktop/SharedSkills/unify-agent-skills/scripts/build_manager.py</code> to rebuild.',
    rebuildCopied: "Rebuild command copied to clipboard.",
    pathCopied: "Path copied to clipboard.",
    cmdDisable: "Disable command copied — paste in terminal where server is running.",
    cmdEnable: "Enable command copied — paste in terminal where server is running.",
    cmdDelete: "Delete command copied — paste in terminal where server is running.",
    confirmDelete: function(n) { return 'Move "' + n + '" to the manager trash?'; }
  },
  zh: {
    title: "SharedSkills 管理台", rebuild: "重新构建", refresh: "刷新",
    search: "按名称、描述或路径搜索 Skill",
    all: "全部状态", activeOnly: "仅启用", disabledOnly: "仅禁用",
    sortName: "按名称排序", sortModified: "按修改时间排序", sortStatus: "按状态排序",
    folder: "文件夹", rootFolder: "SharedSkills 根目录", skill: "Skill",
    status: "状态", stats: "统计", actions: "操作",
    activeLbl: "启用", disabledLbl: "禁用", protected: "受保护",
    copyPath: "复制路径", disable: "禁用", enable: "启用", del: "删除",
    versions: "版本", events: "改动记录", knowledge: "知识库", files: "个文件",
    noDescription: "暂无描述", noSkills: "没有匹配当前筛选条件的 Skill。",
    noEvents: "暂无改动记录。", noVersions: "暂无版本记录。",
    selectSkill: "选择一个 Skill 查看它的版本知识库。",
    language: "EN", operationFailed: "操作失败",
    snapshotBanner: "数据快照，构建于 {time}",
    snapshotHint: '数据为静态快照。运行 <code>python3 ~/Desktop/SharedSkills/unify-agent-skills/scripts/build_manager.py</code> 重新构建以刷新数据。',
    rebuildCopied: "构建命令已复制到剪贴板。",
    pathCopied: "路径已复制到剪贴板。",
    cmdDisable: "禁用命令已复制 — 请在管理台服务运行后将命令粘贴到终端执行。",
    cmdEnable: "启用命令已复制 — 请在管理台服务运行后将命令粘贴到终端执行。",
    cmdDelete: "删除命令已复制 — 请在管理台服务运行后将命令粘贴到终端执行。",
    confirmDelete: function(n) { return '将「' + n + '」移动到管理台回收区？'; }
  }
};

// --- Localized event labels ---
var eventLabels = {
  zh: { added: "新增", removed: "移除", modified: "修改", disabled: "禁用", enabled: "启用", deleted: "删除", active: "启用" },
  en: {}
};

// --- State ---
var s = {
  skills: DATA.skills || [],
  events: DATA.events || [],
  sharedDir: SHARED_DIR,
  lang: localStorage.getItem("mlang") || "zh",
  sel: "",
  vers: []
};

// --- Helpers ---
function t(k) { return (i18n[s.lang] && i18n[s.lang][k]) || (i18n.en && i18n.en[k]) || k; }
function el(tp) { return (eventLabels[s.lang] && eventLabels[s.lang][tp]) || tp; }

function changePoint(text) {
  if (s.lang !== "zh") return text;
  return text
    .replace(/^Initial knowledge-base record for (.+)\.$/, "首次写入知识库：$1。")
    .replace(/^Status changed: (.+) -> (.+)\.$/, "状态变化：$1 -> $2。")
    .replace("Description changed.", "描述发生变化。")
    .replace("Files added: ", "新增文件：")
    .replace("Files removed: ", "移除文件：")
    .replace("Files modified: ", "修改文件：")
    .replace(/^Version recorded after (.+)\.$/, "已记录版本，原因：$1。");
}

function fmtBytes(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

function badge(sk) {
  var st = sk.status === "disabled" ? "disabledLbl" : "activeLbl";
  var cls = sk.status === "disabled" ? "disabled" : "active";
  var pr = sk.protected ? '<span class="badge protected">' + t("protected") + "</span>" : "";
  return '<span class="badge ' + cls + '">' + t(st) + "</span> " + pr;
}

function escHtml(v) {
  return String(v).replace(/[&<>"']/g, function(c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}
function escAttr(v) { return escHtml(v).replace(/`/g, "&#96;").replace(/\\/g, "\\\\"); }

function groupSkills(skills) {
  var map = new Map();
  for (var i = 0; i < skills.length; i++) {
    var sk = skills[i];
    var n = sk.category || "SharedSkills";
    if (!map.has(n)) map.set(n, []);
    map.get(n).push(sk);
  }
  var arr = [];
  map.forEach(function(items, name) { arr.push({ name: name, skills: items }); });
  arr.sort(function(a, b) { return displayCat(a.name).localeCompare(displayCat(b.name)); });
  return arr;
}

function displayCat(name) {
  if (name === "SharedSkills") return t("rootFolder");
  if (name === ".disabled") return t("folder") + " · " + t("disabledLbl");
  return t("folder") + " · " + name;
}

// --- Render ---
function render() {
  document.querySelector("h1").textContent = t("title");
  document.getElementById("rebuildBtn").textContent = t("rebuild");
  document.getElementById("langBtn").textContent = t("language");
  document.getElementById("sharedDir").textContent = s.sharedDir;
  document.getElementById("search").placeholder = t("search");
  document.getElementById("sideEvents").textContent = t("events");
  document.getElementById("sideVersions").textContent = t("knowledge");

  var stSel = document.getElementById("status");
  stSel.options[0].textContent = t("all");
  stSel.options[1].textContent = t("activeOnly");
  stSel.options[2].textContent = t("disabledOnly");

  var soSel = document.getElementById("sort");
  soSel.options[0].textContent = t("sortName");
  soSel.options[1].textContent = t("sortModified");
  soSel.options[2].textContent = t("sortStatus");

  var ths = document.querySelectorAll("th");
  ths[0].textContent = t("skill");
  ths[1].textContent = t("status");
  ths[2].textContent = t("stats");
  ths[3].textContent = t("actions");

  // --- Snapshot banner ---
  var banner = document.getElementById("banner");
  var bannerText = document.getElementById("bannerText");
  var bannerHint = document.getElementById("bannerHint");
  var bannerCopy = document.getElementById("bannerCopy");
  bannerText.textContent = t("snapshotBanner").replace("{time}", DATA.builtAt || "");
  bannerHint.innerHTML = t("snapshotHint");
  banner.hidden = false;

  // --- Filter & sort ---
  var q = document.getElementById("search").value.trim().toLowerCase();
  var sv = document.getElementById("status").value;
  var sov = document.getElementById("sort").value;

  var skills = s.skills.filter(function(sk) {
    var matchStatus = sv === "all" || sk.status === sv;
    var haystack = (sk.name + " " + sk.description + " " + sk.id).toLowerCase();
    return matchStatus && (!q || haystack.indexOf(q) !== -1);
  });

  skills.sort(function(a, b) {
    if (sov === "modified") return b.modifiedAt.localeCompare(a.modifiedAt);
    if (sov === "status") return a.status.localeCompare(b.status) || a.name.localeCompare(b.name);
    return (a.category || "").localeCompare(b.category || "") || a.name.localeCompare(b.name);
  });

  // --- Table ---
  var groups = groupSkills(skills);
  var rows = document.getElementById("skillRows");
  rows.innerHTML = groups.map(function(g) {
    return '<tr class="folder-row"><td colspan="4"><span class="folder-pill">'
      + escHtml(g.name) + ' <span class="folder-count">' + g.skills.length + " " + t("skill")
      + "</span></span></td></tr>"
      + g.skills.map(function(sk) {
        var btns = '<button onclick="showVersions(\'' + escAttr(sk.id) + '\')">' + t("versions") + '</button>'
          + '<button onclick="copyPath(\'' + escAttr(sk.id) + '\')">' + t("copyPath") + '</button>';
        if (sk.status === "active") {
          btns += '<button ' + (sk.protected ? "disabled" : "")
            + ' onclick="doCmd(\'disable\',\'' + escAttr(sk.id) + '\')">' + t("disable") + '</button>';
        } else {
          btns += '<button onclick="doCmd(\'enable\',\'' + escAttr(sk.id) + '\')">' + t("enable") + '</button>';
        }
        btns += '<button class="danger" ' + (sk.protected ? "disabled" : "")
          + ' onclick="confirmDel(\'' + escAttr(sk.id) + '\',\'' + escAttr(sk.name) + '\')">' + t("del") + '</button>';

        return '<tr><td><div class="name">' + escHtml(sk.name)
          + '</div><div class="desc">' + escHtml(sk.description || t("noDescription"))
          + '</div><div class="path">' + escHtml(sk.id)
          + '</div></td><td>' + badge(sk)
          + '</td><td class="stats"><div>' + sk.fileCount + " " + t("files")
          + '</div><div>' + fmtBytes(sk.sizeBytes)
          + '</div><div class="path">' + escHtml(sk.modifiedAt)
          + '</div><div>' + (sk.versionCount || 0) + " " + t("versions")
          + '</div></td><td><div class="actions">' + btns + '</div></td></tr>';
      }).join("");
  }).join("");

  document.getElementById("empty").hidden = skills.length !== 0;
  document.getElementById("empty").textContent = t("noSkills");

  // --- Events ---
  var evEl = document.getElementById("events");
  evEl.innerHTML = s.events.slice().reverse().map(function(e) {
    return '<div class="event"><strong>' + escHtml(el(e.type)) + " &middot; " + escHtml(e.skillId)
      + '</strong><span>' + escHtml(e.time)
      + (e.detail ? " &middot; " + escHtml(e.detail) : "")
      + '</span></div>';
  }).join("") || '<div class="empty">' + t("noEvents") + '</div>';

  renderVersions();
}

// --- Versions ---
var versionsEl = document.getElementById("versions");
function showVersions(skillId) {
  s.sel = skillId;
  s.vers = VERSIONS[skillId] || [];
  renderVersions();
}

function renderVersions() {
  if (!s.sel) {
    versionsEl.innerHTML = '<div class="empty">' + t("selectSkill") + '</div>';
    return;
  }
  versionsEl.innerHTML = s.vers.slice().reverse().map(function(v) {
    return '<div class="event"><strong>v' + v.version + " &middot; " + escHtml(v.name || v.skillId)
      + '</strong><span>' + escHtml(v.time) + " &middot; " + escHtml(v.reason || "")
      + " &middot; " + escHtml((v.hash || "").slice(0, 12))
      + '</span><ul>' + (v.changePoints || []).map(function(p) {
        return "<li>" + escHtml(changePoint(p)) + "</li>";
      }).join("") + '</ul></div>';
  }).join("") || '<div class="empty">' + t("noVersions") + '</div>';
}

// --- Actions ---
function copyPath(skillId) {
  var path = s.sharedDir + "/" + skillId;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(path).then(function() { toast(t("pathCopied")); })
      .catch(function() { toast(path); });
  } else {
    showBanner(path, "", "Copy");
  }
}

function doCmd(action, skillId) {
  var cmd;
  if (action === "disable") cmd = "curl -s -X POST http://127.0.0.1:8765/api/disable/" + encodeURIComponent(skillId);
  else if (action === "enable") cmd = "curl -s -X POST http://127.0.0.1:8765/api/enable/" + encodeURIComponent(skillId);
  else cmd = "curl -s -X POST http://127.0.0.1:8765/api/delete/" + encodeURIComponent(skillId);

  var key = "cmd" + action.charAt(0).toUpperCase() + action.slice(1);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(cmd).then(function() { toast(t(key)); }).catch(function() { showBanner(cmd, "", "Copy"); });
  } else {
    showBanner(cmd, "", "Copy");
  }
}

function confirmDel(id, name) {
  var cf = t("confirmDelete");
  if (typeof cf === "function") cf = cf(name);
  if (confirm(cf)) doCmd("delete", id);
}

function rebuild() {
  var cmd = "python3 ~/Desktop/SharedSkills/unify-agent-skills/scripts/build_manager.py";
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(cmd).then(function() { toast(t("rebuildCopied")); })
      .catch(function() { showBanner(cmd, "", "Copy"); });
  } else {
    showBanner(cmd, "", "Copy");
  }
}

// --- Toast ---
var toastTimer;
function toast(msg) {
  var el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function() { el.classList.remove("show"); }, 3000);
}

// --- Banner ---
function showBanner(text, hint, btnText) {
  var banner = document.getElementById("banner");
  var bannerText = document.getElementById("bannerText");
  var bannerHint = document.getElementById("bannerHint");
  var bannerCopy = document.getElementById("bannerCopy");
  bannerText.textContent = text;
  bannerHint.innerHTML = hint || "";
  banner.hidden = false;
  if (btnText) {
    bannerCopy.textContent = btnText;
    bannerCopy.hidden = false;
    bannerCopy.onclick = function() {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function() { toast("Copied."); });
      }
    };
  } else {
    bannerCopy.hidden = true;
  }
}

// --- Init ---
document.getElementById("rebuildBtn").addEventListener("click", rebuild);
document.getElementById("langBtn").addEventListener("click", function() {
  s.lang = s.lang === "zh" ? "en" : "zh";
  localStorage.setItem("mlang", s.lang);
  render();
});
document.getElementById("search").addEventListener("input", render);
document.getElementById("status").addEventListener("change", render);
document.getElementById("sort").addEventListener("change", render);

render();
</script>
</body>
</html>'''


def build(args):
    shared_dir = expand(args.shared_dir)
    output = Path(args.output) if args.output else shared_dir / "unify-agent-skills" / "assets" / "manager" / "index.html"

    print(f"Scanning {shared_dir}...")
    skills = scan_skills(shared_dir)
    events = load_events(shared_dir, limit=200)
    versions = load_all_versions(shared_dir)

    data = {
        "builtAt": datetime.now().isoformat(timespec="seconds"),
        "skills": skills,
        "events": events,
        "skillCount": len(skills),
        "activeCount": sum(1 for s in skills if s["status"] == "active"),
        "disabledCount": sum(1 for s in skills if s["status"] == "disabled"),
    }

    html = META_HTML
    html = html.replace("__DATA_PLACEHOLDER__", json.dumps(data, ensure_ascii=False))
    html = html.replace("__VERSIONS_PLACEHOLDER__", json.dumps(versions, ensure_ascii=False))
    html = html.replace("__SHARED_DIR_PLACEHOLDER__", json.dumps(str(shared_dir), ensure_ascii=False))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"  Active:   {data['activeCount']}")
    print(f"  Disabled: {data['disabledCount']}")
    print(f"  Events:   {len(events)}")
    print(f"  Written to {output}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build standalone SharedSkills manager HTML")
    parser.add_argument("--shared-dir", default="~/Desktop/SharedSkills", help="Path to SharedSkills directory")
    parser.add_argument("--output", default="", help="Output HTML path")
    args = parser.parse_args()
    build(args)


if __name__ == "__main__":
    main()
