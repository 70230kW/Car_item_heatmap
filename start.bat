@echo off
cd /d "%~dp0"
echo 在庫ヒートマップ比較を起動しています…
echo.
if not exist "run.py" (
  echo [エラー] run.py が見つかりません。
  echo zip の中から直接開いている可能性があります。
  echo zip を右クリック →「すべて展開」してから、展開したフォルダの start.bat を実行してください。
  goto END
)
where python >nul 2>nul
if not errorlevel 1 (
  python run.py
  goto END
)
where py >nul 2>nul
if not errorlevel 1 (
  py run.py
  goto END
)
echo [エラー] Python が見つかりません。
echo PowerShell で python --version が動くか確認してください。
:END
echo.
echo このウィンドウを閉じるには何かキーを押してください。
pause >nul
