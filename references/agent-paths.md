# Agent Skill Paths

Use these paths as discovery hints, not as universal truth. Prefer existing directories on the user's machine, explicit user-provided paths, and project documentation over assumptions.

## Common Local Targets

- Codex: `~/.codex/skills`
- Claude Code: `~/.claude/skills`
- Cursor: `~/.cursor/skills`
- Gemini CLI: `~/.gemini/skills`
- OpenClaw: `~/.openclaw/skills`
- OpenCode: `~/.opencode/skills`
- Qoder: `~/.qoder/skills`
- Qwen Code: `~/.qwen/skills`
- Trae: `~/.trae/skills`
- Project-scoped agents: `<repo>/.agents/skills`, `<repo>/.codex/skills`, or `<repo>/.claude/skills` when the user asks for project-local behavior

## Target Selection

Use a target when:

- The directory already exists and contains skill-like folders.
- The parent configuration directory exists and the user asked to include that agent.
- The user explicitly provides the path.

Skip a target when:

- Neither the target nor its parent exists.
- It would create a new configuration tree for an agent the user may not use.
- The target appears to be a generated cache, vendor import, or plugin cache rather than a user-editable skill directory.

## Required Link Model

The target experience is directory-level symlinking:

```bash
ln -s ~/Desktop/SharedSkills ~/.claude/skills
ln -s ~/Desktop/SharedSkills ~/.codex/skills
```

The central folder is the real storage location. Each agent's `skills` path is only an entry point into that same folder. This is what makes new skills auto-collect into the shared library and appear across agents immediately.

Use copies only as an explicit fallback when a target agent cannot follow symlinks.
