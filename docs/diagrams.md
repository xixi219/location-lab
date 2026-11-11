# 執行流程與系統架構

2026-11-07。實線是現有程式路徑；虛線是規劃。
「已實作」不代表真機已驗證。「模擬」表示只改記憶體，沒有操作手機。

## 執行流程

```mermaid
flowchart TD
    A["CLI 輸入<br/>已實作"] --> B{"模式"}
    B -->|demo / plan set| C{"座標驗證<br/>已實作"}
    C -->|無效| D["錯誤退出<br/>已實作"]
    C -->|demo| E["設定 → 清除記憶體位置<br/>已實作・模擬"]
    C -->|plan set| F["DVT 指令 JSON<br/>已實作・不執行"]
    B -->|plan clear| F
    B -->|scenario| G["正常／斷線／清除重試<br/>已實作・模擬"]
    G --> H["逐步事件與最終狀態<br/>已實作・模擬"]
    F -.-> I["Mac 連接指定 iPhone<br/>規劃・未真機驗證"]
    I -.-> J["設定 → 獨立觀察 → 清除 → 獨立觀察<br/>規劃・未真機驗證"]
```

手機閱讀版：輸入座標 → 檢查範圍 → 選離線演練或指令預覽。
故障演練使用固定公開範例座標，不需要你的實際位置。
plan clear 不需要座標。現在所有路徑都不會連接 iPhone。

## 系統架構

```mermaid
flowchart TD
    A["CLI / run.py<br/>已實作"] --> C["Coordinate + Session<br/>已實作・離線測試"]
    B["手機友善圖形介面<br/>規劃"] -.-> C
    C --> D["Backend 契約<br/>已實作"]
    D --> E["MemoryBackend<br/>已實作・模擬"]
    D --> S["ScenarioBackend 故障注入<br/>已實作・模擬"]
    D -.-> F["Mac 裝置 adapter<br/>規劃"]
    F -.-> G["pymobiledevice3<br/>已研究・未整合"]
    G -.-> H["iPhone 開發者服務<br/>未真機驗證"]
    A --> P["DVT 指令 planner<br/>已實作・不執行"]
```

手機閱讀版：介面負責輸入；核心負責驗證與狀態；
後端負責實際操作。目前只有記憶體及故障模擬後端。
未來接 Mac 裝置後端，才有可能把操作送到 iPhone。

## 失敗與恢復

```mermaid
stateDiagram-v2
    [*] --> idle
    idle --> active: set 被後端接受
    active --> active: 更新位置被接受
    idle --> unknown: set 或 clear 失敗
    active --> unknown: set 或 clear 失敗
    active --> cleared: clear 被接受
    idle --> cleared: clear 被接受
    cleared --> active: set 被接受
    cleared --> unknown: set 或 clear 失敗
    cleared --> cleared: 再次 clear 被接受
    unknown --> unknown: 阻止 set 或 clear 再次失敗
    unknown --> cleared: clear 重試被接受
```

上圖為已實作狀態規則，在 mock 中測試。
active 不是位置觀測結果；cleared 也不是確認 GPS 已恢復。
真機加入後，仍要另外顯示「獨立觀察：未驗證／已觀察」。

## 現階段設計決策

1. 先驗證核心和恢復流程：手機可以先看結果，Mac 到手再驗證硬體。
2. UI 與裝置操作分開：之後換地圖或 Mac UI 不需重寫狀態管理。
3. 失敗顯示 unknown：可能已部分操作，不能假裝安全恢復。
4. 不延續 WLoc 代理作為主線：它的近期失效原因仍有待驗證；研究見 research.md。
5. 介面形式、正式名稱、地圖供應商與公開授權尚未決定，現在不用先選。

下一步適合讓 維護者 參與的是手機介面的資訊順序：
選地點 → 看連線裝置 → 設定 → 查看狀態 → 恢復。先做離線 UI，仍需另行實作。
