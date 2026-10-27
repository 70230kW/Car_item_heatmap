"""未使用車専門店の在庫一覧ページから、価格・年式・走行距離を抽出する。

サイトごとにHTML構造が違うため、特定のCSSセレクタに依存せず
「価格を含む同じ形の要素が繰り返し並んでいる = 1台ぶんのカードの一覧」というヒューリスティックで抽出する。
うまく取れないサイトは、画面の「車両データを見る」で抽出テキストを確認しつつ個別対応する想定。
"""
from __future__ import annotations

import ipaddress
import re
import socket
import time
import unicodedata
from collections import Counter
from urllib.parse import parse_qsl, urlencode, urldefrag, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; InventoryHeatmap/0.1)"
TIMEOUT = 15
MAX_BYTES = 5_000_000

# ---------------------------------------------------------------- SSRF対策


def assert_public_url(url: str) -> None:
    """サーバーが任意URLを取得するため、社内/ローカル宛てのアクセスを拒否する。"""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("http(s) のURLを指定してください")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror as e:
        raise ValueError(f"ホスト名を解決できません: {p.hostname}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("プライベート/ローカルアドレスは指定できません")


def fetch(url: str, session: requests.Session) -> tuple[str, str]:
    """リダイレクトを1回ずつ検証しながら取得。 (final_url, html) を返す。"""
    for _ in range(5):
        assert_public_url(url)
        r = session.get(url, timeout=TIMEOUT, allow_redirects=False, stream=True,
                        headers={"User-Agent": UA, "Accept-Language": "ja"})
        if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
            url = urljoin(url, r.headers.get("Location", ""))
            continue
        r.raise_for_status()
        body = r.raw.read(MAX_BYTES + 1, decode_content=True)
        if len(body) > MAX_BYTES:
            raise ValueError("ページが大きすぎます")
        enc = r.encoding if r.encoding and "charset" in r.headers.get("content-type", "").lower() else None
        enc = enc or requests.utils.get_encodings_from_content(body[:5000].decode("ascii", "ignore")) or None
        enc = enc[0] if isinstance(enc, list) else enc
        return url, body.decode(enc or r.apparent_encoding or "utf-8", errors="replace")
    raise ValueError("リダイレクトが多すぎます")


# ---------------------------------------------------------------- 抽出辞書

MAKERS = {
    "トヨタ": "トヨタ", "TOYOTA": "トヨタ", "レクサス": "レクサス", "LEXUS": "レクサス",
    "ホンダ": "ホンダ", "HONDA": "ホンダ", "日産": "日産", "ニッサン": "日産", "NISSAN": "日産",
    "マツダ": "マツダ", "MAZDA": "マツダ", "スバル": "スバル", "SUBARU": "スバル",
    "スズキ": "スズキ", "SUZUKI": "スズキ", "ダイハツ": "ダイハツ", "DAIHATSU": "ダイハツ",
    "三菱": "三菱", "ミツビシ": "三菱", "MITSUBISHI": "三菱", "いすゞ": "いすゞ", "日野": "日野",
    "メルセデス": "メルセデス・ベンツ", "ベンツ": "メルセデス・ベンツ", "BMW": "BMW",
    "アウディ": "アウディ", "AUDI": "アウディ", "フォルクスワーゲン": "フォルクスワーゲン",
    "VW": "フォルクスワーゲン", "ボルボ": "ボルボ", "VOLVO": "ボルボ", "ポルシェ": "ポルシェ",
    "ミニ": "MINI", "MINI": "MINI", "ジープ": "ジープ", "JEEP": "ジープ", "フィアット": "フィアット",
    "プジョー": "プジョー", "ルノー": "ルノー", "シトロエン": "シトロエン",
    "アルファロメオ": "アルファロメオ", "フォード": "フォード", "シボレー": "シボレー",
    "テスラ": "テスラ", "ランドローバー": "ランドローバー", "ジャガー": "ジャガー",
}
# 長い名称を優先してマッチさせる
_MAKER_KEYS = sorted(MAKERS, key=len, reverse=True)

BODY_KEYWORDS = [  # (表示名, 正規表現)  上から優先
    ("軽自動車", r"軽自動車|軽ワゴン|軽ハイト|軽トラ|軽バン|軽スーパー"),
    ("ミニバン", r"ミニバン|ワンボックス"),
    ("SUV", r"SUV|クロカン|クロスオーバー"),
    ("セダン", r"セダン"),
    ("ステーションワゴン", r"ステーションワゴン"),
    ("コンパクト", r"コンパクト|ハッチバック"),
    ("クーペ/オープン", r"クーペ|オープン|カブリオレ|ロードスター|スポーツカー"),
    ("トラック/バン", r"トラック|バン\b|商用"),
]

# 車名 → ボディタイプ（ページに明記がない場合の補完用。必要に応じて追記）
MODEL_BODY = {
    "軽自動車": ["N-BOX", "N-WGN", "N-ONE", "タント", "ムーヴ", "ミラ", "ワゴンR", "スペーシア", "ハスラー", "アルト",
                 "ジムニー", "デイズ", "ekワゴン", "ekクロス", "ルークス", "サクラ", "ラパン", "キャスト", "ウェイク",
                 "ハイゼット", "エブリイ", "アトレー", "ミライース", "タフト", "eKスペース", "スペーシアギア"],
    "ミニバン": ["アルファード", "ヴェルファイア", "ヴォクシー", "ノア", "エスクァイア", "セレナ", "ステップワゴン",
               "フリード", "シエンタ", "シャトル", "オデッセイ", "エルグランド", "ランディ", "デリカ", "アイシス", "ウィッシュ",
               "プレサージュ", "MPV", "ストリーム", "ジェイド"],
    "SUV": ["RAV4", "ハリアー", "C-HR", "ヤリスクロス", "ライズ", "ロッキー", "ヴェゼル", "CR-V", "ZR-V", "CX-5", "CX-3",
            "CX-30", "CX-60", "エクストレイル", "キックス", "ジューク", "フォレスター", "XV", "クロストレック", "レガシィアウトバック",
            "ランドクルーザー", "プラド", "エクリプスクロス", "アウトランダー", "ハリアーハイブリッド", "ヴェゼルハイブリッド",
            "ジムニーシエラ", "T-ROC", "Q3", "X1", "X3", "GLA", "GLC", "ティグアン"],
    "セダン": ["クラウン", "カムリ", "プリウス", "マークX", "アリスト", "スカイライン", "フーガ", "ティアナ", "シルフィ",
              "アコード", "インサイト", "レジェンド", "アテンザ", "MAZDA6", "インプレッサG4", "レガシィB4", "カローラアクシオ",
              "シーマ", "シルビア", "IS", "GS", "ES", "LS", "Cクラス", "Eクラス", "3シリーズ", "5シリーズ", "A4", "A6"],
    "コンパクト": ["ヤリス", "アクア", "ヴィッツ", "パッソ", "ポルテ", "スペイド", "ルーミー", "タンク", "ノート", "マーチ",
                "フィット", "グレイス", "デミオ", "MAZDA2", "マツダ2", "スイフト", "ソリオ", "バレーノ", "イグニス",
                "カローラフィールダー", "カローラスポーツ", "インプレッサスポーツ", "ミラージュ", "コルト", "ポロ", "ゴルフ",
                "A1", "A3", "1シリーズ", "Aクラス", "クラブマン", "ミニクーパー"],
    "クーペ/オープン": ["86", "GR86", "BRZ", "スープラ", "ロードスター", "S660", "フェアレディZ", "GT-R", "RX-8", "RX-7",
                  "コペン", "NSX", "ランサーエボリューション", "インプレッサWRX", "WRX", "911", "ボクスター", "ケイマン"],
    "トラック/バン": ["ハイエース", "NV350", "NV200", "キャラバン", "ボンゴ", "タイタン", "ダイナ", "サンバー", "ハイゼットカーゴ",
                  "ステップバン", "プロボックス", "サクシード", "ADバン", "ライトエース", "タウンエース"],
}
# 長い車名から先に判定（「ジムニーシエラ」→SUV を「ジムニー」→軽 より優先）
_MODEL_INDEX = sorted(
    ((m.upper(), body) for body, models in MODEL_BODY.items() for m in models),
    key=lambda x: len(x[0]), reverse=True,
)

# ---------------------------------------------------------------- 価格抽出

_MAN = re.compile(r"(?<![\d.,])(\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s*万\s*円?")
_YEN = re.compile(r"¥\s*(\d{1,3}(?:,\d{3})+)|(?<![\d.,])(\d{1,3}(?:,\d{3})+)\s*円")
_PRICE_ANY = re.compile(_MAN.pattern + "|" + _YEN.pattern)
_BODY_LABEL = re.compile(r"(?:車両|本体)\s*(?:本体)?\s*価格")
_TOTAL_LABEL = re.compile(r"(?:支払|お支払い?)\s*総額|総\s*額")
# ラベルなしで最初の価格を拾うときに、車両価格ではない金額を避ける
_NOT_CAR_PRICE = re.compile(r"月々|月額|頭金|ボーナス|諸費用|諸経費|税|リサイクル|下取|値引|オプション|割引|手数料|保険|ローン|残価")


def _price_matches(text: str):
    for m in _PRICE_ANY.finditer(text):
        if m.group(1):
            yield m, float(m.group(1).replace(",", ""))
        else:
            yield m, int((m.group(2) or m.group(3)).replace(",", "")) / 10000


def _first_price_after(text: str, label: re.Pattern) -> float | None:
    for lm in label.finditer(text):
        for m, v in _price_matches(text[lm.end():lm.end() + 40]):
            return v
    return None


def extract_price(card_text: str, basis: str = "auto") -> float | None:
    """basis: auto(本体価格優先) / body(本体価格) / total(支払総額)。単位は万円。"""
    if basis in ("auto", "body"):
        p = _first_price_after(card_text, _BODY_LABEL)
        if p is not None or basis == "body":
            return p
    p = _first_price_after(card_text, _TOTAL_LABEL)
    if p is not None or basis == "total":
        return p
    for m, v in _price_matches(card_text):
        if v >= 10 and not _NOT_CAR_PRICE.search(card_text[max(0, m.start() - 8):m.start()]):
            return v
    return None


# ---------------------------------------------------------------- カード抽出
#
# 一覧ページでは「1台ぶんのカード」が同じ形で繰り返し並ぶ。
# 価格表記を含む要素から親を辿り、「価格を含む子要素が同じ形で3つ以上並ぶ親」を一覧とみなし、
# その子要素を1台ぶんのカードとして扱う（1台に本体価格・支払総額・諸費用など価格が複数あっても、
# カードの単位は崩れない）。

_PRICE_HINT = re.compile(r"[万円¥￥]")


def _clean(text: str) -> str:
    # 全角英数・㎞ などを半角にそろえてから判定する
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def _sig(el) -> tuple:
    cls = el.get("class") or []
    return el.name, cls[0] if cls else ""


def _card_like(text: str) -> bool:
    """価格以外の文字がある程度ある（＝車名や諸元を含む）か。絞り込みメニューの「〜50万円」等を除く。"""
    rest = _PRICE_ANY.sub("", text)
    return len(re.sub(r"[\s〜~\-・/|()（）\d.,:：]", "", rest)) >= 10


def _price_anchors(soup) -> list:
    """価格表記を含む最小の要素。数値と「万円」が別タグに分かれていても拾う。"""
    out, seen = [], set()
    for node in soup.find_all(string=_PRICE_HINT):
        el = node.parent
        for _ in range(4):
            if el is None or el.name in ("body", "html", "[document]"):
                break
            if _PRICE_ANY.search(_clean(el.get_text(" "))):
                if id(el) not in seen:
                    seen.add(id(el))
                    out.append(el)
                break
            el = el.parent
    return out


def parse_cards(html: str) -> list[str]:
    """1台分と思われるブロックのテキスト（全角→半角に正規化済み）を返す。"""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "head", "nav", "footer", "header", "select", "option"]):
        t.decompose()
    order = {id(el): i for i, el in enumerate(soup.find_all(True))}
    anchors = _price_anchors(soup)
    if not anchors:
        return []

    # 親要素ごとに「価格を含む子要素」を集める
    hits: dict[int, dict[int, object]] = {}
    elems: dict[int, object] = {}
    for a in anchors:
        child, parent = a, a.parent
        while parent is not None and parent.name != "[document]":
            hits.setdefault(id(parent), {})[id(child)] = child
            elems[id(parent)] = parent
            child, parent = parent, parent.parent

    cands = []
    for pid, kids in hits.items():
        if len(kids) < 2:
            continue
        sig, n = Counter(_sig(k) for k in kids.values()).most_common(1)[0]
        members = [k for k in kids.values() if _sig(k) == sig]
        texts = [_clean(k.get_text(" ")) for k in members]
        good = [(k, t) for k, t in zip(members, texts) if _card_like(t)]
        if len(good) >= 2:
            cands.append((len(good), pid, good))
    cands.sort(key=lambda c: -c[0])

    cards, card_ids, ancestor_ids = [], set(), set()
    for n, pid, good in cands:
        cont = elems[pid]
        lineage = [cont, *cont.parents]
        if any(id(p) in card_ids for p in lineage) or pid in ancestor_ids:
            continue  # 既に採用したカードの内側、または採用した一覧を包む外側の要素
        for k, t in good:
            card_ids.add(id(k))
            cards.append((order.get(id(k), 0), t))
        ancestor_ids.update(id(p) for p in lineage)

    if not cards:
        # 1台だけのページなど繰り返しが無い場合: 価格要素から、価格表記が4つ以下の範囲で親を辿る
        best = None
        for a in anchors:
            el = a
            while el.parent is not None and el.parent.name not in ("body", "html", "[document]"):
                t = _clean(el.parent.get_text(" "))
                if len(_PRICE_ANY.findall(t)) > 4 or len(t) > 2000:
                    break
                el = el.parent
            t = _clean(el.get_text(" "))
            if _card_like(t) and (best is None or len(t) > len(best[1])):
                best = (order.get(id(el), 0), t)
        cards = [best] if best else []

    return [t for _, t in sorted(cards, key=lambda c: c[0])]


def detect_maker(text: str) -> str:
    up = text.upper()
    for k in _MAKER_KEYS:
        if k.upper() in up:
            return MAKERS[k]
    return "不明"


def detect_body(text: str) -> str:
    for name, pat in BODY_KEYWORDS:
        if re.search(pat, text):
            return name
    up = text.upper()
    for model, body in _MODEL_INDEX:
        if model in up:
            return body
    return "不明"


# ---------------------------------------------------------------- 年式

_ERA = {"令和": 2018, "R": 2018, "平成": 1988, "H": 1988, "昭和": 1925, "S": 1925}
_AFTER_NEN = r"(?!保証|落|間|経過|以内|超|目|分|毎|ごと)"  # 「3年保証」「5年落ち」などは年式ではない
_Y_AD = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*(?:年" + _AFTER_NEN + r"|(?=[(]\s*(?:令和|平成|R|H)\s*\d))")
_Y_ERA = re.compile(r"(?<![A-Za-z])(令和|平成|昭和|R|H|S)\s*(\d{1,2}|元)\s*\)?\s*年" + _AFTER_NEN)
_Y_SLASH = re.compile(r"(?<![\d.])((?:19|20)\d{2})\s*[/.]\s*(?:0?[1-9]|1[0-2])(?![\d.]|\s*万)")
_Y_LABEL = re.compile(r"年\s*式|初度登録|初年度登録|登録年月?|モデル年")
# ラベル直後は「2024」「R6」「令和6」のように「年」が無くても年式とみなす
_Y_AFTER_LABEL = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)|(?<![A-Za-z])(令和|平成|昭和|R|H)\s*(\d{1,2}|元)(?!\d)")
_Y_NOT_MODEL = re.compile(r"車検|検査|掲載|更新|入庫|納車|保証|点検|整備|リサイクル|有効")


def _era_year(era: str, n: str) -> int:
    return _ERA[era] + (1 if n == "元" else int(n))


def detect_year(text: str) -> int | None:
    """年式(西暦)を返す。「年式 2024」「年式(初度登録) R6」のようなラベル付きを最優先し、
    次に「2024年」「令和6年」「2024(R06)」「2024/04」を拾う。車検・掲載日などの年は除外。"""
    import datetime
    text = unicodedata.normalize("NFKC", text)
    hi = datetime.date.today().year + 1
    ok = lambda y: 1980 <= y <= hi  # noqa: E731

    for lab in _Y_LABEL.finditer(text):
        m = _Y_AFTER_LABEL.search(text, lab.end(), lab.end() + 16)
        if m:
            y = int(m.group(1)) if m.group(1) else _era_year(m.group(2), m.group(3))
            if ok(y):
                return y

    cands: list[tuple[int, int]] = []
    for m in _Y_AD.finditer(text):
        cands.append((m.start(), int(m.group(1))))
    for m in _Y_ERA.finditer(text):
        cands.append((m.start(), _era_year(m.group(1), m.group(2))))
    for m in _Y_SLASH.finditer(text):
        cands.append((m.start(), int(m.group(1))))
    cands = sorted((p, y) for p, y in cands if ok(y) and not _Y_NOT_MODEL.search(text[max(0, p - 8):p]))
    return cands[0][1] if cands else None


# ---------------------------------------------------------------- 走行距離

_KM_UNIT = r"(?:km|キロ)(?!\s*/|\s*[Lℓ]|メートル|\s*以内|\s*まで)"
_KM_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(万|千)?\s*" + _KM_UNIT, re.I)
_KM_LABEL = re.compile(r"走行(?:距離)?")
# ラベル直後は単位が別要素で欠けていても数値を走行距離とみなす（「走行距離 20」「走行 0.1万」）
_KM_AFTER_LABEL = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(万|千)?\s*(km|キロ)?(?!\s*[年ヶか月%])", re.I)
_KM_NOT_MILEAGE = re.compile(r"燃費|電費|航続|WLTC|JC08|保証|一充電|無制限")


def _km(num: str, mult: str | None) -> int:
    n = float(num.replace(",", ""))
    return int(round(n * {"万": 10000, "千": 1000}.get(mult or "", 1)))


def detect_mileage(text: str) -> int | None:
    """走行距離(km)を返す。「走行距離 0.1万km」「走行 20 km」「12,000km」「10㎞」等に対応。
    燃費(km/L)・航続距離・保証距離は除外。"""
    text = unicodedata.normalize("NFKC", text)
    for lab in _KM_LABEL.finditer(text):
        seg = text[lab.end():lab.end() + 16]
        m = _KM_AFTER_LABEL.search(seg)
        if m and m.start() <= 6 and not _KM_NOT_MILEAGE.search(seg[:m.start()]):
            km = _km(m.group(1), m.group(2))
            if km <= 500_000:
                return km

    for m in _KM_RE.finditer(text):
        if _KM_NOT_MILEAGE.search(text[max(0, m.start() - 12):m.start()]):
            continue
        km = _km(m.group(1), m.group(2))
        if km <= 500_000:
            return km
    return None


# ---------------------------------------------------------------- ページ送り

_PAGE_KEYS = {"page", "p", "pg", "pageno", "page_no", "paged", "pn", "pagenum", "currentpage"}
_NEXT_LABELS = {"次へ", "次のページ", "次ページ", "次", "›", "＞", ">", "→", "next", "next ›", "next >", "next »", "次へ ›", "次へ >"}
_NEXT_CLASS = re.compile(r"(^|[\s_-])next($|[\s_-])", re.I)


def _norm(u: str) -> str:
    return urldefrag(u)[0]


def _page_of(url: str) -> int | None:
    """URLから現在のページ番号を推定（page系クエリ / パスの /page/N・/pN）。"""
    u = urlparse(url)
    for k, v in parse_qsl(u.query):
        if k.lower() in _PAGE_KEYS and v.isdigit():
            return int(v)
    m = re.search(r"/(?:page/|p)(\d+)/?$", u.path)
    return int(m.group(1)) if m else None


def bump_page(url: str) -> str | None:
    """URL中のページ番号を +1 したURL。ページ番号が見当たらなければ None。"""
    u = urlparse(url)
    q = parse_qsl(u.query, keep_blank_values=True)
    for i, (k, v) in enumerate(q):
        if k.lower() in _PAGE_KEYS and v.isdigit():
            q[i] = (k, str(int(v) + 1))
            return urlunparse(u._replace(query=urlencode(q)))
    m = re.search(r"(/(?:page/|p))(\d+)(/?)$", u.path)
    if m:
        path = u.path[:m.start()] + m.group(1) + str(int(m.group(2)) + 1) + m.group(3)
        return urlunparse(u._replace(path=path))
    return None


def find_next_url(html: str, base: str, visited: set[str] | frozenset = frozenset(), page_no: int = 1) -> str | None:
    """次ページURLを探す。rel=next → 「次へ」系 → ページ番号リンク → URLのページ番号+1 の順。"""
    soup = BeautifulSoup(html, "html.parser")

    def ok(href: str | None) -> str | None:
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            return None
        u = _norm(urljoin(base, href))
        return u if u not in visited and u != _norm(base) else None

    # 1. rel=next
    for el in soup.select('a[rel~="next"], link[rel~="next"]'):
        if (u := ok(el.get("href"))):
            return u

    # 2. 「次へ」系のテキスト / aria-label / title / class
    for a in soup.find_all("a", href=True):
        labels = [a.get_text(" ", strip=True), a.get("aria-label", ""), a.get("title", "")]
        labels = [re.sub(r"\s+", " ", x).strip() for x in labels]
        if any(w in x for x in labels for w in ("最後", "最終", "前へ", "前の", "prev", "Prev", "last", "Last")):
            continue
        classes = " ".join(a.get("class", [])) + " " + " ".join((a.parent.get("class", []) if a.parent else []))
        if "disabled" in classes:
            continue
        hit = any(x.lower() in _NEXT_LABELS or x.startswith(("次へ", "次のページ")) for x in labels if x) \
            or bool(_NEXT_CLASS.search(classes))
        if hit and (u := ok(a["href"])):
            return u

    # 3. ページ番号リンク（現在ページより大きい最小の番号で、未訪問のもの）
    cur_no = _page_of(base) or page_no
    nums: dict[int, str] = {}
    for a in soup.find_all("a", href=True):
        t = a.get_text(strip=True)
        if t.isdigit() and len(t) <= 3 and (u := ok(a["href"])):
            nums.setdefault(int(t), u)
    for n in sorted(nums):
        if n > cur_no:
            return nums[n]

    # 4. URL中のページ番号を +1（リンクが取れないJS寄りのサイト向けの最後の手段）
    #    ページ番号リンクが見えているのに次がない = 最終ページなので、ここでは進まない
    if nums:
        return None
    nxt = bump_page(base)
    return nxt if nxt and nxt not in visited else None


# ---------------------------------------------------------------- 集計


def scrape(url: str, max_pages: int = 5, basis: str = "auto", delay: float = 1.0) -> dict:
    """URLから最大 max_pages ページ辿って車両リストを作る。"""
    session = requests.Session()
    vehicles, seen, pages, warnings = [], set(), 0, []
    cur: str | None = url
    visited: set[str] = set()
    while cur and pages < max_pages:
        visited.add(_norm(cur))
        try:
            final, html = fetch(cur, session)
        except (requests.RequestException, ValueError) as e:
            if pages == 0:
                raise
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status not in (404, 410):  # 404 は「最終ページを越えた」だけなので警告しない
                warnings.append(f"{pages + 1}ページ目の取得に失敗したため、{pages}ページ分の結果を表示しています（{e}）。")
            cur = None
            break
        pages += 1
        visited.add(_norm(final))
        added = 0
        for text in parse_cards(html):
            key = text[:200]
            if key in seen:
                continue
            seen.add(key)
            price = extract_price(text, basis)
            if price is None or price <= 0:
                continue
            vehicles.append({"price": price, "maker": detect_maker(text), "body": detect_body(text),
                             "year": detect_year(text), "mileage": detect_mileage(text), "text": text[:200]})
            added += 1
        if added == 0 and pages > 1:
            warnings.append(f"{pages}ページ目に新しい車両がなかったため、そこで終了しました。")
            cur = None
            break
        cur = find_next_url(html, final, visited, pages)
        if cur and pages < max_pages:
            time.sleep(delay)
    if not vehicles:
        warnings.append("車両を検出できませんでした。JavaScriptで描画されるサイトや、価格表記が特殊なサイトの可能性があります。")
    elif pages == 1 and cur is None:
        warnings.append("次ページのリンクを検出できなかったため、1ページ分のみ集計しています（ページ送りがJavaScript/POSTの場合は未対応）。")
    if cur and pages >= max_pages:
        warnings.append(f"{max_pages}ページで打ち切りました（次ページが残っています）。")
    return {"vehicles": vehicles, "pages": pages, "warnings": warnings}


