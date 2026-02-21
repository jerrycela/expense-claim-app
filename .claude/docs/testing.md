# Testing Requirements

## 最低測試覆蓋率：80%

測試類型（全部必要）：
1. **單元測試** — 個別函式、工具、元件
2. **整合測試** — API 端點、資料庫操作
3. **E2E 測試** — 關鍵使用者流程（Playwright）

## Test-Driven Development（必要流程）

1. 先寫測試（RED） — 測試應該 FAIL
2. 最小實作（GREEN） — 通過測試
3. 重構（IMPROVE） — 在測試通過前提下清理
4. 驗證覆蓋率（80%+）

## 測試原則

- 測試行為，而非實作細節
- 每個測試一個斷言（盡可能）
- 清晰的測試名稱描述場景
- 使用既有的測試工具/helper
- 測試必須是確定性的（deterministic）
- 修復實作，而非測試（除非測試有誤）

## Troubleshooting 測試失敗

1. 使用 **tdd-guide** agent
2. 檢查測試隔離性
3. 驗證 mocks 是否正確
4. 修復實作，而非測試（除非測試有誤）

## Agent 支援

- **tdd-guide** — 新功能開發時主動使用，強制 write-tests-first
- **e2e-runner** — Playwright E2E 測試專家
