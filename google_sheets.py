"""Per-browser, read-only Google Sheets OAuth. Tokens stay in server memory."""
import base64
import hashlib
import json
import os
import re
import secrets
import time
from urllib.parse import quote, urlencode, urlparse, parse_qs

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, Field

from sheet_data import convert_rows

router = APIRouter()
COOKIE = "zaiko_google_session"
SESSIONS = {}
SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"


def config():
    client = os.environ.get("GOOGLE_CLIENT_ID", "")
    secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    redirect = os.environ.get("GOOGLE_REDIRECT_URI", "")
    parsed = urlparse(redirect)
    valid = parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"))
    return client, secret, redirect if valid and parsed.path == "/auth/google/callback" else ""


def session(request, required=True):
    key = request.cookies.get(COOKIE, "")
    current = SESSIONS.get(key)
    if current and current["expires"] <= time.time():
        SESSIONS.pop(key, None)
        current = None
    if required and (not current or not current.get("token")):
        raise HTTPException(401, "Googleに接続してください。接続の有効期限が切れた場合は再接続してください。")
    return current


def same_origin(request):
    origin = request.headers.get("origin")
    redirect = config()[2]
    if origin and redirect:
        parsed = urlparse(redirect)
        if origin != parsed.scheme + "://" + parsed.netloc:
            raise HTTPException(403, "接続元を確認できません。アプリの画面から操作してください。")


@router.get("/api/google/status")
def status(request: Request):
    current = session(request, False)
    return {"configured": all(config()), "connected": bool(current and current.get("token"))}


@router.get("/auth/google/login")
def login():
    client, secret, redirect = config()
    if not all((client, secret, redirect)):
        raise HTTPException(503, "管理者がGoogle接続を設定する必要があります。GOOGLE_CLIENT_ID・GOOGLE_CLIENT_SECRET・GOOGLE_REDIRECT_URIを設定してください。")
    now = time.time()
    for key in list(SESSIONS):
        if SESSIONS.get(key, {}).get("expires", 0) <= now:
            SESSIONS.pop(key, None)
    if len(SESSIONS) >= 1000:
        raise HTTPException(503, "Google接続が混み合っています。後で再試行してください。")
    key, state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    SESSIONS[key] = {"expires": now + 600, "state": state, "verifier": verifier}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    response = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": client, "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256", "prompt": "select_account",
    }), status_code=302)
    response.set_cookie(COOKIE, key, max_age=3600, httponly=True, secure=redirect.startswith("https://"), samesite="lax")
    return response


@router.get("/auth/google/callback")
def callback(request: Request):
    current = session(request, False)
    state = request.query_params.get("state", "")
    if not current or not secrets.compare_digest(current.get("state", ""), state) or not state:
        raise HTTPException(400, "Google接続を確認できません。アプリから再接続してください。")
    current.pop("state", None)  # A callback can be used only once.
    if request.query_params.get("error") or not request.query_params.get("code"):
        SESSIONS.pop(request.cookies.get(COOKIE), None)
        return RedirectResponse("/?google=cancelled", status_code=303)
    client, secret, redirect = config()
    try:
        response = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": client, "client_secret": secret, "redirect_uri": redirect,
            "grant_type": "authorization_code", "code": request.query_params["code"],
            "code_verifier": current.pop("verifier", ""),
        }, timeout=20)
        response.raise_for_status()
        token = response.json()
        if not token.get("access_token") or token.get("token_type", "").lower() != "bearer":
            raise ValueError("Invalid token response")
        current.update(token=token["access_token"], expires=time.time() + min(int(token.get("expires_in", 3600)), 3500))
    except (requests.RequestException, ValueError, KeyError):
        SESSIONS.pop(request.cookies.get(COOKIE), None)
        return RedirectResponse("/?google=failed", status_code=303)
    return RedirectResponse("/?google=connected", status_code=303)


@router.post("/api/google/logout")
def logout(request: Request):
    same_origin(request)
    SESSIONS.pop(request.cookies.get(COOKIE), None)
    response = JSONResponse({"connected": False})
    response.delete_cookie(COOKIE)
    return response


class PreviewRequest(BaseModel):
    url: str = Field(max_length=2000)
    sheet: str = Field(default="", max_length=200)
    header_row: int = Field(default=1, ge=1, le=50)


class ImportRequest(PreviewRequest):
    mapping: dict[str, int]
    company: str = Field(default="", max_length=200)
    role: str = Field(default="rival", pattern="^(own|rival)$")
    price_unit: str = Field(default="man", pattern="^(man|yen)$")
    mileage_unit: str = Field(default="km", pattern="^(km|man_km)$")


def sheet_id(value):
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != "docs.google.com":
        raise HTTPException(400, "GoogleスプレッドシートのhttpsのURLを入力してください。")
    match = re.match(r"^/spreadsheets/d/([A-Za-z0-9_-]{20,200})(?:/|$)", parsed.path)
    if not match:
        raise HTTPException(400, "スプレッドシートのURLを確認してください。")
    return match[1]


def api_get(path, token, params):
    response = None
    try:
        response = requests.get("https://sheets.googleapis.com/v4/spreadsheets/" + path,
                                headers={"Authorization": "Bearer " + token}, params=params, timeout=25, stream=True)
        if response.status_code == 401:
            raise HTTPException(401, "Google接続の有効期限が切れました。再接続してください。")
        if response.status_code in (403, 404):
            raise HTTPException(403, "このGoogleアカウントではシートを読み取れません。共有権限とGoogle Sheets APIの有効化を確認してください。")
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > 8 * 1024 * 1024:
                raise HTTPException(413, "シートが大きすぎます。対象の列・行を減らしたシートで取り込んでください。")
            chunks.append(chunk)
        return json.loads(b"".join(chunks))
    except (requests.RequestException, ValueError):
        raise HTTPException(502, "Googleスプレッドシートを読み込めませんでした。少し待ってから再試行してください。") from None
    finally:
        if response is not None:
            response.close()


def read_sheet(body, token):
    identity = sheet_id(body.url)
    meta = api_get(identity, token, {"fields": "properties(title),sheets(properties(title,sheetId))"})
    names = [item["properties"]["title"] for item in meta.get("sheets", [])]
    if not names:
        raise HTTPException(400, "読み取り可能なシートがありません。")
    parsed = urlparse(body.url)
    gid = parse_qs(parsed.fragment).get("gid", parse_qs(parsed.query).get("gid", [""]))[0]
    requested = next((item["properties"]["title"] for item in meta.get("sheets", [])
                      if str(item["properties"].get("sheetId", "")) == gid), None) if gid else None
    if gid and not body.sheet and requested is None:
        raise HTTPException(400, "URLで指定されたタブがありません。シートを確認してください。")
    name = body.sheet or requested or names[0]
    if name not in names:
        raise HTTPException(400, "シートが見つかりません。一覧を読み直してください。")
    area = "'" + name.replace("'", "''") + "'!A" + str(body.header_row) + ":BH" + str(body.header_row + 10001)
    values = api_get(identity + "/values/" + quote(area, safe=""), token, {"valueRenderOption": "FORMATTED_VALUE"}).get("values", [])
    if not values or not any(str(cell).strip() for cell in values[0]):
        raise HTTPException(400, "見出し行が空です。見出しの行番号を変更してください。")
    headers = [str(cell) for cell in values[0]]
    rows = [row for row in values[1:] if any(str(cell).strip() for cell in row)]
    # Bound the response for a small hosting instance; report any truncation.
    limit = min(10000, 200000 // max(len(headers), 1))
    return {"id": identity, "title": meta.get("properties", {}).get("title", ""),
            "sheets": names, "sheet": name, "headers": headers, "rows": rows[:limit],
            "truncated": len(rows) > limit}


def read_authorized(body, request):
    current = session(request)
    try:
        return read_sheet(body, current["token"])
    except HTTPException as error:
        if error.status_code == 401:
            current.pop("token", None)
        raise


@router.post("/api/google/preview")
def preview(body: PreviewRequest, request: Request):
    same_origin(request)
    return read_authorized(body, request)


@router.post("/api/google/import")
def import_sheet(body: ImportRequest, request: Request):
    same_origin(request)
    table = read_authorized(body, request)
    try:
        if set(body.mapping) - {"price", "year", "mileage", "name", "company"}:
            raise ValueError("列の項目を確認してください。")
        source = table["id"] + ":" + table["sheet"]
        result = convert_rows(table["headers"], table["rows"], body.mapping, body.company,
                              body.price_unit, body.mileage_unit, source)
        if body.role == "own" and len(result["stores"]) != 1:
            raise ValueError("自社として取り込む場合は、1社分のシートを選択してください。複数会社は他社として取り込めます。")
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    for store in result["stores"]:
        store["role"] = body.role
        if table["truncated"]:
            store["data"]["warnings"].append("読み込み上限のため、シートの一部のみ取り込みました。")
        if result["skipped_rows"]:
            store["data"]["warnings"].append(str(result["skipped_rows"]) + "行は価格が空欄または不正なため除外しました。")
    result.update(source=source, url=body.url, sheet=table["sheet"])
    return result
