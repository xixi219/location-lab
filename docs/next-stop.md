# 下一站：離線按鈕原型

更新：2026-11-12。只使用標準函式庫、MemoryBackend 與 fake-only 裝置邊界；預設不連接 iPhone，不載入實驗控制器。另有 [明確 opt-in 的 USB 原型](mac-usb-control.md)，
尚未真機驗收。不操作遊戲或其他 App，不修改 IP。這不是已完成的真機產品。

## 使用

```sh
PYTHONPATH=src python3 -m location_lab.next_stop_web --queue /absolute/private/queue.json
```

在**執行程式的同一台電腦**開啟 `http://127.0.0.1:8765`。
可用 `--port 0` 選擇空閒埠，以啟動訊息為準。只綁定 IPv4 loopback，沒有 LAN／公開服務選項。
雲端啟動的 loopback 不是使用者 Mac 的 loopback，不能直接讓手機連進來。
目前不對外部署，也不建立轉送通道。

1. 畫面先顯示未連接 iPhone、離線模擬未啟用／狀態未知。
2. 按「啟用離線模擬」，再按「清除／復原（僅模擬）」。
3. 按「下一個」只推進一站，顯示目前／下一站店名、下一站地址與進度，不需手動輸入座標。
4. A→B 直接 set，兩站之間不自動 clear。
5. 「模擬斷線」進入 unknown；重新啟用仍需明確 clear 才能繼續。
6. clear 不回捲進度，也不前進；下一次 next 仍指向尚未成功的站。

## 私人進度與 fake 裝置邊界

```sh
mkdir -m 700 /absolute/private-progress
PYTHONPATH=src python3 -m location_lab.next_stop_web \
  --queue /absolute/private/queue.json \
  --journal /absolute/private-progress/progress.json \
  --backend fake-device --device synthetic-device
```

`fake-device` 只接受 FakeDeviceTransport，`--device` 是明確指定的合成識別，不會搜尋真機。
未指定 backend 時仍為 memory。兩種方式都顯示「離線演練／未連接 iPhone」。
裝置契約分開實作 exact identity、preflight、程序內唯一 owner、同步命令與故障後封鎖。
不准用此旗標啟動舊實驗控制器；另有 usb 選項，但必須另給 allow-device-write／私人識別檔／journal，詳見 Mac 控制文件。

**指定 journal 時，重啟保留已完成 cursor 與去重回條，但使用新 epoch 並回到 disconnected + unknown；
須明確啟用／preflight，再 clear 才能 next。從不重播未完成指令。未指定 journal 時進度仍在重啟後歸零。**
journal 綁定完整佇列內容／原順序與選定 backend identity 的 hash；變更任一者拒絕載入。
保留原檔排查，不能以刪除 journal 冒充恢復。更換 queue 是新的行程，需新 journal 與明確啟動。

每次操作先原子保存 intent，再呼叫後端，再原子保存結果。程序在 intent 與 ACK 間崩潰時，
該 request 的回條永久為 outcome_unknown，cursor 不前進。重啟後先明確恢復，再以新 request 操作同站。
若 ACK 後保存結果失敗，當次顯示未知並鎖住所有操作；重啟讀取實際已落盤狀態，可能是舊 cursor
與 pending，或 rename 已成功的新 cursor。兩者均不自動操作裝置。
同 ID 重送回傳既有回條，不因重啟而執行第二次；舊 epoch 的新 request 拒絕。

journal 檔案是 0600，父目錄須為目前使用者擁有的 0700，必須在 repo 外。
同 journal 使用 lifetime flock；fake backend 另有固定每使用者、依身分 hash 的 POSIX lease，
即使使用不同 journal，也不能由兩個程序同時取得相同合成裝置。lock 檔保留 inode、不含原始識別。
此互斥只是離線邊界，尚未整合真實 Mac 裝置身分或通道生命周期。
不保存座標、店名、地址、原始 request ID 或裝置識別。hash 不是加密，檔案仍需私人保護。
儲存失敗／損毀／綁定不符必須人工檢查，程式不偷偷重設或自動刪除。

停止程序不等於實體裝置恢復。在離線模式 clear 成功只表示 mock 呼叫返回；
`physical_restored`、`hardware_verified`、`device_connected` 固定為 false。

## 私人佇列

以明確路徑讀入 repo 外 JSON（含符號連結解析），不複製、不改寫、不重新排序。
頂層 `executed` 與 `hardware_verified` 必須為 false；`steps` 是非空陣列，
每項含 `name`、`address`、`latitude`、`longitude`。座標須為有限且合法範圍的數字。
額外查核來源欄位不影響讀取。檔案順序是唯一執行順序；不重新地理查核、不假裝確認營業。
真實店名、座標、資料檔、截圖及 logs 不應加入原始碼或測試 fixture。
常態 UI／API 不傳出座標；queue 資料在程序中仍是私人資訊。

## 命令契約與安全

`NextStopController.execute` 是獨立入口；新增本機 one-shot CLI 可供未來 chat adapter 呼叫，**尚未接上聊天**。
先取得 snapshot，再傳 `request_id`（唯一字串）、`epoch`、`version` 與 `action`。
action 包含 `next`、`clear`、`preflight`、`disconnect`；`connect_mock`／`disconnect_mock` 保留為舊介面別名。
fake-device 的 preflight 只查合成資料；USB 模式才會在明確 opt-in 下呼叫真實 worker。

- 單一 controller 鎖序列化判斷及後端呼叫；同時兩個相同版本的 next 最多一個成功。
- 同 ID、同內容回傳原回條；同 ID 改內容拒絕。回條不是最新 snapshot，之後必須重新讀狀態。
- epoch 不同（重啟）或版本過期拒絕；有效操作嘗試即消耗版本，包括失敗／斷線拒絕。
- set 失敗不移動 cursor，狀態 unknown／disconnected，必須重新 preflight 與明確 clear；clear 失敗仍 unknown。
- UI 阻擋處理中點擊、同次雙擊的後續 click 與重複按鍵；沒有計時前進、自動重試或輪詢。
- 網路失敗不知請求是否已執行時停用 UI，使用者重新整理查看狀態，不自動再送。
- 每個 session 最多保存 10,000 回條；達上限拒絕新指令，避免淘汰後重複執行。
- HTTP 僅在 loopback；檢查精確 Host、同來源 Origin 與每程序隨機 token，沒有 CORS。
  讀取狀態亦需 token；GET 不操作後端。不記錄存取紀錄、原始例外或 token。
- 這不是多使用者服務。可讀本機 loopback 的其他本機程序不在隔離邊界內；不得公開代理此服務。

## 下一階段（尚未完成）

Mac companion 才能持有 USB／開發者通道及唯一裝置 owner。
正式 adapter 仍需真機 preflight、既有跨程序 lease 的真實裝置綁定、逾時／取消 quiescence 屏障、斷線通知、
現有 journal 與實機生命周期整合、故障後恢復及獨立地圖觀察。ACK 不等於第三方 App 已接受定位。
fake 邊界仍拒絕 real transport，新的 USB backend 另行隔離實作，並非移除 fake gate。
USB worker 的 generation／request ID、程序停止屏障須配合真機生命周期驗收；
clear 呼叫返回不是 ACK。沒有 unsafe 背景 thread timeout。

手機說「可以下一個」的 chat-trigger adapter 必須將單次明確意圖對應到指定 session、
版本與唯一 request ID，由已授權連線到 Mac 的路徑送給本機 controller；目前沒有接線或驗收。
若日後採 cloud-to-Mac bridge，需另設驗證、授權、重播防護與裝置綁定；雲端不直接操作 USB。
不需要為目前離線原型先建公開 relay、安裝憑證或設定 credentials。

## 驗證

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node tests/next_stop_ui_test.js
```

unittest 使用合成站點、記憶體故障後端及暫時 loopback server。
Node 可選測試執行實際 inline JS 搭配 DOM／fetch mock，測試雙擊（包含第一個回應已完成）、
處理中連按、重複按鍵及網路中斷。不是瀏覽器視覺或真機驗收。
