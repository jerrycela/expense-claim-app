# Security Guidelines

## 必要安全檢查（每次 commit 前）

- [ ] 無硬編碼機密（API keys, passwords, tokens）
- [ ] 所有使用者輸入已驗證
- [ ] SQL injection 防護（parameterized queries）
- [ ] XSS 防護（sanitized HTML）
- [ ] CSRF protection 已啟用
- [ ] 身份認證/授權已驗證
- [ ] 所有端點已設定 Rate limiting
- [ ] 錯誤訊息不洩漏敏感資料

## Secret Management

```typescript
// NEVER: 硬編碼機密
const apiKey = "sk-proj-xxxxx"

// ALWAYS: 環境變數
const apiKey = process.env.OPENAI_API_KEY

if (!apiKey) {
  throw new Error('OPENAI_API_KEY not configured')
}
```

## 安全回應流程

發現安全問題時：
1. **立即停止** 當前工作
2. 使用 **security-reviewer** agent 評估
3. 修復所有 **CRITICAL** 問題後才繼續
4. **輪換**任何已暴露的機密
5. 審查整個 codebase 是否有類似問題
