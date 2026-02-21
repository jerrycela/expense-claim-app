# Notify Slack

將重要結論推送到 n8n-測試 頻道（C08D74G1ZG8）。

## 使用方式

當你完成一個重要任務、得出重要結論、或有需要同步的資訊時，使用此 skill 推送通知。

## 指令

使用 Slack MCP 工具 `mcp__slack__slack_post_message` 發送訊息：
- channel_id: C08D74G1ZG8
- text: 格式化的訊息內容

## 訊息格式

```
*[Claude Code 通知]*

$ARGUMENTS
```

如果沒有提供 $ARGUMENTS，請根據當前對話的上下文，摘要最近完成的重要結論或任務。

## 執行

立即使用 `mcp__slack__slack_post_message` 工具發送訊息到頻道 C08D74G1ZG8。
