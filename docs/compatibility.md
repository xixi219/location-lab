# 相容性與可行性證據

更新：2026-11-11。上游文件描述、原始碼宣告與本專案實測必須分開看。

| 範圍 | 來源描述 / 限制 | Location Lab 證據 |
| --- | --- | --- |
| 離線核心與打包 | Python >=3.11，標準庫，無裝置依賴 | 26 個離線 unittest 通過；不代表硬體驗收 |
| pymobiledevice3 套件 | 2026-11-11 PyPI 最新已發布版為 11.52.1，宣告 Python >=3.9，含 Python 3.15 classifier | 已在本機忽略的隔離 venv 安裝 11.52.1 並核對 CLI；未納入專案發行依賴，這不是本專案降低 Python 門檻的理由 |
| iOS 17.4+ USB | 上游目前文件：自動 userspace tunnel、通常無需 root | 已在 iOS 27.2 完成一組 set/clear 地圖驗收；不能外推每個新 iOS build 都可用 |
| iOS 17.0–17.3 + Mac | 上游：native tunnel，無需 root；路徑不同 | 未真機驗證 |
| iOS 17.0–17.3 + Linux/Windows | 上游：需 privileged tunneld，Windows 另有 driver 條件 | 不列為初期產品目標 |
| iOS <17 | 本專案 DVT planner 以 iOS 17+ 指令為研究範圍 | 未支援，不能以 WLoc 回報推論 |
| Mac 最低版本 | 本次 pymobiledevice3 安裝文件未提供可直接套用的最低 macOS 保證 | 尚未訂產品最低版本；不得沿用 WLoc 的 macOS 13 deployment target |
| WLoc | 先前 Podfile：iOS 12、macOS 13 deployment target | 編譯目標不等於運作相容性，且代理有失效回報 |
| Wi-Fi | 上游有配對、初始設定與 discovery 條件 | 第一個真機里程碑只做 USB |
| 只有 iPhone / 瀏覽器 | 尚無本專案裝置通道 | 只能讀文件，未交付可改全機定位的 App |

Mac 實驗前：確認機型/CPU、完整 OS build、Python 環境、手機型號/iOS build、
信任配對、Developer Mode 與可用開發者服務/映像。
不假設 Developer Mode 開啟即所有前置條件滿足。
採獨立 Python 環境；不要把系統內建 Python 當成相容性保證。

必須在 P2 選定**已發布且可重現安裝的上游版本**，讀該版本 --help，
記錄 lock/雜湊與傳輸選項；目前讀到 default branch 文件，不代表已鎖定發布版。

持續性要求：上游 v11.50.1 的 release notes 說明它修正 userspace tunnel 在長時間
`developer dvt simulate-location set` / `play` 等待期間阻塞事件迴圈、導致模擬位置很快還原的問題。
因此本專案的候選實驗版本必須不低於 11.50.1，且每次真機驗收都要在 set 後保持連線並獨立觀察一段時間；
上游 release note 不是本機成功證據。

2026-11-11 的本機真機驗收：一台已信任 USB、iOS 27.2 的 iPhone，其 Developer Mode 與 userspace DVT
服務皆成功。Google Maps 獨立顯示藍點跳到公開測試點，接著在 `clear` 命令返回後重新顯示測試前基準位置的藍點。
後續一次驗收也發現，殘留的 set 工作階段會讓單次 clear 的回傳無法判讀；在停止殘留工作階段、以同一 DVT
連線送出 clear 並再次由 Google Maps 觀察後，才確認已回到基準位置。故任何 adapter 都必須管理子程序生命週期，
並在 clear 後做獨立觀測，不能只依賴 CLI 退出碼。
因此只對這組 Mac、Python 3.15.2、pymobiledevice3 11.52.1、iOS 27.2 作出「單點 set 與 clear 經 Google Maps
觀察」的真機主張。工作階段完整持續時間、拔線、重連與其他 iOS 27.x 版本仍待測；裝置識別與測試座標不寫入本專案。

來源（2026-11-11 直接讀取）：
- [pymobiledevice3 pyproject](https://github.com/doronz88/pymobiledevice3/blob/master/pyproject.toml)
- [安裝文件](https://github.com/doronz88/pymobiledevice3/blob/master/docs/installation.md)
- [iOS 17+ tunnels](https://github.com/doronz88/pymobiledevice3/blob/master/docs/guides/ios17-tunnels.md)
- [v11.50.1 release notes](https://github.com/doronz88/pymobiledevice3/releases/tag/v11.50.1)
- [WLoc Podfile，原研究快照](https://github.com/OpenHRTT/wloc/blob/54bd7378853d12c2e69aa7d7da33bc21c617d2c6/Podfile)
