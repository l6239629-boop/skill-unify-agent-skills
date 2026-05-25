# Skill Adjustment Playbook

Use this checklist when converting scattered agent-specific skills into a shared library.

## 1. Inventory

- List every skill folder in each target agent directory.
- Record duplicate skill names and compare their `SKILL.md` files.
- Identify generated caches and vendor imports; do not make those the canonical source.

## 2. Choose Canonical Copies

- Prefer the newest intentional user-edited version.
- Prefer a complete skill folder over a partial metadata-only folder.
- Preserve useful agent-specific metadata in side files rather than discarding it.
- When two versions diverge meaningfully, create a merged shared version and keep backups of both originals.

## 3. Normalize Structure

Each shared skill should normally look like:

```text
skill-name/
  SKILL.md
  agents/openai.yaml        # optional, Codex UI metadata
  scripts/                  # optional
  references/               # optional
  assets/                   # optional
```

Keep the folder name and frontmatter `name` aligned. Use lowercase letters, digits, and hyphens for shared skill names.

## 4. Make Instructions Portable

- Put the general workflow first.
- Label agent-specific instructions with headings such as `Codex`, `Claude Code`, or `Gemini`.
- Avoid hard-coded absolute paths inside reusable instructions unless they are examples.
- Store long examples, schemas, or detailed notes under `references/` and link to them from `SKILL.md`.

## 5. Synchronize

- Use `~/Desktop/SharedSkills` as the central source unless the user gives another path.
- Move retained skills from each agent's old `skills` folder into the central folder.
- Preserve hidden skill collections such as `.system` when they contain real skills.
- Back up each old `skills` folder after migration.
- Replace each old `skills` folder with a symlink to the central folder.
- Re-run the plan after synchronization to confirm every target points to the central folder.

## 6. Validate

- Check that every shared skill has readable frontmatter with `name` and `description`.
- For Codex skills, run the available `quick_validate.py` validator.
- Ask at least one target agent to use a synchronized skill on a small task.
- If a target agent does not discover symlinked skills, document that agent as a fallback exception and copy the central folder contents only for that target.
