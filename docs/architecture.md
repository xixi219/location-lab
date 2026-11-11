# 架構與決策 ADR-001

狀態：暫定採用；日期：2026-11-07。
目標：可診斷、可清除、可維護的位置模擬工具。暫不處理路線、自動化遊戲或 IP 出口。

## 選型

| 方案 | 優點 | 代價／未知 | 決策 |
| --- | --- | --- | --- |
| Mac companion + pymobiledevice3 adapter | 後端已有 DVT set/clear；可獨立測試業務邏輯 | 需手機配對、版本驗證、長連線管理與 GPL 決策 | 優先技術驗證 |
| WLoc Swift fork | 現有 iOS/macOS UI、恢復機制可研究 | 代理信任鏈受近期變更影響；簽名、憑證、授權依賴 | 保留研究，不作 MVP 基礎 |
| 網頁控制面 + 本機 companion | 手機友善 UI，可共用核心 | 瀏覽器本身不能替代裝置通道；需本機服務安全設計 | 後續階段 |
| 原生 Swift UI + adapter | macOS 整合好 | 目前無 Mac 可建置驗證；維護另一工具鏈 | 真機可行後再決定 |

## 分層

目前實作：CLI → Coordinate / Session → Backend protocol → MemoryBackend。
另有獨立 planner：驗證輸入 → 輸出 DVT argv JSON → 結束（不啟動 process）。

下一階段：UI → application service → device adapter → trusted iPhone developer services。
UI 不直接拼接 shell 字串，不取得 pairing secrets。裝置 adapter 負責指定裝置、
版本檢查、工作階段、有限時間等待、取消與清除重試。核心不依賴 pymobiledevice3。

## 狀態契約

- idle：這個 session 尚未做操作；不能推論裝置真實位置。
- active：後端已接受 set。mock 代表記憶體已設定；未來真機也只代表指令成功。
- cleared：後端已接受 clear；仍須外部觀察確認裝置定位恢復。
- unknown：set / clear 失敗，可能已部分執行；禁止繼續 set，允許 clear 重試。

位置觀測應在未來以獨立欄位記錄，例如 observed / unverified，
不把後端 ACK 當成 GPS 驗證。MVP 無並行呼叫、跨程序狀態或磁碟持久化。
實機後端加入前必須有 crash journal 與重啟恢復，紀錄最少必要資訊並保護隱私。

## 實機 adapter 的驗收門檻

選定並固定上游版本；明確指定 UDID、拒絕多裝置歧義；建立連線前顯示目標；
set 長連線保持；中斷與失敗分開處理；clear 的逾時不能當成功；
輸出經過遮罩，避免紀錄配對檔、實際經緯度與完整裝置 ID。
不用短暫 subprocess.run 成功返回來假裝維持定位 session。
set 的子程序必須由同一個 session owner 結束並確認不再殘留；否則後續 clear 不能作為恢復證據。
初版未實作這些功能，因此不提供 --execute。

未來本機 HTTP 控制端需 loopback bind、Origin/Host 檢查、session token、
CSRF 防護和輸入上限；在此之前不開放遠端或手機網頁控制。
