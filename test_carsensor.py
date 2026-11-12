"""Synthetic Carsensor-format fixtures; no live-site requests."""
import unittest
from unittest.mock import patch
from scraper import parse_cards, extract_price, detect_year, detect_mileage, find_next_url, bump_page, scrape


def card(vehicle_id, price=128.5):
    return f"""
    <div class="cassetteMain">
      <h3 class="cassetteMain__title"><a href="/usedcar/detail/{vehicle_id}/index.html">ホンダ N-BOX カスタム</a></h3>
      <div class="cassetteMain__price"><div class="totalPrice">支払総額（税込）<span>139.8</span>万円</div>
      <div class="basePrice">車両本体価格（税込）<span>{price}</span>万円</div><p>諸費用 11.3万円</p></div>
      <dl class="specList"><dt>年式</dt><dd>2024(R06)年</dd><dt>走行距離</dt><dd>0.3万km</dd>
      <dt>車検</dt><dd>2027年</dd><dt>保証</dt><dd>保証付 1年・1万km</dd></dl>
    </div>"""


class CarsensorTests(unittest.TestCase):
    def test_cards_specs_and_prices(self):
        cards = parse_cards("<html>" + card("AU0000000001") + card("AU0000000002") + "</html>")
        self.assertEqual(len(cards), 2)
        self.assertEqual(extract_price(cards[0]), 128.5)
        self.assertEqual(extract_price(cards[0], "total"), 139.8)
        self.assertEqual(detect_year(cards[0]), 2024)
        self.assertEqual(detect_mileage(cards[0]), 3000)
        self.assertNotEqual(cards[0], cards[1])

    def test_single_vehicle(self):
        self.assertEqual(len(parse_cards(card("AU0000000001"))), 1)

    def test_pagination(self):
        base = "https://www.carsensor.net/usedcar/bHO/s094/index2.html"
        self.assertEqual(find_next_url('<a href="index3.html">次へ</a>', base),
                         "https://www.carsensor.net/usedcar/bHO/s094/index3.html")
        self.assertEqual(bump_page(base), "https://www.carsensor.net/usedcar/bHO/s094/index3.html")
        self.assertEqual(bump_page("https://www.carsensor.net/usedcar/bHO/s094/index.html"),
                         "https://www.carsensor.net/usedcar/bHO/s094/index2.html")
        self.assertEqual(bump_page("https://www.carsensor.net/usedcar/search.php?STID=x&PN=2"),
                         "https://www.carsensor.net/usedcar/search.php?STID=x&PN=3")
        self.assertEqual(find_next_url('<a href="?PN=2">2</a><a href="?PN=3">3</a>', base),
                         "https://www.carsensor.net/usedcar/bHO/s094/index2.html?PN=3")

    def test_500_pages_and_distinct_vehicle_ids(self):
        def fetch(url, session):
            from urllib.parse import urlparse, parse_qs
            number = int(parse_qs(urlparse(url).query).get("PN", ["1"])[0])
            nxt = f'<a rel="next" href="?PN={number+1}">次へ</a>' if number < 500 else ""
            return url, card(f"AU{number:010d}") + nxt
        with patch("scraper.fetch", side_effect=fetch), patch("scraper.time.sleep"):
            result = scrape("https://www.carsensor.net/usedcar/search.php?PN=1", max_pages=500)
        self.assertEqual(result["pages"], 500)
        self.assertEqual(len(result["vehicles"]), 500)
        self.assertEqual(len({v["id"] for v in result["vehicles"]}), 500)

    def test_incremental_next_url(self):
        html = card("AU0000000001") + '<a rel="next" href="?PN=2">次へ</a>'
        with patch("scraper.fetch", return_value=("https://www.carsensor.net/usedcar/search.php?PN=1", html)):
            result = scrape("https://www.carsensor.net/usedcar/search.php?PN=1", max_pages=1)
        self.assertEqual(result["next_url"], "https://www.carsensor.net/usedcar/search.php?PN=2")


if __name__ == "__main__":
    unittest.main()
