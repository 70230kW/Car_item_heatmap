from pathlib import Path
from threading import BoundedSemaphore

import requests
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from scraper import scrape
from google_sheets import router as google_router

app = FastAPI(title="在庫レンズ")
app.include_router(google_router)


@app.middleware("http")
async def private_google_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/google/", "/auth/google/")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Cookie, Origin"
    return response

ROOT = Path(__file__).resolve().parent
app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")
# Keep slow scraping requests from occupying every web worker thread.
SCRAPE_SLOTS = BoundedSemaphore(2)


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(ROOT / "assets" / "favicon.ico", media_type="image/x-icon")


@app.get("/")
@app.get("/static/index.html", include_in_schema=False)
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/api/analyze")
def analyze(
    url: str,
    max_pages: int = Query(5, ge=1, le=500),
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


@app.get("/api/analyze-page")
def analyze_page(
    url: str,
    basis: str = Query("auto", pattern="^(auto|body|total)$"),
):
    """One bounded request per page, so large scans do not hold one HTTP request open."""
    result = analyze(url, max_pages=1, basis=basis)
    # The client owns the overall page limit in this mode.
    result["warnings"] = [w.replace("1ページ分のみ集計しています", "このページまでを集計しています") for w in result["warnings"]
                          if w != "1ページで打ち切りました（次ページが残っています）。"]
    return result
