# 研究紀錄 — 2026-11-07 UTC

## 來源範圍

使用 GitHub 直接讀取 README、LICENSE、NOTICE、檔案樹、Swift 核心檔、DVT CLI 與全部近期 issues/comments。
WLoc main tree: `54bd7378853d12c2e69aa7d7da33bc21c617d2c6`。
pymobiledevice3 master tree: `776d601cec83b894c3ad0eeee8ab4db375a46e4a`。
分支讀取與 tree 查詢在同次研究進行，未在本機建置兩個上游專案。
以下 OS 版本均照來源記載，不推定裝置相容性，也未獨立核驗回報者環境。

## WLoc 架構

[README](https://github.com/OpenHRTT/wloc/blob/54bd7378853d12c2e69aa7d7da33bc21c617d2c6/README.md)
及程式顯示它是 Swift iOS/macOS 專案：
地圖選點 → iOS Packet Tunnel Extension / macOS 系統 PAC → 本地 HTTPS proxy →
Apple 定位服務的特定網域。它不是單純 VPN 換 IP，也不是 pymobiledevice3 的 DVT 方法。

- [PacketTunnelProvider.swift](https://github.com/OpenHRTT/wloc/blob/54bd7378853d12c2e69aa7d7da33bc21c617d2c6/WLocApp/WLocCore/PacketTunnelProvider.swift)：NetworkExtension 建立 tunnel 設定並啟動代理服務。
- [AppWLocMutator.swift](https://github.com/OpenHRTT/wloc/blob/54bd7378853d12c2e69aa7d7da33bc21c617d2c6/WLocApp/WLocCore/AppWLocMutator.swift)：解析 ARPC / Protobuf，改寫 Wi-Fi location 資料並組裝回應。
- 原始碼另有憑證儲存、座標轉換、狀態、VPN manager、Mac PAC manager / privileged helper。
- [Podfile](https://github.com/OpenHRTT/wloc/blob/54bd7378853d12c2e69aa7d7da33bc21c617d2c6/Podfile)：SwiftProtobuf、SnapKit、IQKeyboardManagerSwift、GCDWebServer；第三方授權必須各別確認。
- README 要求本機產生憑證及信任設定。公開 tree 未見完整網頁服務端原始碼，不能因有「網頁版」就推定只用瀏覽器 API 即可更改全機定位。
- README 宣傳相容性不等於測試證據；本專案不採納其規避風控的承諾。

## 「兩天前失效」查證

最符合描述的是 [issue #11](https://github.com/OpenHRTT/wloc/issues/11)，
建立於 **2026-11-04 05:05 UTC**，最後回覆 **2026-11-05 01:57 UTC**。
相對本次研究 11 月 7 日，建立約三天前、最後回覆約兩天前；不把相對日期當成精確故障時間。

| 證據等級 | 查到什麼 | 可以得出的結論 |
| --- | --- | --- |
| 已確認公開紀錄 | #11 多人回報 18.6、26.3.1、26.6.2 等失效；有人未重啟仍可用 | 存在跨版本失效回報，但非全面相容性統計 |
| 有技術細節的社群調查 | 11/4 12:06 Xboxpig 回報 pinningrules.sqlite3 對 gs-loc 網域增加 AppleIssued 校驗，出現 -67880 / pinning requirements 錯誤 | 憑證釘選變更是有依據的主要假說 |
| 維護者回應 | 11/4 12:08 OpenHRTT 認為看起來是 Apple 更新；後續擔心再次更新 | 維護者支持此解釋，但沒有官方確認或本機可重現測試 |
| 尚未確認 | Apple 政策變更的完整範圍、所有 iOS 版本、服務端或下發規則的完整因果鏈 | 不可宣稱已證明全面封鎖，也不可宣稱已修復 |

後續 [#12](https://github.com/OpenHRTT/wloc/issues/12)（11/6）與
[#13](https://github.com/OpenHRTT/wloc/issues/13)（11/6）仍有 17、26.4、15.8.8 等版本的使用者回報。
截至此次讀取，沒有看到上述討論內已驗證的非越獄修復方案。
快取造成未重啟裝置暫時可用是討論中的解釋，未由本專案驗證。

**工程判斷：** 若失效來自系統信任政策，重寫同一套 HTTPS 代理不會自動解決根因。
因此第一階段不重刻代理或修改憑證信任規則，也不研究偵測繞過。

## pymobiledevice3 評估

[README](https://github.com/doronz88/pymobiledevice3/blob/776d601cec83b894c3ad0eeee8ab4db375a46e4a/README.md)
與 [DVT simulate-location CLI](https://github.com/doronz88/pymobiledevice3/blob/776d601cec83b894c3ad0eeee8ab4db375a46e4a/pymobiledevice3/cli/developer/dvt/simulate_location.py)
提供 set / clear / play；set 會保持工作階段至中斷。DVT CLI 描述適用 iOS 17+。
這條路線透過裝置開發者服務，機制上不同於 WLoc 的定位服務代理；
**這不代表已證明能在 測試用的手機或特定 App 上成功。**

[隧道文件](https://github.com/doronz88/pymobiledevice3/blob/776d601cec83b894c3ad0eeee8ab4db375a46e4a/docs/guides/ios17-tunnels.md)
目前記載 iOS 17.4+ 可自動使用無 root userspace tunnel；
17.0–17.3 的 macOS / Linux / Windows 路徑不同。不要沿用「所有新 iOS 都必須 sudo tunneld」的舊假設。
這是上游當前文件，尚未對某個已發布套件版本驗證，實作前必須固定版本並檢查 --help。
Wi-Fi 通常仍需初始 USB 配對／啟用條件，不是只有手機就能在這個雲端環境操作。

需要確認：iPhone 型號、iOS 完整 build、Mac 系統、信任配對、Developer Mode、開發者映像與 transport。
WLoc 授權為 MIT（僅自有碼），pymobiledevice3 為 GPL v3；詳見第三方紀錄。

## 還沒做的事

未連接手機、未安裝根憑證、未更改代理、未執行定位指令、未測試遊戲。
未將 issue 中的憑證規則修改當作實作建議。

## 2026-11-11 追蹤更新（取代先前「尚未看到修復建議」的現況描述）

[#11](https://github.com/OpenHRTT/wloc/issues/11) 維護者在 11/7 新增回覆，
將問題歸因於系統信任資產更新，並提出涉及裝置重置及阻止更新的處理方式。
[#15](https://github.com/OpenHRTT/wloc/issues/15) 11/10 仍有人表示重置後失效，維護者重貼相同建議。
[#14](https://github.com/OpenHRTT/wloc/issues/14) 連結另一個憑證校驗相關工具，
但只有提案/外部連結，不構成本專案測試結果。未下載或執行該工具。

已確認：上述公開回覆存在。仍未確認：根因的獨立重現、修復成功率、完整版本範圍。
本專案不採用裝置重置、封鎖安全更新或繞過憑證釘選作為產品依賴。
DVT 開發者服務路線仍須另做真機驗證，不能由 WLoc 的結果推論成功。

pymobiledevice3 的 pyproject 在本次讀取宣告 GPL-3.0-or-later、Python >=3.9；
Location Lab 核心仍為 Python >=3.11。完整矩陣見 compatibility.md。

## 2026-11-11 上游持續性修正

[v11.50.1 release notes](https://github.com/doronz88/pymobiledevice3/releases/tag/v11.50.1) 說明：先前 userspace
tunnel 的長連線 CLI 命令在等待中會阻塞維持隧道的事件迴圈；`developer dvt simulate-location set` 與 `play`
可能因此在設定後不久還原真實位置。該版將等待改為不阻塞。這讓它成為本機試驗的最低候選版，
但只是一份上游描述，不能替代本專案裝置上的 set、持續觀察與 clear 恢復驗收。
