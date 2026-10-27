import scraper
from scraper import (assert_public_url, bump_page, detect_body, detect_maker, detect_mileage, detect_year,
                     extract_price, find_next_url, parse_cards, scrape)

CARDS = """
<li><h3>トヨタ アルファード 2.5 S</h3><p>車両本体価格 398.0万円</p><p>支払総額 420.5万円</p></li>
<li><h3>ホンダ N-BOX カスタム</h3><p>車両本体価格 128万円</p><p>支払総額 139.8万円</p></li>
<li><h3>日産 ノート e-POWER</h3><p>本体価格 ¥1,480,000</p></li>
<li><h3>BMW X3 xDrive20d SUV</h3><p>車両本体価格 520.0万円</p><p>支払総額 545万円</p></li>
<li><h3>スズキ ジムニーシエラ</h3><p>車両本体価格 215万円</p></li>
"""

# ---- 1ページ内の抽出
cards = parse_cards(f"<html><body><ul>{CARDS}</ul></body></html>")
assert len(cards) == 5
assert [extract_price(c) for c in cards] == [398.0, 128.0, 148.0, 520.0, 215.0]
assert [detect_body(c) for c in cards] == ["ミニバン", "軽自動車", "コンパクト", "SUV", "SUV"]
assert extract_price(cards[0], "total") == 420.5
assert detect_maker(cards[3]) == "BMW"

# ---- 実サイトに近い構造：1台に価格が3つ（支払総額・本体・諸費用）＋諸元表
def motorfan_card(name, total, body, year, km):
    return f"""
<li class="cassette js-item">
  <h3 class="cassette__title"><a href="/d/1">{name}</a></h3>
  <div class="cassette__price">
    <dl><dt>支払総額</dt><dd><span class="num">{total}</span><span>万円</span></dd></dl>
    <dl><dt>車両本体価格</dt><dd><span class="num">{body}</span>万円</dd></dl>
    <dl><dt>諸費用</dt><dd>5万円</dd></dl>
  </div>
  <table class="spec"><tr><th>年式(初度登録)</th><td>{year}</td></tr><tr><th>走行</th><td>{km}</td></tr>
    <tr><th>車検</th><td>検10.9</td></tr><tr><th>保証</th><td>保証有。 [保証付]：3ヶ月・3000km</td></tr></table>
</li>"""

MF = f"""<html><body>
<aside><ul class="filter"><li><a>〜50万円</a></li><li><a>50〜100万円</a></li><li><a>100〜150万円</a></li><li><a>150万円〜</a></li></ul></aside>
<ul class="cassettes">
{motorfan_card("ハイゼットトラック スタンダード 届出済未使用車 衝突軽減ブレーキ", 104.8, 99.8, "2026年", "20km")}
{motorfan_card("ハイゼットカーゴ DX 届出済未使用車", 119.8, 114.8, "R7", "１５㎞")}
{motorfan_card("スペーシア ハイブリッドG 届出済未使用車", 134.8, 129.8, "２０２５", "0.1万km")}
{motorfan_card("ノート X 登録済未使用車", 229.8, 219.0, "2024(R06)", "8<span>km</span>")}
</ul></body></html>"""
mf = parse_cards(MF)
assert len(mf) == 4, mf                                         # 絞り込みメニューの「〜50万円」は車両にしない
assert [extract_price(c) for c in mf] == [99.8, 114.8, 129.8, 219.0]
assert [extract_price(c, "total") for c in mf] == [104.8, 119.8, 134.8, 229.8]
assert [detect_year(c) for c in mf] == [2026, 2025, 2025, 2024], [detect_year(c) for c in mf]
assert [detect_mileage(c) for c in mf] == [20, 15, 1000, 8], [detect_mileage(c) for c in mf]

# 最終ページに2台だけ → それでもカード単位で取れる（価格要素がバラバラに「車」扱いされない）
mf2 = parse_cards(f"<html><body><ul class='c'>{motorfan_card('タント X', 160, 150, '2025年', '5km')}"
                  f"{motorfan_card('ムーヴ L', 140, 130, '2025年', '9km')}</ul></body></html>")
assert len(mf2) == 2 and [extract_price(c) for c in mf2] == [150, 130]

# 1台だけのページ
one = parse_cards(f"<html><body><div class='detail'>{motorfan_card('N-BOX カスタム', 210, 199.8, '2025年', '12km')}</div></body></html>")
assert len(one) == 1 and extract_price(one[0]) == 199.8 and detect_year(one[0]) == 2025 and detect_mileage(one[0]) == 12

# dt/dd 形式・月々払いあり・価格の数字と単位が別タグ
DL = "".join(f"""<div class="car-item"><p class="name">スズキ ハスラー HYBRID G {i}</p>
<dl><dt>価格</dt><dd><em>{150 + i}</em><small>万円</small></dd><dt>月々</dt><dd>9,800円〜</dd>
<dt>年式</dt><dd>R{5 + i % 2}</dd><dt>走行距離</dt><dd>{10 + i}</dd><dt>燃費</dt><dd>25.0km/L</dd></dl></div>""" for i in range(3))
dl = parse_cards(f"<html><body><section class='list'>{DL}</section></body></html>")
assert len(dl) == 3
assert [extract_price(c) for c in dl] == [150, 151, 152]
assert [detect_year(c) for c in dl] == [2023, 2024, 2023]
assert [detect_mileage(c) for c in dl] == [10, 11, 12]

# ---- 年式
from scraper import detect_year
assert detect_year("トヨタ ヤリス 2023年式 走行0.1万km") == 2023
assert detect_year("年式 令和5年 本体 128万円") == 2023
assert detect_year("R5年 ノート") == 2023
assert detect_year("H30年 アルファード") == 2018
assert detect_year("平成元年 スカイライン") == 1989
assert detect_year("車検 2027年3月 年式 2024年") == 2024          # 車検の年を拾わない
assert detect_year("車検 2027年3月 2024年 ノート") == 2024
assert detect_year("年式 2022/04 走行3km") == 2022
assert detect_year("初度登録 令和6年8月") == 2024
assert detect_year("2021(令和3)年式") == 2021
assert detect_year("ES 5年保証 車両本体価格 2020.5万円") is None   # 保証年数・価格を年式と誤認しない
assert detect_year("本体 128万円") is None
assert detect_year("年式 2024 走行 5km") == 2024                    # ラベル直後は「年」が無くてもOK
assert detect_year("年式：R6 走行 5km") == 2024
assert detect_year("年式 令和元") == 2019
assert detect_year("掲載日 2026年10月1日 ノート 2024年式") == 2024   # 掲載日を拾わない
assert detect_year("年式 ２０２３年 走行 ３ｋｍ") == 2023            # 全角

# ---- 走行距離
from scraper import detect_mileage
assert detect_mileage("走行距離 0.1万km 年式 2024年") == 1000
assert detect_mileage("走行：5ｋｍ") == 5
assert detect_mileage("走行距離 12,000km") == 12000
assert detect_mileage("走行 10キロ") == 10
assert detect_mileage("燃費 25.4km/L 走行距離 8km") == 8                 # 燃費を拾わない
assert detect_mileage("WLTC 21.0km/ℓ 3km") == 3
assert detect_mileage("サクラ 航続距離 180km 走行距離 6km") == 6         # 航続距離を拾わない
assert detect_mileage("保証 3年/6万km 走行 15km") == 15                 # 保証距離を拾わない
assert detect_mileage("ヤリス 本体 168万円 7km") == 7
assert detect_mileage("ヤリス 本体 168万円") is None
assert detect_year("年式 2024年 走行距離 1.2万km") == 2024
assert detect_mileage("走行距離 20") == 20                           # 単位が別要素で欠けている
assert detect_mileage("走行 10㎞") == 10
assert detect_mileage("走行距離 1.5千km") == 1500
assert detect_mileage("走行距離無制限保証 1年 走行 7km") == 7
assert detect_mileage("走行 ３ｋｍ") == 3

# ---- ページ送りの検出パターン
B = "https://shop.example/stock/"
def nxt(html, base=B, visited=frozenset(), n=1):
    return find_next_url(f"<html><body>{html}</body></html>", base, visited, n)

assert nxt('<a rel="next" href="?page=2">x</a>') == B + "?page=2"
assert nxt('<a href="/stock/?p=2">次へ</a>') == "https://shop.example/stock/?p=2"
assert nxt('<a href="/s/2" aria-label="次のページ"><i class="icon"></i></a>') == "https://shop.example/s/2"
assert nxt('<li class="pager-next"><a href="/s/2">›</a></li>') == "https://shop.example/s/2"
assert nxt('<a href="/s/1">1</a><a href="/s/2">2</a><a href="/s/3">3</a>') == "https://shop.example/s/2"
assert nxt('<a href="?page=1">1</a><a href="?page=2">2</a><a href="?page=3">3</a>', base=B + "?page=2") == B + "?page=3"
assert nxt('<a href="/s/last">最後へ</a>') is None            # 「最後」は次ページではない
assert nxt('<li class="next disabled"><a href="/s/9">次へ</a></li>') is None
assert nxt('', base=B + "?page=4") == B + "?page=5"            # リンクが取れなくてもURLのページ番号を+1
assert nxt('<a href="?page=2">次へ</a>', visited={B + "?page=2"}) is None   # 訪問済みは辿らない
assert bump_page("https://x.jp/list/page/3/") == "https://x.jp/list/page/4/"
assert bump_page("https://x.jp/list/") is None

# ---- 複数ページを辿る scrape（通信はスタブ）
def make(i, last):
    cars = "".join(f"<li><h3>トヨタ ヤリス {i}-{k}</h3><p>車両本体価格 {100 + i * 10 + k}万円</p></li>" for k in range(3))
    nxt_a = "" if last else f'<a href="?page={i + 1}">次へ</a>'
    return f"<html><body><ul>{cars}</ul>{nxt_a}</body></html>"

PAGES = {f"https://shop.example/stock?page={i}": make(i, i == 4) for i in range(2, 5)}
PAGES["https://shop.example/stock"] = make(1, False).replace("?page=2", "?page=2")
import requests

def stub(url, s):
    if url not in PAGES:
        raise requests.HTTPError("404", response=type("R", (), {"status_code": 404})())
    return url, PAGES[url]

scraper.fetch = stub
scraper.time.sleep = lambda s: None

r = scrape("https://shop.example/stock", max_pages=10)
assert r["pages"] == 4 and len(r["vehicles"]) == 12 and not r["warnings"], r   # 最終ページ越えの404は警告しない
assert nxt('<a href="?page=3">3</a>', base=B + "?page=4") is None             # 最終ページでは進まない
r = scrape("https://shop.example/stock", max_pages=2)
assert r["pages"] == 2 and any("打ち切り" in w for w in r["warnings"])

# 2ページ目の取得に失敗しても、1ページ目の結果は残す
def flaky(url, s):
    if "page=2" in url:
        raise requests.ConnectionError("boom")
    return url, PAGES[url]
scraper.fetch = flaky
r = scrape("https://shop.example/stock", max_pages=5)
assert r["pages"] == 1 and len(r["vehicles"]) == 3 and r["warnings"], r

# ---- SSRF
for bad in ["http://127.0.0.1/", "http://localhost:8000", "ftp://x.com", "http://169.254.169.254/"]:
    try:
        assert_public_url(bad); raise SystemExit(f"NOT BLOCKED {bad}")
    except ValueError:
        pass

print("ALL OK")
