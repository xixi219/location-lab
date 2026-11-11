# 本機實驗控制器：原始碼備份與恢復

更新：2026-11-11。這裡保存已審閱的實驗原始碼，讓專案可從 GitHub 找回。
**這不是正式 adapter、安裝程式或安全驗收通過的版本。不要在現有手機 session 活躍或狀態未知時啟動副本。**

## 保存範圍

`device-controller/` 的五個 Python 檔案與 `README.original.md` 保留當時原始 bytes。
原始說明中的「local-only／ignored／未發布」描述快照建立時的狀態；現在公開的是這份恢復用原始碼快照，
主 CLI 仍只執行離線功能。快照不會由主程式自動匯入或執行。

- `iphone_location.py`：便利入口，要求恰好一台 USB 裝置。
- `device_control.py`：外層命令、輸入檢查與原型控制流程。
- `dvt_clear_grace.py`、`dvt_location_session.py`：依賴 pymobiledevice3 的 DVT helpers。
- `plus_code.py`：離線 Plus Code 子集 helper，不是啟動控制器的必要檔案。
- `DEPENDENCY_VERSIONS.txt`：當時本機環境的套件版本清單，不是可移植的 hash lock，也不含套件程式碼。
- `MANIFEST.sha256`：上述檔案的內容雜湊。

這些檔案未包含實際裝置 ID、私人位置、地點收藏、配對資料、憑證、執行紀錄或活動 session。
不要把這類本機資料加入 Git。完整原始碼備份不等於連線狀態或私人資料備份。

## 在乾淨副本恢復

1. 先取得完整 repo，閱讀本文件與 [安全邊界](../SECURITY.md)，跑離線測試：

   ```sh
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m unittest discover -s tests -v
   ```

2. 確認沒有舊 controller 正在操作同一台手機，且副本中沒有既存 `private/`，再從 repo 根目錄恢復：

   ```sh
   test ! -e private && mkdir private && cp experiments/device-controller/*.py private/
   ```

   若 `private/` 已存在，先人工比對，不覆蓋它。原始程式依賴此目錄位置；不要直接從快照目錄執行。
   `private/` 保持被 Git 忽略，方便把本機執行副本與公開快照分開。

3. 在 Mac 本機另建 `.device-venv` 並由操作者安裝 `pymobiledevice3==11.52.1`。
   先閱讀該依賴的 GPL-3.0-or-later 授權與安裝要求。此 repo 不附帶依賴、wheel 或 venv。
   原快照環境為 Python 3.15.2；其他 Python／OS 組合、未來套件取得與跨平台重現均未保證。
4. `python3 private/iphone_location.py inspect` 是實際裝置操作，不是離線檢查。
   只有在操作者已授權、明確確認裝置及舊 session 狀態後才執行。信任配對與開發者服務需在本機準備，
   不要自動變更安全設定或重新配對。
5. `set` 的位置由操作者在本機提供，並顯式使用 `--allow-device-write`。
   `clear` 也需要此旗標。每次操作都要用獨立地圖或定位工具觀察，返回碼不能證明位置或恢復成功。
   收藏和配對資訊不在 repo，需保留於本機或由操作者重新提供。

不要為了恢復副本而自動殺程序、刪 socket、重放舊位置或重設裝置。狀態不明時保留 unknown，先確認現況。

## 已知限制

- Socket 依 repo 路徑命名，沒有綁定選定裝置；既有 supervisor 不會向請求端證明裝置一致。
  不可把這個原型用作多裝置控制器。
- `--fallback-cli` 不遵守 `--hold`，且缺少完整子程序生命週期管理。不能當作限時自動清除功能。
- `--hold` 的原始 help 文字與實作有差異：非 fallback 分支省略 hold 時由持久 supervisor 接管後返回，
  並非保持前景等待 Ctrl+C。
- DVT helpers 可直接呼叫，沒有外層的寫入旗標檢查；旗標不是不可繞過的安全界線。
- 退出、訊號、斷線、重連及失敗清理的故障矩陣未完成。某些清理失敗路徑可能回零，必須獨立觀測。
- 本機 argv 仍可能含裝置識別與座標，程序檢視或 shell history 可能看到它們；不要貼入共享紀錄。
- Socket 建立後才限制權限，完整 session 隔離與生命週期尚未驗收。
- Plus Code helper 僅實作六／十碼子集，極界、換日線及完整標準相容性未驗收。

本次發布僅做來源／敏感資料審閱、Python 語法檢查、離線測試與打包驗證，沒有操作手機或重跑真機驗收。
既有單機觀測證據見 [相容性文件](../docs/compatibility.md)，不應外推為此快照的完整安全保證。

## 授權與來源

此快照是本專案原創 wrapper／API adapter，未捆綁 pymobiledevice3 或其他第三方原始碼。
兩個 DVT helpers 直接引用 pymobiledevice3 API；該外部依賴為 GPL-3.0-or-later。
引用 API、複製來源與捆綁依賴是不同事實，這裡不據此宣告 GPL 豁免，也不以 subprocess 作為豁免理由。
本次不新增或變更專案 LICENSE；未選定公開授權不等於授予他人重用權。
正式整合或散布組合套件前，仍需由維護者確認專案授權與相容義務。
參考 [第三方告知](../THIRD_PARTY_NOTICES.md) 與
[pymobiledevice3 v11.52.1 LICENSE](https://github.com/doronz88/pymobiledevice3/blob/v11.52.1/LICENSE)。
