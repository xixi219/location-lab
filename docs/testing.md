# 測試策略

## 離線自動驗證

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

涵蓋有效座標邊界、超界與非有限數字、布林值／字串、設定清除循環、
可能部分寫入後斷線、清除失敗再試、idle 與重複清除、負座標 CLI 解析、
指令計畫不執行、缺參數與非法輸入退出碼。
這些測試確認軟體契約，不驗證 Apple 協定、裝置位置或遊戲接受程度。
標準函式庫即可執行；不下載依賴、不連網。

## 之後的 adapter 測試

使用假的 process / transport 測試：找不到工具、版本不合、多台裝置、
配對拒絕、Developer Mode 關閉、set 部分成功、斷線、取消、clear 逾時、
程序重啟後 unknown 狀態恢復。測試必須涵蓋清理失敗的真實分支。

## Mac + iPhone 手動驗收（全部尚未執行）

1. 記錄日期、Mac OS、iPhone 型號、iOS build、上游版本與 commit。
2. 確認擁有的測試裝置與信任配對；檢查 Developer Mode / 開發者映像。
3. 先用系統地圖或自己的 Core Location 測試 App 記錄基準位置。
4. 選一個測試座標，執行 set，記錄後端回應與獨立觀測結果。
5. 保持工作階段、切換前景、等待，觀察行為；不可假設拔線仍有效。
6. clear，獨立確認真實位置恢復；失敗標示 unknown，保留診斷並重試。
7. 測試中斷／USB 斷線／重連／程序關閉；每次均確認恢復。
8. 全部結果只適用測過的組合；未知組合一律標成 unverified。

| 環境 | 核心自動測試 | 設定真機位置 | 清除真機位置 |
| --- | --- | --- | --- |
| 此 Linux 工作空間 / Python 3.12 | 見 validation.md | 未執行 | 未執行 |
| 測試用的 Mac + iPhone | 待測 | 待測 | 待測 |
