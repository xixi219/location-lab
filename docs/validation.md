# 驗證結果

日期：2026-11-07；環境：Linux / Python 3.12.14。

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v`：13 tests，全部通過，退出碼 0。
- `python3 -m location_lab demo --latitude 35.6812 --longitude 139.7671`（PYTHONPATH=src）：輸出 mock，active → cleared，hardware_verified=false。
- `python3 -m location_lab plan set --latitude 40.69 --longitude -74.04`（PYTHONPATH=src）：輸出 plan-only、executed=false；負經度前有 `--`。
- 本機 Git 已初始化，分支 main；沒有設定遠端、沒有發布，尚未建立第一筆 commit。

沒有安裝或執行 pymobiledevice3；沒有編譯 WLoc；沒有連接 iPhone；沒有 Mac/iOS 實測結果。
打包安裝、跨 Python 版本與未來 device adapter 尚未驗證。

## 第二次開發驗證

新增 scenario 故障演練、完整流程與架構圖、原始碼啟動入口及轉移指南。
同一測試命令執行 19 tests 全部通過，退出碼 0。
所有情境均為記憶體模擬，未進行任何裝置通訊。

## 2026-11-11 架構與公開準備

從先前交付 ZIP 還原，先驗證 ZIP SHA-256 與 24 個檔案 manifest 全部相符。
重新執行既有 19 個 unittest 全數通過。更新系統架構、相容矩陣、公開前檢查、
安全邊界與貢獻文件；無裝置功能變更。常見機密模式掃描未命中，非完整資安審計。
本次沒有 GitHub mutation，也沒有真機測試。
