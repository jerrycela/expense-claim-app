# Git Workflow

## Commit 訊息格式

```
<type>: <description>

<optional body>
```

**類型**：`feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`

**注意**：Attribution 已透過 `~/.claude/settings.json` 全域停用。

## 每次 commit 必須

- 成功編譯
- 通過所有既有測試
- 新功能附帶測試
- 遵循專案格式化/linting 規範
- Commit 訊息解釋「為什麼」而非「做了什麼」

## Pull Request 工作流程

1. 分析完整 commit 歷史（不只最新 commit）
2. 使用 `git diff [base-branch]...HEAD` 查看所有變更
3. 撰寫詳盡的 PR 摘要
4. 包含測試計畫與 TODO 清單
5. 若是新分支，使用 `-u` flag 推送

## 功能實作工作流程

1. **先規劃** — 使用 planner agent，拆解為階段，識別風險
2. **TDD** — 先寫測試 → 最小實作 → 重構 → 驗證 80%+ 覆蓋率
3. **程式碼審查** — 完成後立即使用 code-reviewer agent
4. **程式碼精煉** — 審查通過後使用 code-simplifier agent，簡化程式碼結構、消除冗餘、提升可讀性（不改變功能）
5. **Commit** — 遵循 conventional commits 格式
