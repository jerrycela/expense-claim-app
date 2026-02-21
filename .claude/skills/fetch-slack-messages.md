---
name: fetch-slack-messages
description: 批次抓取多個 Slack 頻道的訊息（含串內回覆）並彙整成 Markdown 文件
---

# Slack 訊息批次抓取 Skill

## 使用時機

當用戶要求：
- 抓取特定時間範圍的 Slack 訊息
- 從多個頻道批次抓取訊息
- 需要包含主訊息和串內回覆
- 需要將結果整理成文件

## 執行步驟

### 步驟 1：確認輸入資訊

**必要資訊**：
- 頻道列表文件路徑（或直接提供頻道 ID 列表）
- 時間範圍（例如：2026/2/2 ~ 2026/2/6）
- 時區（預設 UTC+8）

**詢問用戶**：
```
我需要以下資訊：
1. 頻道列表文件路徑（或直接告訴我頻道 ID）
2. 時間範圍（開始日期和結束日期）
3. 時區（預設 UTC+8）
4. 輸出格式（原始格式或美化格式）
```

### 步驟 2：讀取頻道列表

如果用戶提供文件路徑，使用 Read 工具讀取頻道列表文件並提取所有頻道 ID 和名稱。

### 步驟 3：計算正確的 Unix Timestamp

**重要**：Slack API 使用 UTC 時間的 Unix timestamp

**轉換公式**（以 UTC+8 為例）：
- 本地時間 2026/2/2 00:00:00 UTC+8 = UTC 時間 2026/2/1 16:00:00
- 本地時間 2026/2/6 23:59:59 UTC+8 = UTC 時間 2026/2/6 15:59:59

**Unix timestamp 計算方式**：
1. 計算基準日（2026-01-01 00:00:00 UTC）的 timestamp
2. 加上經過的天數 × 86400（秒/天）
3. 減去時區偏移（8小時 = 28800秒）

**範例**：
- 2026/2/2 00:00:00 UTC+8 → oldest: 1769961600
- 2026/2/6 23:59:59 UTC+8 → latest: 1770393599

**驗證時間戳**：
- 使用線上工具：https://www.unixtimestamp.com/
- 或使用命令：`date -r [timestamp]`

### 步驟 4：載入 Slack 工具

首先使用 ToolSearch 載入 Slack MCP 工具：
```
ToolSearch(query: "slack read channel")
```

這會載入：
- `mcp__claude_ai_Slack__slack_read_channel`
- `mcp__claude_ai_Slack__slack_read_thread`

### 步驟 5：並行啟動 Agent

**關鍵原則**：
- ✅ 每個頻道使用獨立的 agent
- ✅ 所有 agent 在同一個 message 中並行啟動
- ✅ 使用 Haiku 模型（快速且便宜）
- ✅ 每個 agent 的 prompt 包含完整的執行指令

**Agent Prompt 模板**：

```
請抓取 Slack 頻道 {CHANNEL_ID}（{部門名稱}）的所有訊息，時間範圍：{START_DATE} 00:00 至 {END_DATE} 23:59 (UTC+8)

## 時間戳轉換
- oldest: {OLDEST_TIMESTAMP} ({START_DATE} 16:00:00 UTC)
- latest: {LATEST_TIMESTAMP} ({END_DATE} 15:59:59 UTC)

## 任務步驟
1. 使用 mcp__claude_ai_Slack__slack_read_channel 抓取主頻道訊息
   - channel_id: {CHANNEL_ID}
   - oldest: "{OLDEST_TIMESTAMP}"
   - latest: "{LATEST_TIMESTAMP}"
   - limit: 100
   - response_format: "detailed"

2. 如果有分頁（next_cursor），繼續抓取直到完整

3. 針對有回覆的訊息（reply_count > 0），使用 mcp__claude_ai_Slack__slack_read_thread 抓取串內訊息
   - channel_id: {CHANNEL_ID}
   - message_ts: [訊息的 ts 值]

4. 將所有訊息整理成 markdown 格式

## 輸出格式
# {部門名稱} ({CHANNEL_ID})
時間範圍：{START_DATE} - {END_DATE}

## 主頻道訊息
[所有主頻道訊息，包含時間、發送者、內容]

## 串內討論
[所有 thread 訊息，按照原始訊息分組]

請完整執行並回傳結果。
```

**並行執行範例**：

在單一 message 中啟動所有 agent，每個頻道一個 Task call：

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  description: "抓取{部門}頻道訊息",
  prompt: [使用上述模板，替換所有變數]
)
```

### 步驟 6：等待所有 Agent 完成

所有 agent 會並行執行，等待全部完成後收集結果。

### 步驟 7：彙整結果

將所有 agent 回傳的結果彙整成單一 Markdown 文件：

```markdown
# Slack 訊息彙整報告

**時間範圍**：{START_DATE} ~ {END_DATE} (UTC+8)
**抓取日期**：{TODAY}
**涵蓋頻道**：{N} 個部門頻道

---

[依序貼上每個部門的訊息內容]
```

### 步驟 8：保存文件

使用 Write 工具將結果保存為 Markdown 文件：

**檔名建議**：
- 原始格式：`slack_messages_raw_{START_YYYYMMDD}-{END_YYYYMMDD}.md`
- 美化格式：`slack_messages_{START_YYYYMMDD}-{END_YYYYMMDD}.md`

**保存路徑**：當前工作目錄或用戶指定路徑

## 常見錯誤與解決方案

### 錯誤 1：時間戳計算錯誤

**症狀**：抓到錯誤年份的訊息（例如抓到 2025 年而非 2026 年）

**原因**：Unix timestamp 計算錯誤

**解決**：
1. 使用線上工具驗證時間戳
2. 確認是否正確減去時區偏移
3. 檢查年份計算（閏年會影響天數）

### 錯誤 2：沒有抓到串內訊息

**症狀**：只有主訊息，沒有 thread 回覆

**原因**：沒有檢查 `reply_count` 或沒有呼叫 `slack_read_thread`

**解決**：
- 確保 agent prompt 包含步驟 3（抓取 thread）
- 檢查訊息是否真的有回覆（`reply_count > 0`）

### 錯誤 3：Agent 執行時間過長

**症狀**：等待時間超過預期

**原因**：
- 頻道訊息量過大
- 串內訊息過多
- 網路延遲

**解決**：
- 使用 Haiku 模型（已最佳化）
- 考慮分批處理（減少時間範圍）
- 使用 `run_in_background: true`（如果不急）

### 錯誤 4：頻道 ID 錯誤

**症狀**：找不到頻道或無權限

**原因**：頻道 ID 不正確或 Slack 連線問題

**解決**：
- 使用 `slack_search_channels` 驗證頻道 ID
- 確認 Slack MCP 工具已正確設定
- 檢查是否有該頻道的存取權限

## 輸出格式選項

### 選項 1：原始格式（未美化）

**特色**：
- 保留 Slack 原始訊息結構
- 最小化格式調整
- 適合後續處理或分析

**結構**：
```markdown
## 頻道名稱 (ID)

### 主訊息
- 發送者：...
- 時間：...
- 內容：...

### 串內回覆
**回覆 1** | 時間 | 發送者
內容...
```

### 選項 2：美化格式

**特色**：
- 增加摘要和統計
- 分類整理工作內容
- 適合閱讀和報告

**結構**：
```markdown
## 頻道名稱

### 主要工作項目
- 項目 1
- 項目 2

### 統計資訊
- 總訊息數：...
- 參與者：...

### 詳細訊息
[按時間或主題分組]
```

## 進階功能

### 功能 1：過濾特定發送者

在 agent prompt 中加入：
```
只抓取以下發送者的訊息：{USER_ID_LIST}
```

### 功能 2：關鍵字搜尋

在 agent prompt 中加入：
```
只保留包含以下關鍵字的訊息：{KEYWORDS}
```

### 功能 3：自動摘要

在彙整步驟後，使用 AI 生成摘要：
```
請分析以上訊息，生成以下摘要：
1. 主要工作項目
2. 重要決策
3. 待辦事項
4. 風險或問題
```

## 效能優化建議

1. **模型選擇**：
   - 簡單抓取：Haiku（最快最便宜）
   - 需要分析：Sonnet
   - 複雜處理：Opus

2. **並行數量**：
   - 建議：10-15 個頻道並行
   - 超過 20 個頻道：考慮分批處理

3. **時間範圍**：
   - 建議：單次不超過 7 天
   - 超過 2 週：考慮分段抓取

4. **快取策略**：
   - 保存中間結果
   - 避免重複抓取相同頻道

## 完整執行檢查清單

在執行前確認：
- [ ] 已確認頻道 ID 列表
- [ ] 已計算正確的 Unix timestamp
- [ ] 已載入 Slack MCP 工具
- [ ] 已準備好 agent prompt 模板
- [ ] 已確認輸出格式（原始/美化）
- [ ] 已確認保存路徑

執行中監控：
- [ ] 所有 agent 都成功啟動
- [ ] 沒有 agent 回報錯誤
- [ ] 預估執行時間合理

執行後驗證：
- [ ] 所有頻道都有結果
- [ ] 時間範圍正確
- [ ] 包含主訊息和串內回覆
- [ ] 檔案已成功保存

## 範例完整流程

```python
# 假設：抓取 11 個頻道，2026/2/2 ~ 2026/2/6

# 步驟 1：讀取頻道列表
channels = [
    {"id": "C06T60YQBA9", "name": "企劃部門"},
    {"id": "C06SUE5RYB1", "name": "美術部門"},
    # ... 其他 9 個頻道
]

# 步驟 2：計算時間戳
oldest = "1769961600"  # 2026/2/2 00:00 UTC+8
latest = "1770393599"  # 2026/2/6 23:59 UTC+8

# 步驟 3：載入工具
ToolSearch(query: "slack read channel")

# 步驟 4：並行啟動 11 個 agent
for channel in channels:
    Task(
        subagent_type="general-purpose",
        model="haiku",
        description=f"抓取{channel['name']}訊息",
        prompt=generate_prompt(channel, oldest, latest)
    )

# 步驟 5：等待完成並彙整
results = collect_all_results()

# 步驟 6：保存檔案
Write(
    file_path="slack_messages_raw_20260202-20260206.md",
    content=format_results(results)
)
```

## 相關資源

- **Slack API 文檔**：https://api.slack.com/methods
- **Unix Timestamp 轉換**：https://www.unixtimestamp.com/
- **MCP Slack 工具說明**：使用 `ToolSearch` 查詢工具文檔

---

**Skill 版本**：1.0
**最後更新**：2026-02-10
**適用場景**：批次抓取 Slack 多頻道訊息
