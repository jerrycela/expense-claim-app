---
description: "Create a task handoff for web version Claude Code to pick up. Usage: /handoff <task description>"
---

# Task Handoff — Local → Web

You are creating a task handoff file so that web version Claude Code can pick up and execute the work.

## Instructions

1. Read the user's task description from `$ARGUMENTS`
2. Read the existing `.claude/handoff.md` file if it exists (to append, not overwrite)
3. Add a new task entry to `.claude/handoff.md` using this format:

```markdown
## Task: [SHORT TITLE]
- **Status**: pending
- **Created**: [YYYY-MM-DD HH:MM]
- **Created by**: local
- **Description**: [FULL TASK DESCRIPTION]
- **Context**: [Any relevant file paths, branch info, or context the web version needs]
- **Acceptance criteria**: [What "done" looks like]

---
```

4. If the file doesn't exist, create it with this header first:

```markdown
# Claude Code Handoff Tasks

Tasks created by local Claude Code for web version to pick up.
When picking up a task, change status to `in_progress`.
When done, change status to `completed` and add a summary.

---
```

5. After writing, tell the user:
   - The task has been added to `.claude/handoff.md`
   - They need to `git add .claude/handoff.md && git commit -m "handoff: [task title]" && git push`
   - Or offer to commit and push for them

6. Be thorough in the Context section — the web version has no conversation history from this session.
