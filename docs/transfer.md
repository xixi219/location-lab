# 搬到本機

下載 location-lab-source.zip 並解壓縮。內容只有專案程式與文件，
不含 .git、虛擬環境、配對檔、憑證或私密資料。MANIFEST.sha256 記錄每個檔案的 SHA-256。
這是原始碼快照，不是 iPhone 安裝檔，也不是可操控真機的成品。

## Mac 本機開始

需要 Python 3.11+。在解壓後的 location-lab 目錄開啟終端機：

```sh
python3 --version
python3 run.py --help
python3 run.py scenario clear-retry
python3 run.py demo --latitude 35.6812 --longitude 139.7671
PYTHONPATH=src python3 -m unittest discover -s tests -v
shasum -a 256 -c MANIFEST.sha256
```

不需 pip install，也不需先裝 Xcode 或連接手機即可跑離線演練。
版本低於 Python 3.11 時，先準備相容版本；不要把 macOS 內建 Python 版本當成已符合需求。

要在本機 Codex 接續，開啟解壓的 location-lab 資料夾，先讀 AGENTS.md、
docs/system-design.md、docs/diagrams.md。Git 歷史不在 ZIP；需要時在本機 git init。

## 重新製作快照

```sh
python3 scripts/export_project.py
```

腳本只包裝固定檔案清單。新增檔案若要交付，需同步更新 FILES。
輸出在 dist/，同時產生 ZIP 的 SHA-256。打包不會發布任何遠端。
完整性雜湊只能檢查檔案一致性，不能證明來源身分。
