---
description: 一鍵啟動翻譯品質提升三合一工作流 — 結合 Prompt 工程、Agent 評估、自我改善三大 Skill
argument-hint: [目標語言或具體改善方向]
---

# Translation Quality Boost - 翻譯品質三合一提升

<!-- NOTE: 此 command 中「相關資源」區塊的路徑（~/翻譯工作流/）為本機專屬路徑，
     在其他機器上不存在。使用前請確認相關目錄存在，或更新為正確路徑。 -->

一次調用三個 Skill，系統性提升翻譯品質與 CVP（持續驗證改善）方法論。

## 三大 Skill 對應角色

| 順序 | Skill | 在翻譯流程中的角色 |
|------|-------|-------------------|
| 1 | `prompt-engineering-patterns` | 優化翻譯 Prompt — 讓 AI 翻得更準 |
| 2 | `customaize-agent-agent-evaluation` | 評估翻譯 Agent 表現 — 知道哪裡不夠好 |
| 3 | `self-improve-prompt-design` | 設計自我改善迴圈 — 讓系統越用越好 |

## 執行流程

收到此指令後，依序執行以下三個階段。每個階段使用對應的 Skill 工具。

### Phase 1: Prompt 工程優化

**調用 Skill：** `prompt-engineering-patterns`

針對翻譯場景，運用以下 Prompt 工程模式：

1. **Few-Shot 動態選例**：從 learnings JSONL 中挑選語義最接近的翻譯範例
2. **Chain-of-Thought 自我驗證**：讓翻譯 Agent 先分析原文語境，再翻譯，最後自我檢查
3. **結構化輸出**：確保翻譯結果格式一致、可解析
4. **漸進式提示**：根據文本複雜度動態調整 prompt 層級
5. **錯誤復原**：翻譯失敗時的 fallback 策略

**產出**：優化後的翻譯 Prompt 模板或改善建議

### Phase 2: Agent 表現評估

**調用 Skill：** `customaize-agent-agent-evaluation`

用多維度評量標準評估翻譯 Agent：

1. **指令遵循度**：是否正確套用 learnings 規則
2. **完整性**：是否翻譯了所有內容，無遺漏
3. **推理品質**：上下文理解、語境判斷是否合理
4. **一致性**：同一術語/角色名是否前後一致
5. **自然度**：譯文是否流暢自然（非機翻感）

**評估方法**：
- 抽樣已完成翻譯進行 LLM-as-Judge 評分
- 與人工校對版本比對（若有 snapshots）
- 識別偏差模式（長度偏差、位置偏差、風格偏差）

**產出**：評估報告 + 具體改善方向

### Phase 3: 自我改善迴圈設計

**調用 Skill：** `self-improve-prompt-design`

基於 Phase 1 和 Phase 2 的發現，設計或更新翻譯系統的自我改善機制：

1. **Git Diff 條件檢查**：只處理有變更的 learnings 檔案
2. **Learnings 驗證**：檢查 JSONL 規則是否仍然準確
3. **規則衝突偵測**：找出矛盾的翻譯規則
4. **行數限制**：確保 learnings 檔案不會無限膨脹
5. **信任度調整**：根據校對回饋調整 confidence 等級

**產出**：更新後的自我改善 prompt 或 learnings 維護建議

## 綜合報告

三個階段完成後，產出一份綜合報告：

```markdown
## 翻譯品質提升報告

### 1. Prompt 優化
- 改善了哪些 prompt 模式
- 預期影響

### 2. Agent 評估結果
- 各維度分數
- 主要弱項

### 3. 自我改善建議
- Learnings 健康度
- 建議的迴圈調整

### 4. 下一步行動
- 優先處理事項
- 預計改善幅度
```

## 參數說明

- `$ARGUMENTS`：可指定目標語言（ko/ja/en/zh-CN）或具體改善方向
  - 範例：`/translation-quality-boost ko` — 專注韓文翻譯品質
  - 範例：`/translation-quality-boost 術語一致性` — 專注術語一致性問題
  - 無參數時：全面檢視所有語言

## 相關資源

<!-- WARNING: 以下路徑為本機專屬（~/翻譯工作流/），在其他機器上不存在 -->
- 翻譯工作流設定：`~/翻譯工作流/CLAUDE.md`
- Learnings 目錄：`~/翻譯工作流/learnings/`
- 翻譯 Agent：`~/翻譯工作流/.claude/agents/translator.md`
- 學習 Agent：`~/翻譯工作流/.claude/agents/learner.md`
