---
description: "Pick up and execute handoff tasks from local Claude Code. Reads .claude/handoff.md for pending tasks."
---

# Task Pickup — Web picks up from Local

You are on the web version of Claude Code, picking up tasks that the local version created.

## Instructions

1. Read `.claude/handoff.md` in the current repo
2. If the file doesn't exist or has no pending tasks, tell the user "No pending handoff tasks found."
3. For each task with **Status: pending**:
   - Show the task to the user with its full description and context
   - Ask if they want you to execute it
4. When the user confirms:
   - Change the task status to `in_progress` in the handoff file
   - Execute the task following the description and acceptance criteria
   - When done, change status to `completed` and add:
     ```
     - **Completed**: [YYYY-MM-DD HH:MM]
     - **Completed by**: web
     - **Summary**: [What was done, key files changed]
     ```
5. After completing, commit the changes (both the task work AND the updated handoff.md)
6. Push so the local version can see the results

## Important

- Read the Context section carefully — it contains info you need since you don't have the local session's conversation history
- Follow the Acceptance criteria to know when the task is truly done
- If a task is unclear or blocked, change status to `blocked` and add a note explaining why
