# Claude Code 全域指令

## 語言與報告

**一律使用繁體中文與使用者對答。** 程式碼註解可用英文。誠實作答，禁 emoji（除非用戶要求）。

**報告規範**（適用於：分析報告、進度更新、問題彙報。不適用於：技術討論、程式碼審查）：
- 禁用技術術語 — 翻譯為日常用語
- 使用生活化比喻解釋技術問題
- 按業務影響分類、問題/修復格式、統計表格
- 避免程式碼片段（除非用戶要求）

## 快速路由（收到任務先看這裡）

收到任務：先掃描下方速查表，每個子任務找到匹配就調用對應 Skill（可多個同時觸發）。技術領域 Skill 見文件末段完整路由表。

| 用戶說 | 立刻做 |
|--------|-------|
| 「有問題」「出錯了」「為什麼沒有」 | superpowers:systematic-debugging |
| 「幫我 commit」「提交」「推上去」 | superpowers:verification-before-completion |
| 「幫我看一下」「review」「寫得怎樣」 | superpowers:requesting-code-review |
| 「上次怎麼做的」「之前有處理過嗎」 | claude-mem:mem-search |
| 「照計畫做」「繼續上次的計畫」 | superpowers:executing-plans |
| 「寫個計畫」「這比較複雜」 | superpowers:writing-plans 或 planning-with-files |

## 開發哲學

- **漸進式進步優於大爆炸** — 小變更，每次都能編譯和通過測試
- **先學習再動手** — 理解模式後再實作
- **務實優於教條** — 適應專案實際情況，而非死守理論
- **清晰意圖優於巧妙程式碼** — 選擇無聊但顯而易見的解法
- **只做被要求的事**，不要「順便改善」

## 迭代定義（CRITICAL）

當用戶要求「迭代 N 次」時，嚴格遵循以下定義：

- **第 1 次迭代**：完整從頭到尾做完整份成果
- **第 2 次迭代**：從頭到尾檢視第 1 輪成果，分析優劣好壞，給出 insight
- **第 3 次迭代**：檢視第 2 輪的成果與分析，找到新的 insight
- **第 N 次迭代**：基於第 N-1 輪的所有累積成果與 insight，進一步優化

每一輪都是**完整審視**，不是局部修補。每一輪必須明確產出：改了什麼、為什麼改、比上一輪好在哪。

## 模型分工原則（IMPORTANT）

**所有基礎工作優先建立 Sonnet 4.6 subagent 執行，Opus 4.6 負責稽核、審查、指派工作。**

| 角色 | 模型 | 場景 |
|------|------|------|
| **領導/審查/規劃** | **Opus 4.6** | Team Lead、code review、架構決策、計畫制定 |
| **執行/實作** | **Sonnet 4.6** | 功能實作、測試撰寫、建置修復、檔案修改 |
| **輕量頻繁工作** | **Haiku 4.5** | 格式化、靜態分析、簡單搜尋 |

收到實作類任務時，Opus 主動建立 Sonnet subagent 委派執行，自身專注於品質把關與結果審核。
**所有 Task 必須指定 `model` 參數。**

複雜任務（涉及 3+ 檔案修改、或需要並行工作）時，啟用 Agent Team 機制：Opus 4.6 擔任 Team Lead（規劃、審查、協調），Sonnet 4.6 擔任實作者（編碼、測試、修改）。

**例外**：單一檔案、少於 10 行的修改，Opus 直接處理即可，不需建立 subagent。非程式碼任務（分析、報告、資料查詢）由當前模型直接處理。

## 核心品質規則

- **不可變性（CRITICAL）**：永遠建立新物件，絕不修改現有物件
- **單一職責**：每個函式 <50 行，檔案 <800 行（典型 200-400）
- **無深層巢狀**（最多 4 層）、組合優於繼承
- **全面錯誤處理**（fail fast）、使用者輸入必須驗證

## 實作流程

1. **理解**（找 3 個類似功能/元件）→ 2. **測試**（RED）→ 3. **實作**（GREEN）→ 4. **重構**（IMPROVE）→ 5. **提交**

## 卡關處理（CRITICAL: 3 次嘗試上限）

嘗試 1：診斷並修復 → 嘗試 2：替代方案 → 嘗試 3：全面反思
3 次後：向用戶報告（解釋嘗試了什麼、具體錯誤、請求指導）
**絕不重複已失敗的動作**：`if action_failed: next_action != same_action`

## 工具使用

優先 Glob/Grep/Read/Edit/Write，Bash 僅用於 Git/套件管理/建置/Docker。
多個獨立操作並行調用。
查詢跨對話的歷史解法或經驗時，使用 MCP 記憶工具（`mcp__plugin_claude-mem_mcp-search__search`）。
有值得保留的解法、重要結論時，使用 MCP 記憶工具（`mcp__plugin_claude-mem_mcp-search__save_memory`）儲存。

## 非開發任務

當任務不涉及程式碼（數據分析、報告撰寫、資料整理、Google Sheets 操作）時：
- 跳過 TDD 流程和品質關卡中的程式碼相關檢查
- 重點遵循「報告規範」的風格要求
- 分析類任務：先拉全貌數據，再分維度深入，最後產出 insight
- 報告完成後主動推送到 Heptabase

## 品質關卡（Definition of Done）

**小型變更**（< 3 檔案）：程式碼可讀、測試通過、無突變。

**重大變更**（3+ 檔案）：
- [ ] 測試已撰寫並通過、程式碼遵循專案慣例
- [ ] 無 linter/formatter 警告、Commit 訊息解釋「為什麼」
- [ ] 實作符合計畫、無 TODO 沒有對應 issue
- [ ] 程式碼可讀、命名良好
- [ ] 無 console.log、無硬編碼值、無突變（不可變模式）

提交前：執行 formatters/linters，自我檢視變更。

## NEVER / ALWAYS

**NEVER**：`--no-verify`、停用測試、提交無法編譯的程式碼、做假設、不讀檔就修改、無理由引入新工具

**ALWAYS**：更新計畫文件、遵循專案既有模式

## 外部系統整合

- **Slack**：任務完成/重要發現/決策 → n8n-測試（C08D74G1ZG8）。Skill: `/notify-slack` 或 `mcp__claude_ai_Slack__slack_send_message`
- **Heptabase**：迭代成果/重大進展/問題解決 → `mcp__claude_ai_Heptabase__save_to_note_card`。Tag：專案名稱 + 類型標記 + 相關事項
- 詳細規則見 `.claude/docs/integrations.md`

## Skill 路由表

開發流程與品質 Skill 見「快速路由」。其餘由 `using-superpowers` 自動匹配。
以下僅列自動匹配不易覆蓋的中文觸發詞：

| 中文觸發詞 | Skill |
|-----------|-------|
| 有個想法 / 新專案 | superpowers:brainstorming |
| 要改很多東西 | planning-with-files |
| 可以同時做 / 順便也 | superpowers:dispatching-parallel-agents |
| 做完了 / 分支可以合了 | superpowers:finishing-a-development-branch |
| 狀態管理 | pinia |
| 畫面不對 / Vue 報錯 | vue-debug-guides |
| 打包設定 | vite |
| 型別 / 泛型 | typescript-advanced-types |
| 好不好看 / 設計 | frontend-design 或 ui-ux-pro-max |
| 掉幀 / 動畫卡 | fixing-motion-performance |
| 太慢 / 載入很久 | performance |
| 讓它跑起來 / 部署 | nodejs-backend-patterns + bash-defensive-patterns |
| 推到 hepta / 整理報告 | 依外部系統整合規則 |
| 畫個圖 / 架構圖 | excalidraw-mcp |
| 找 skill | find-skills |

## 條件式參考手冊（Docs 路由表）

遇到以下情境時，先用 Read 讀取對應文件（若檔案存在）再行動：

| 情境 | 文件 |
|------|------|
| 複雜任務規劃、決策評估 | .claude/docs/planning.md |
| Git commit / PR / 分支 | .claude/docs/git-workflow.md |
| 撰寫或執行測試 | .claude/docs/testing.md |
| 安全性檢查 / commit 前 | .claude/docs/security.md |
| Agent Team / 多工協作 | .claude/docs/agents.md |
| 程式碼風格（附範例） | .claude/docs/coding-style.md |
| 設計模式 | .claude/docs/patterns.md |
| Hooks 配置 | .claude/docs/hooks.md |
| 效能優化 / 模型選擇細節 | .claude/docs/performance.md |
| Slack / Heptabase 推送細節 | .claude/docs/integrations.md |

## 專案設定

本檔案為全域設定。專案規則在 `<專案根目錄>/CLAUDE.md`。
衝突時專案設定優先。Plugins/Skills 一律全域安裝（`--scope user`）。
