# Location Lab — iPhone 定位模擬工作空間

獨立的 iPhone 定位模擬研究專案，暫定名稱 Location Lab。
**目前是可執行、可測試的離線初版，沒有連接或驗證 iPhone。**

這是位置（WGS84 經緯度／GPS 定位輸出）模擬專案，不是 IP 位址修改器。
不承諾第三方 App 接受模擬位置，不實作遊戲偵測規避。

## 系統設計與公開準備

- [完整系統架構與分階段驗收](docs/system-design.md)
- [版本相容性與證據](docs/compatibility.md)
- [安全邊界](SECURITY.md)

## 現在可以做什麼

- 驗證經緯度，拒絕超界、NaN、Infinity。
- 用記憶體後端演練設定、清除與失敗後恢復狀態。
- 產生 pymobiledevice3 DVT 指令計畫；只輸出 JSON，**不執行指令**。
- 閱讀 WLoc 架構、失效證據、技術選型和真機驗收清單。

目前交付的是離線研究骨架，真機實驗須具備 Mac 與已信任的 iPhone。

## 流程圖與下載後接續

完整[流程圖與架構圖](docs/diagrams.md)、[本機轉移指南](docs/transfer.md)。
新增故障演練：`python3 run.py scenario clear-retry`，只操作記憶體。

## 開始

Python 3.11+，離線核心只用標準函式庫；不需要安裝任何依賴。

```sh
PYTHONPATH=src python3 -m location_lab demo --latitude 35.6812 --longitude 139.7671
PYTHONPATH=src python3 -m location_lab plan set --latitude 40.69 --longitude -74.04
PYTHONPATH=src python3 -m location_lab plan clear
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

demo 的狀態只屬於 mock 後端，結束即消失。plan 不代表指令已送出或位置已變更。

## 目錄

- `src/location_lab/`：座標模型、後端契約、工作階段、CLI、DVT 指令規劃
- `tests/`：輸入邊界、故障與恢復、命令計畫、CLI
- `docs/research.md`：2026-11-07 研究與來源
- `docs/architecture.md`：選型與狀態語意
- `docs/testing.md`：自動測試與真機驗收
- `docs/roadmap.md`：下一階段工作與待補資訊
- `AGENTS.md`：維護規則

## 授權與發布

本專案尚未選定公開授權。公開 repo：https://github.com/xixi219/location-lab 。初版為新寫的實作，未複製 WLoc 或
pymobiledevice3 原始碼，也未捆綁這兩個依賴。參考來源與授權列於
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。正式整合或散布前再確定授權及依賴版本。
