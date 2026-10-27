"""在庫ヒートマップ比較を起動する（start.bat をダブルクリックするとこれが動く）。

- このファイルのあるフォルダで起動する（どこから実行しても main.py を見つけられる）
- 必要なライブラリが無ければ requirements.txt からインストールする
- ポート 8000 が使えない（他のアプリが使用中 / Windowsの予約ポート）ときは空いているポートを自動で選ぶ
- 起動したらブラウザで画面を開く
"""
import importlib.util
import os
import socket
import subprocess
import sys
import threading
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

REQUIRED = ["fastapi", "uvicorn", "requests", "bs4"]
PORTS = [8000, 8765, 8080, 8888, 5050]


def ensure_packages() -> None:
    missing = [m for m in REQUIRED if importlib.util.find_spec(m) is None]
    if not missing:
        return
    print(f"必要なライブラリをインストールします（{', '.join(missing)}）…")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", os.path.join(HERE, "requirements.txt")])


def free_port() -> int:
    for port in [*PORTS, 0]:  # 0 = OSに空きポートを選ばせる
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:  # 使用中、または WinError 10013（予約済みで使えない）
                if port:
                    print(f"ポート {port} は使えないため、別のポートを試します。")
    raise SystemExit("空いているポートが見つかりませんでした。")


LOG = os.path.join(HERE, "startup.log")


def main() -> None:
    print(f"Python {sys.version.split()[0]}（{sys.executable}）")
    ensure_packages()
    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    print()
    print("=" * 60)
    print("在庫ヒートマップ比較を起動しました。")
    print(f"  ブラウザで開くアドレス:  {url}")
    print("  ※ このウィンドウを閉じるとアプリも止まります（終了は Ctrl+C）")
    print("=" * 60)
    print()
    with open(LOG, "w", encoding="utf-8") as f:
        f.write(f"started {url}\npython {sys.version}\n")
    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("終了しました。")
    except subprocess.CalledProcessError:
        print("\n[エラー] ライブラリのインストールに失敗しました。")
        print("インターネット接続（会社のプロキシ等）を確認し、PowerShell で次を実行してみてください:")
        print(f'  "{sys.executable}" -m pip install -r "{os.path.join(HERE, "requirements.txt")}"')
        sys.exit(1)
    except Exception:
        import traceback
        detail = traceback.format_exc()
        with open(LOG, "w", encoding="utf-8") as f:
            f.write(detail)
        print("\n[エラー] 起動できませんでした。内容:")
        print(detail)
        print(f"同じ内容を {LOG} に保存しました。")
        sys.exit(1)
