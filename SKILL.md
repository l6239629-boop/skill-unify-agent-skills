---
name: unify-agent-skills
description: Create and maintain one Desktop SharedSkills library for all local desktop coding agents by migrating existing skills into the central folder, replacing each agent's skills directory with a symlink, and providing a local browser-based SharedSkills Manager. Use when the user wants Claude Code, Codex, Cursor, Trae, OpenClaw, OpenCode, Qoder, Gemini CLI, Qwen Code, or other agents on the same computer to share one Skill library, auto-collect newly installed skills into the central library, audit skill symlinks, manage skills visually, record skill add/delete/modify history, or disable/delete skills locally.
---

# Unify Agent Skills

## Overview

Use this skill to implement a single source of truth for local agent skills. The article's required experience is: create one central `SharedSkills` folder on the Desktop, migrate existing agent skills into it, then replace each agent's entire `skills` directory with a symlink pointing to `SharedSkills`.

After setup, any new skill installed by any linked agent lands in the central folder and becomes visible to every other linked agent automatically.

This skill also includes a standalone local HTML manager. It embeds all skill data, events, and version history into a single HTML file that opens in any browser (Chrome, Edge, Safari, or the Codex in-app browser) without needing a server or filesystem API permissions. For mutations (disable/enable/delete), buttons copy the corresponding server command to the clipboard.

## Quick Workflow

1. Use `~/Desktop/SharedSkills` as the default central Skill library unless the user gives a different path.
2. Run a preview before changing paths:

```bash
python3 scripts/unify_agent_skills.py --mode plan
```

3. Apply the setup when the user wants the unified experience:

```bash
python3 scripts/unify_agent_skills.py --mode apply
```

4. The script must create `~/Desktop/SharedSkills` automatically, install this `unify-agent-skills` skill into it when missing, migrate existing target skills into it, back up old `skills` folders, and create `skills -> ~/Desktop/SharedSkills` symlinks.
5. On first successful `apply`, automatically launch the local manager and open it in the browser. If `.skill-manager/manager-opened.json` already exists, do not open it again unless `--open-manager` is used.
6. Report the central path, migrated skills, target symlinks, backups, manager URL or launch log, skipped conflicts, and any manual follow-up.

## Safety Rules

- Always start with `--mode plan`; switch to `--mode apply` when the user asked to set up or repair the unified library.
- Never delete an existing skill folder. The article says to remove the old `skills` folder after copying; implement that safely by moving it to a timestamped backup after migration.
- Preserve hidden skill collections such as `.system` when they live inside an agent's old `skills` folder; skip only OS noise such as `.DS_Store`.
- Treat user-created skill edits as valuable. Merge or preserve them instead of overwriting them.
- Prefer one real central folder and many symlinked `skills` folders. Do not create per-skill symlinks unless the user explicitly asks for a fallback.
- If `~/Desktop/SharedSkills/unify-agent-skills` already exists, treat it as the canonical copy and apply that existing file. Refresh it from the current copy only when the user asks or when `--refresh-self` is passed.
- The manager skill must not disable or delete itself. Protect `.system` skills in the UI because those are platform capabilities.
- Do not assume every agent supports the same metadata. Keep the canonical skill content in the shared library, then add small agent-specific metadata only where required.
- Prefer absolute paths in reports so the user can inspect the result directly.

## Common Tasks

### Audit Current State

Run:

```bash
python3 scripts/unify_agent_skills.py --mode plan
```

Use the output to identify whether `~/Desktop/SharedSkills` exists, whether this skill is already installed there, which target agents were discovered, and what each `skills` path would become.

### Link One Shared Library Everywhere

Run:

```bash
python3 scripts/unify_agent_skills.py --mode apply
```

This creates `~/Desktop/SharedSkills`, copies this skill into it if needed, moves existing skills from each target's old `skills` directory into the central library when no central copy exists, backs up the old directory, and creates a directory-level symlink.

The first successful run also starts the local manager and opens it in the browser.

### Build the Standalone Manager HTML

Run:

```bash
python3 scripts/build_manager.py
```

This scans `~/Desktop/SharedSkills` and generates a self-contained HTML file at `assets/manager/index.html`. The file embeds all skill data, events, and version history. Open it in any browser — no server, no filesystem permissions needed.

Options:
- `--shared-dir <path>` — scan a different SharedSkills directory
- `--output <path>` — write the HTML to a custom path

Skills shown in the manager are a snapshot at build time. Re-run the build script to refresh the data.

The disable/enable/delete buttons copy `curl` commands to the clipboard. Paste and run them in a terminal where the manager server is running on `127.0.0.1:8765`.

### Open The Manager Server (live mode)

Run:

```bash
python3 scripts/skill_manager_server.py --open
```

The manager serves only on `127.0.0.1`. It stores its state, trash, and event log under `~/Desktop/SharedSkills/.skill-manager`.
Version knowledge-base records live under `~/Desktop/SharedSkills/.skill-manager/knowledge-base`.

To force the manager to open after a later apply:

```bash
python3 scripts/unify_agent_skills.py --mode apply --open-manager
```

### Add Custom Targets

When an agent stores skills somewhere unusual, pass explicit targets:

```bash
python3 scripts/unify_agent_skills.py --mode apply --only-targets --target "my-agent=/absolute/path/to/skills"
```

Multiple `--target` flags are allowed.

### Refresh This Skill in the Central Library

If the central library already has this skill, new agents must use that existing copy automatically. To deliberately replace the central copy with the current working copy, run:

```bash
python3 scripts/unify_agent_skills.py --mode apply --refresh-self
```

## Adjusting Skills for Reuse

When asked to "adjust skills" after unifying:

- Ensure every shared skill folder has a top-level `SKILL.md`.
- Keep the frontmatter to `name` and `description` unless the target agent explicitly needs more.
- Move agent-specific details into references or metadata files instead of duplicating whole skills.
- Keep instructions tool-agnostic where possible. Mention Codex-only, Claude-only, or other agent-specific steps only in clearly labeled sections.
- Validate the canonical shared skill in `~/Desktop/SharedSkills` first, then verify each target `skills` path resolves to that central folder.

For a more detailed migration checklist, read `references/skill-adjustment-playbook.md`.

## Resources

- `scripts/unify_agent_skills.py`: creates the Desktop central library, migrates existing skills, installs this skill into the library, and points each agent's whole `skills` directory to it.
- `scripts/build_manager.py`: generates a standalone HTML manager with all skill data embedded — open in any browser, no server needed.
- `scripts/skill_manager_server.py`: serves the local HTML manager and exposes local-only APIs for scanning, event logs, disable, enable, delete, and reveal.
- `assets/manager/index.html`: the manager HTML page (generated by `build_manager.py` or served by `skill_manager_server.py`).
- `references/product-requirements.md`: product requirements for the manager.
- `references/agent-paths.md`: common skill directory conventions and target selection guidance.
- `references/skill-adjustment-playbook.md`: checklist for converting scattered skills into reusable shared skills.
