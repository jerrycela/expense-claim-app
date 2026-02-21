# Performance Optimization

## 模型選擇策略

**Haiku 4.5**（輕量，3x 成本節省）：
- 頻繁調用的輕量 agents
- 簡單搜尋和探索任務
- 多 agent 系統中的 worker agents

**Sonnet 4.6**（最佳 coding 模型，Opus 等級的 coding 能力，Sonnet 定價）：
- 主要實作工作
- Coding agents 和 pair programming
- 複雜 coding 任務
- 協調多 agent 工作流程

**Opus 4.6**（最深推理能力）：
- 規劃和架構決策
- 程式碼審查和品質保證
- 最高推理需求
- 研究和分析任務

## Context Window 管理

避免在最後 20% context window 執行：
- 大規模重構
- 跨多檔案的功能實作
- 複雜交互的除錯

較低 context 敏感度的任務：
- 單一檔案編輯
- 獨立工具函式建立
- 文件更新
- 簡單 bug 修復

## Ultrathink + Plan Mode

複雜任務需要深度推理時：
1. 使用 `ultrathink` 強化思考
2. 啟用 **Plan Mode** 結構化方法
3. 多輪批評（"Rev the engine"）
4. 使用 split role sub-agents 進行多視角分析

## Build Troubleshooting

建置失敗時：
1. 使用 **build-error-resolver** agent
2. 分析錯誤訊息
3. 逐步修復
4. 每次修復後驗證
