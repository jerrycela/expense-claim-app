# Agent Orchestration

## 模型角色分配（CRITICAL）

| 角色類型 | 模型 | 適用場景 |
|---------|------|---------|
| **領導 / 審查 / 檢核** | **Opus 4.6** | Team Lead、程式碼審查、架構決策、安全檢核、計畫制定 |
| **執行 / 實作** | **Sonnet 4.6** | 功能實作、檔案修改、建置測試、程式碼搜尋 |
| **輕量工作** | **Haiku 4.5** | 頻繁調用的簡單任務、格式化、靜態分析 |

**所有 Task 必須明確指定 `model` 參數**。

## Agent Team 標準架構

```
Team Lead（Opus 4.6）
├── 制定計畫、分配任務、品質把關、最終審核
├── code-reviewer（Opus 4.6）— 程式碼審查、安全審查
└── implementer（Sonnet 4.6）— 功能實作、測試撰寫、建置修復
```

## 何時啟用 Agent Team（符合任一即啟用）

- 涉及 3+ 個獨立子任務可並行
- 跨多個模組或檔案的實作工作
- 需要實作 + 測試 + 審查等多角色協作
- 程式碼審查、安全審查、架構評估等深度分析工作

**單一 Task 工具**僅用於：單一明確查詢、簡單程式碼搜尋、不需跨角色協作的輕量任務。

## 主動啟用規則（無需用戶提示）

1. 收到複雜功能需求 → 立即 **TeamCreate**，分配 planner（Opus 4.6）制定計畫
2. 完成實作 → 分配 **code-reviewer（Opus 4.6）** 審查
3. code-reviewer 通過 → 分配 **code-simplifier（Sonnet 4.6）** 精煉
4. 遇到架構決策 → 分配 **architect（Opus 4.6）** 評估
5. 建置失敗 → 分配 **build-error-resolver（Sonnet 4.6）** 修復

## Task 工具使用規範

- 在單一訊息中發送多個 Task tool calls 以實現並行
- 使用 `run_in_background: true` 執行長時間任務

## 並行任務執行

ALWAYS 為獨立操作使用並行 Task 執行：

```markdown
# GOOD: 並行執行
同時啟動 3 個 agents：
1. Agent 1: auth.ts 安全分析
2. Agent 2: cache 系統效能審查
3. Agent 3: utils.ts 型別檢查

# BAD: 不必要的循序執行
先 agent 1，再 agent 2，再 agent 3
```

## 多視角分析

複雜問題使用 split role sub-agents：
- Factual reviewer
- Senior engineer
- Security expert
- Consistency reviewer
- Redundancy checker
