from pathlib import Path
from threading import BoundedSemaphore

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from scraper import scrape

app = FastAPI(title="在庫ヒートマップ")
ROOT = Path(__file__).resolve().parent
app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")
# Keep slow scraping requests from occupying every web worker thread.
SCRAPE_SLOTS = BoundedSemaphore(2)


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/")
@app.get("/static/index.html", include_in_schema=False)
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/api/analyze")
def analyze(
    url: str,
    max_pages: int = Query(5, ge=1, le=50),
    basis: str = Query("auto", pattern="^(auto|body|total)$"),
):
    """在庫一覧URLを取得し、車両ごとの価格・メーカー・ボディタイプを返す。
    ヒートマップの集計(縦軸切替・平滑化)はフロント側で行うので、再取得なしで調整できる。"""
    if not SCRAPE_SLOTS.acquire(blocking=False):
        raise HTTPException(503, "取得処理が混み合っています。少し待ってから再試行してください。", headers={"Retry-After": "5"})
    try:
        return scrape(url, max_pages=max_pages, basis=basis)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except requests.RequestException as e:
        raise HTTPException(502, f"ページを取得できませんでした: {e}")
    finally:
        SCRAPE_SLOTS.release()
