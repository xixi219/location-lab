# Location Lab — iPhone 定位模擬工作空間

獨立的 iPhone 定位模擬研究專案，暫定名稱 Location Lab。
**主 CLI 仍是可執行、可測試的離線初版；另保存可恢復的實驗控制器原始碼，尚未正式整合或完成故障矩陣。**

這是位置（WGS84 經緯度／GPS 定位輸出）模擬專案，不是 IP 位址修改器。
不承諾第三方 App 接受模擬位置，不實作遊戲偵測規避。

## 系統設計與公開準備

- [完整系統架構與分階段驗收](docs/system-design.md)
- [版本相容性與證據](docs/compatibility.md)
- [安全邊界](SECURITY.md)
- [實驗控制器原始碼備份、恢復方式與已知限制](experiments/README.md)

## 現在可以做什麼

- 驗證經緯度，拒絕超界、NaN、Infinity。
- 用記憶體後端演練設定、清除與失敗後恢復狀態。
- 產生 pymobiledevice3 DVT 指令計畫；只輸出 JSON，**不執行指令**。
- 閱讀 WLoc 架構、失效證據、技術選型和真機驗收清單。

主程式交付的是離線研究骨架。2026-11-11 曾以本機實驗控制器在已信任的
iPhone 上完成單點 set / clear 的 Google Maps 獨立觀測；詳見
[相容性與可行性證據](docs/compatibility.md)。該控制器及其相依尚未完成散布授權、故障矩陣與
產品化審查，因此未整合至主 CLI。為方便恢復，原創來源快照另存於 `experiments/device-controller/`；
依賴須另裝，私人資料與正在執行的 session 不在 GitHub。

## 流程圖與下載後接續

完整[流程圖與架構圖](docs/diagrams.md)、[本機轉移指南](docs/transfer.md)。
新增故障演練：`python3 run.py scenario clear-retry`，只操作記憶體。

## 開始

Python 3.11+，離線核心只用標準函式庫；不需要安裝任何依賴。

```sh
PYTHONPATH=src python3 -m location_lab demo --latitude 35.6812 --longitude 139.7671
PYTHONPATH=src python3 -m location_lab plan set --latitude 40.69 --longitude -74.04
PYTHONPATH=src python3 -m location_lab plan clear
PYTHONPATH=src python3 -m location_lab places save --name Tokyo --latitude 35.6812 --longitude 139.7671
PYTHONPATH=src python3 -m location_lab places route Tokyo
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

demo 的狀態只屬於 mock 後端，結束即消失。plan 不代表指令已送出或位置已變更。
`places` 的收藏預設存在使用者私有狀態目錄、而非專案；route 只產生按輸入順序的下一站清單和
免 API key 的 Google Maps 搜尋連結，不會開啟網頁或寫入 iPhone。

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
