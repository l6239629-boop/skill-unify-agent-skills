# SharedSkills Manager Product Requirements

## Goal

Provide a local visual manager for the Desktop `SharedSkills` library so users can see every available skill, understand recent additions, deletions, disables, enables, and modifications, keep a knowledge-base version history for each skill, and safely remove or disable skills without leaving the shared library manually.

## Users

- A user running multiple local agents that all point to `~/Desktop/SharedSkills`.
- An agent helping the user maintain the shared Skill library.

## Core Experience

1. First use of `unify-agent-skills` creates or confirms `~/Desktop/SharedSkills`.
2. The skill automatically starts a local manager and opens it in the browser.
3. The manager shows all active and disabled skills in one searchable list.
4. The manager records skill add, modify, disable, enable, and delete events.
5. The manager records each skill version into a local knowledge base with change points.
6. The manager supports Chinese and English display.
7. The user can disable, enable, or delete a skill from the manager.
8. Operations preserve recoverability by moving files into manager-controlled storage instead of permanently erasing them.

## Functional Requirements

- Discover active skills by locating directories with `SKILL.md` under `SharedSkills`.
- Include nested skill collections such as `.system/imagegen`.
- Exclude manager internals: `.skill-manager`, `.disabled`, `.backups`, and OS noise.
- Read `name` and `description` from `SKILL.md` frontmatter when available.
- Show path, status, modified time, file count, and approximate size for each skill.
- Group nested skills by their top-level folder so a large project can collect smaller skill projects under one folder heading.
- Show root-level skills under a `SharedSkills` root folder group.
- Detect changes by scanning file metadata and content hashes.
- Append all detected and user-triggered events to `.skill-manager/events.jsonl`.
- Store the latest scan state in `.skill-manager/state.json`.
- Store per-skill version history in `.skill-manager/knowledge-base/<encoded-skill-id>/versions.jsonl`.
- Create an initial version record for every discovered skill.
- Create a new version when a skill hash or status changes.
- Record change points including status changes, name changes, description changes, added files, removed files, and modified files.
- Disable a skill by moving it from its active path to `.disabled/<encoded-id>` and recording its original path.
- Enable a skill by moving it back to its original path when the destination is available.
- Delete a skill by moving it to `.skill-manager/trash/<timestamp>-<encoded-id>`.
- Protect the manager skill itself from disable/delete by default.
- Protect `.system` skills from UI deletion by default, because they are platform-provided capabilities.
- Provide a Chinese display mode for UI labels, statuses, event types, and version change-point summaries.

## Non-Goals

- Editing skill file contents in the browser.
- Publishing to GitHub.
- Cross-device sync.
- Authentication for remote network access. The server binds to `127.0.0.1` only.

## Local Control Model

The HTML frontend cannot safely mutate the local filesystem by itself, so it is served by `scripts/skill_manager_server.py`. The server exposes local-only JSON endpoints for scanning, event retrieval, disable, enable, delete, and open-in-Finder convenience actions.

## Acceptance Criteria

- Running `python3 scripts/skill_manager_server.py --open` starts a local server and opens the manager.
- The manager lists `unify-agent-skills` and the Codex `.system` skills when present.
- Adding, editing, disabling, enabling, or deleting a skill writes an event record.
- Skill scans create version records under `.skill-manager/knowledge-base`.
- The manager can switch between Chinese and English display.
- Disable and delete operations do not permanently remove files.
- Re-running `scripts/unify_agent_skills.py --mode apply` opens the manager automatically the first time unless `--no-open-manager` is used.
