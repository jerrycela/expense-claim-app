---
name: open-dashboard
description: Use when user wants to view the CMSI dashboard, check cron history, see project stats, or says "open dashboard", "show dashboard", "look at dashboard"
---

# Open CMSI Dashboard

Launch the Claude MD Self-Iteration (CMSI) dashboard locally.

## What It Does

Runs `scan.js` to refresh all data (global config, docs, skills, projects, cron history + AI insights), then starts Vite dev server and opens browser.

## Command

```bash
cd "/Users/admin/_dev-tools/claude-code/Claude md 自我迭代專案/dashboard" && npm run dashboard
```

Run in background so the conversation continues while the server stays up.

## Notes

- Server runs at `http://localhost:5173/`
- API key for AI insights is in `.env` (auto-loaded via dotenv)
- To refresh data without restarting: `npm run scan` in the same directory
- To stop: kill the background process
