# 安全與隱私

目前是離線原型：有 loopback HTTP 預覽、MemoryBackend 與 fake-only 裝置邊界。
新增明確 opt-in 的真實 USB transport 原型與隔離 pinned-SDK worker，但尚未安裝／執行於真機。
**沒有已驗證硬體支援、手機聊天常駐通道或公開遠端服務。**
不得視為正式定位服務；不操作遊戲或宣稱第三方 App 接受模擬定位。

## 已實作邊界

- CLI 驗證座標、執行記憶體模擬或列出計畫；plan 的 stdout 含使用者輸入座標，不應公開上傳。
- 預覽只綁定 127.0.0.1；檢查精確 Host、同來源 Origin、每程序 token，限制 body 大小，沒有 CORS。
  token 放在同來源頁面而非 URL／日誌；GET 不操作後端；不開 LAN 或代理。
- 同程序鎖、epoch／version 與 request ID 防止重複／過期前進；UI 防雙擊／重複按鍵，網路不明時不自動重送。
- 可選私人 journal 必須位於 repo 外、目前使用者擁有的 0700 目錄；檔案 0600，原子替換並 fsync 檔案及目錄。
  只存 hash 綁定、進度與最小回條，不存座標、店名、地址、原始 request ID、裝置識別或憑證。
- journal lifetime flock 阻擋同一 journal 的第二 owner；queue／device 綁定不符或損毀時拒絕啟動，不覆寫／重設。
- 後端呼叫前保存 intent；未完成 intent 視為 outcome_unknown。寫入失敗停止操作，絕不因 ACK 自動宣稱已恢復定位。
- 真實佇列、UDID、配對紀錄、憑證、密碼與截圖／私人 logs 不得加入 repo；測試只用合成資料。

## 尚需正式實作與驗收

預設 fake 的身分、信任、developer service 旗標只測試契約，不讀取 Mac／iPhone。
USB 模式需明確 opt-in、私人識別檔及 journal；SDK lazy import、版本固定、禁止自動配對與網路 fallback。
詳見 [Mac 控制邊界](docs/mac-usb-control.md)，不能用 doubles 測試宣稱 USB 已驗收。
fake owner 使用程序內 registry 與固定每使用者 POSIX lease，依身分 hash 鎖定，獨立於 journal 路徑。
私有 0700 鎖目錄、空白 0600 hash 檔，nonblocking flock；close 後保留 inode，不刪鎖檔。
跨程序／不同 journal 的相同身分互斥已以合成測試驗證。實機身分來源與 Mac 裝置生命周期仍未整合。

實機 transport 需明確選裝置、相容性檢查、固定與審核相依、配對材料的 OS 保護。
逾時／取消必須保證舊操作已靜止或以新 generation fencing；不能單純讓背景 thread 繼續寫入，
同時允許 clear／新 set。fake 同步執行；USB worker 以程序隔離、請求 ID／generation 和確認停止作取消邊界。
無法確認子程序退出時保留 owner 並封鎖新操作，不能等同實體裝置已恢復。
此機制以 doubles 測試，並非完成真機逾時／USB 韌體行為驗收。
需另補真機斷線、程序崩潰、日誌故障、晚到 ACK 與獨立定位觀察矩陣。

loopback 不是使用者間的安全隔離：本機可存取程序能讀取頁面 token。不得無審查公開代理。
journal hash 是最小化保存，不是加密；私人目錄仍需保護。網路檔案系統的鎖／fsync 語意未驗證。
不得自動安裝憑證、改信任設定或隱式要求新權限。

尚未配置私人弱點通報通道。請勿在公開 issue 張貼秘密或可利用的私人裝置資訊。

## 本機一次性控制

可選私人 Unix socket 提供 status／receipt 只讀及帶 expected epoch／version／request ID 的命令。
父目錄0700、socket0600，不替換既有 endpoint；結果未知不自動重送。這是同使用者權限邊界，
不是可公開代理的多使用者 API。雲端 AF_UNIX 受限，整合測試須在 Mac 重跑。
裝置識別及座標只經私人程序 IPC，不放 argv、公開回應或 logs；SDK stderr 不外洩。
