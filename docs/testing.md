# 測試策略

## 離線自動驗證

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

涵蓋有效座標邊界、超界與非有限數字、布林值／字串、設定清除循環、
可能部分寫入後斷線、清除失敗再試、idle 與重複清除、負座標 CLI 解析、
指令計畫不執行、缺參數與非法輸入退出碼。
這些 23 個測試確認軟體契約，不驗證 Apple 協定、裝置位置或遊戲接受程度。
標準函式庫即可執行；不下載依賴、不連網。

## 之後的 adapter 測試

使用假的 process / transport 測試：找不到工具、版本不合、多台裝置、
配對拒絕、Developer Mode 關閉、set 部分成功、斷線、取消、clear 逾時、
程序重啟後 unknown 狀態恢復。測試必須涵蓋清理失敗的真實分支。

## Mac + iPhone 手動驗收

1. 記錄日期、Mac OS、iPhone 型號、iOS build、上游版本與 commit。
2. 確認擁有的測試裝置與信任配對；檢查 Developer Mode / 開發者映像。
3. 先用系統地圖或自己的 Core Location 測試 App 記錄基準位置。
4. 選一個測試座標，執行 set，記錄後端回應與獨立觀測結果。
5. 保持工作階段、切換前景、等待，觀察行為；不可假設拔線仍有效。
6. clear，獨立確認真實位置恢復；失敗標示 unknown，保留診斷並重試。
7. 測試中斷／USB 斷線／重連／程序關閉；每次均確認恢復。
8. 全部結果只適用測過的組合；未知組合一律標成 unverified。

### 2026-11-11：單點真機驗收（部分完成）

- 已確認：已信任 USB 裝置可由 pymobiledevice3 11.52.1 列出；Developer Mode 為開啟；
  userspace DVT 的只讀 sysmon 服務可開啟。
- 已確認：一次 `simulate-location set` 工作階段至少仍存活於第 20 秒；另一次 set 已由 Google Maps
  獨立觀察到藍點跳至公開測試點。
- 已確認：停止殘留的 set 工作階段後，以維持 DVT 連線的 clear 輔助程式送出清除；Google Maps
  隨後重新顯示測試前基準位置的藍點，且沒有遺留的 location-simulation 程序。
- 已發現：clear selector 不提供裝置回覆，且殘留 set 工作階段會干擾恢復判讀；因此「clear 命令返回」
  本身仍一律標示 unverified。
- 未確認：set 是否完整持續 30 秒，以及拔線、鎖屏、重連、程序強制終止下的恢復。
- 不記錄：UDID、配對資料、真實位置、測試座標或裝置畫面。

| 環境 | 核心自動測試 | 設定真機位置 | 清除真機位置 |
| --- | --- | --- | --- |
| 此 Linux 工作空間 / Python 3.12 | 見 validation.md | 未執行 | 未執行 |
| 測試用的 Mac + iPhone（iOS 27.2） | USB / Developer Mode / DVT read-only 已驗證 | 工作階段 20 秒存活；Google Maps 單點觀測成功；持續性待測 | 清除後 Google Maps 基準位置恢復、且無殘留模擬程序已觀測；故障矩陣待測 |
