# 相容性與可行性證據

更新：2026-11-11。上游文件描述、原始碼宣告與本專案實測必須分開看。

| 範圍 | 來源描述 / 限制 | Location Lab 證據 |
| --- | --- | --- |
| 離線核心 | Python >=3.11，標準庫，無裝置依賴 | Linux Python 3.12：19 tests 通過 |
| pymobiledevice3 套件 | pyproject 宣告 Python >=3.9 | 未安裝；這不是本專案降低 Python 門檻的理由 |
| iOS 17.4+ USB | 上游目前文件：自動 userspace tunnel、通常無需 root | 未真機驗證；不能外推每個新 iOS build 都可用 |
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

來源（2026-11-11 直接讀取）：
- [pymobiledevice3 pyproject](https://github.com/doronz88/pymobiledevice3/blob/master/pyproject.toml)
- [安裝文件](https://github.com/doronz88/pymobiledevice3/blob/master/docs/installation.md)
- [iOS 17+ tunnels](https://github.com/doronz88/pymobiledevice3/blob/master/docs/guides/ios17-tunnels.md)
- [WLoc Podfile，原研究快照](https://github.com/OpenHRTT/wloc/blob/54bd7378853d12c2e69aa7d7da33bc21c617d2c6/Podfile)
