from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from scraper import scrape

app = FastAPI(title="在庫ヒートマップ")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/analyze")
def analyze(
    url: str,
    max_pages: int = Query(5, ge=1, le=50),
    basis: str = Query("auto", pattern="^(auto|body|total)$"),
):
    """在庫一覧URLを取得し、車両ごとの価格・メーカー・ボディタイプを返す。
    ヒートマップの集計(縦軸切替・平滑化)はフロント側で行うので、再取得なしで調整できる。"""
    try:
        return scrape(url, max_pages=max_pages, basis=basis)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except requests.RequestException as e:
        raise HTTPException(502, f"ページを取得できませんでした: {e}")
