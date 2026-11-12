# Mac USB 原型與單次聊天命令介面

此階段新增原創 production-path scaffolding，不再只有 fake：選定裝置的 USB backend、
隔離 SDK worker、持久 DVT session 與本機 one-shot CLI。**只在雲端以 doubles 測試；
未安裝 SDK、未發現或接觸任何真機，hardware_verified 永遠為 false。**
原實驗快照保持不變，不會被新入口執行。

## 啟動條件與範例（尚未在 Mac 執行）

實際執行電腦必須是實體連接 iPhone 的 Mac，且已有經審查的 Python／
pymobiledevice3 11.52.1。此工具不安裝依賴、不自動配對、不啟用 Developer Mode，
不變更信任、憑證或網路設定。不相容、缺依賴或無法確認 USB-only 時拒絕。

先由維護者準備 repo 外私人 0700 目錄、0600 裝置識別檔，以及私人 queue。
裝置識別檔只含明確選定的一個識別，不放入命令列、Git 或日誌。

```sh
PYTHONPATH=src python3 -m location_lab.next_stop_web \
  --backend usb --allow-device-write \
  --device-file /absolute/private/device-id.txt \
  --sdk-python /absolute/existing-sdk-env/bin/python \
  --queue /absolute/private/queue.json \
  --journal /absolute/private/progress.json \
  --control-socket /absolute/private/controller.sock
```

以上是未執行的操作範例，不代表授權或已接通。啟動只建立 owner／介面；仍須明確 preflight，
再 clear 未知狀態後才能 next。真機模式頁面明確寫 USB 原型／硬體未驗證，不冒充離線。
同一 owner 在多次 next 保持 SDK session，A→B 不自動 clear。

SDK 呼叫返回不代表裝置 ACK，更不代表地圖接受。尤其 LocationSimulation.clear 使用
expects_reply=False，只能稱清除呼叫返回／dispatch-unverified；不以固定等兩秒冒充恢復。
停止／關閉 controller 也不自動宣稱清除實體定位。必須以獨立地圖觀察驗收。

## 一次性本機 CLI

既有 controller 使用私人 Unix socket；父目錄0700、socket0600，只供同使用者本機工具。
不開 LAN、不建立公開 relay；手機不能直接連上 Mac localhost。

```sh
PYTHONPATH=src python3 -m location_lab.local_control status \
  --socket /absolute/private/controller.sock

PYTHONPATH=src python3 -m location_lab.local_control next \
  --socket /absolute/private/controller.sock \
  --request-id NEW_UNIQUE_REQUEST_ID --epoch EPOCH_FROM_STATUS --version VERSION_FROM_STATUS

PYTHONPATH=src python3 -m location_lab.local_control receipt \
  --socket /absolute/private/controller.sock --request-id SAME_REQUEST_ID
```

status 與 receipt 都只讀，後者直接查既有回條，不重算 epoch／version、不送新站。
如果先前結果不明，先查 receipt 和 status；不要用新的 request ID 悄悄重送 next。
若 found=false，只代表沒有查到回條，不證明硬體沒變動，仍需確認 controller／journal 狀態。
preflight、clear、disconnect 同 next 一樣需唯一 request ID 與 expected epoch／version。
回條可能屬較早狀態；讀 status 判斷目前進度。

未來 dot 在收到**明確要求執行**的已驗證使用者訊息時，才可選擇當下已連線且授權的 Mac，
透過本機工具執行這個一次性命令。詢問「下一個是什麼」或討論設定，不等同執行指令。
沒有常駐雲端通道、daemon 回呼或離線排程；Mac 不在線就不排隊日後自動跳站。
每個新授權意圖一個 ID，重試同意圖使用原 ID；新版本／新 epoch 要重新確認狀態。

## 驗證限制

雲端 AF_UNIX 被執行環境拒絕（Operation not permitted），因此 socket 整合測試在此環境明確 skip，
須在 Mac 重跑。命令 dispatch、一次性 CLI doubles、只讀回條、過期／重複保護已離線測試。
瀏覽器視覺驗收也尚未完成。USB、實際 SDK、iOS 相容性、拔線／鎖屏／程序崩潰後的
獨立定位結果，均不得由 doubles 推定已驗證。

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node tests/next_stop_ui_test.js
```


## 連線狀態與 journal 綁定

preflight 成功只代表上次檢查成功，不是持續即時偵測拔線。API 的 device_connected 不宣稱即時連線，
USB 模式標示 connection_status=not_live_verified；下一次命令會重新檢查身分或失敗降為 unknown。
journal 的裝置 hash 包含 mock／USB 模式，不能把離線演練進度接續到實體裝置。
較早未包含模式的 journal 會被拒絕綁定，不自動遷移；保留原檔供人工檢查，另行明確建立新行程。


## USB worker 生命週期

pymobiledevice3 11.52.1 lazy 載入在隔離子程序；啟動前無裝置發現。
子程序把 userspace tunnel 的 factory 收窄為指定 serial、connection_type=USB、
本機 /var/run/usbmuxd、autopair=False，禁用 remote pairing／native fallback；
USB 枚舉、lockdown 與 RSD 身分逐層比對。此內部 factory 接點版本敏感，升級必須重新審核。

父子只以 bounded stdin/stdout JSON 傳遞資料；SDK 自己的 stdout/stderr 不可混入協定。
每筆 request 有獨立 ID 及 worker generation，不接受舊回應或 unsolicited 尾隨回應。
逾時／協定異常會終止整個 worker process group 並確認 reap；不能確認時 permanently fenced，
保留 owner，不允許 clear／新 set 競爭。沒有背景命令 thread timeout。
child 繼承同一 device lease FD，parent 被 SIGKILL 時也不能讓另一 owner 先進來；
只有 child 退出後 lease 才可能釋放。這已以 harmless subprocess 測試，不是硬體安全證明。
裝置或 kernel 已收到的請求即使 worker 死亡仍屬未知，必須重新 preflight／clear 與獨立觀察。

SDK 不隨原始碼封裝，沒有執行安裝；GPL 相關整合／散布授權仍待決策，
subprocess 不是授權義務的豁免。參考來源列在 THIRD_PARTY_NOTICES.md。
