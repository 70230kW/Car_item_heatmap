"""公開用起動・HTTP配信・取得処理の回帰テスト。外部サイトへアクセスしない。"""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen, Request

import requests
from fastapi import HTTPException
import main

ROOT = Path(__file__).resolve().parent


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        cls.log = tempfile.TemporaryFile()
        cls.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--app-dir", str(ROOT),
             "--host", "127.0.0.1", "--port", str(port), "--workers", "1"],
            cwd=tempfile.gettempdir(), stdout=cls.log, stderr=cls.log,
        )
        try:
            for _ in range(100):
                if cls.process.poll() is not None:
                    break
                try:
                    with urlopen(cls.base + "/healthz", timeout=1) as response:
                        if response.status == 200:
                            return
                except OSError:
                    time.sleep(.1)
            cls.log.seek(0)
            raise RuntimeError(cls.log.read().decode())
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        try:
            cls.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait()
        cls.log.close()

    def test_health(self):
        with urlopen(self.base + "/healthz") as response:
            self.assertEqual(json.load(response), {"status": "ok"})

    def test_html_works_outside_checkout_working_directory(self):
        for route in ("/", "/static/index.html"):
            with self.subTest(route=route), urlopen(self.base + route) as response:
                self.assertEqual(response.read(), (ROOT / "index.html").read_bytes())

    def test_local_plotly(self):
        with urlopen(self.base + "/assets/plotly-2.35.2.min.js") as response:
            self.assertEqual(response.read(), (ROOT / "assets/plotly-2.35.2.min.js").read_bytes())

    def test_favicon(self):
        with urlopen(self.base + "/favicon.ico") as response:
            self.assertEqual(response.read(), (ROOT / "assets/favicon.ico").read_bytes())
        for name in ("favicon.svg", "apple-touch-icon.png", "app-icon-512.png"):
            with self.subTest(name=name), urlopen(self.base + "/assets/" + name) as response:
                self.assertEqual(response.status, 200)

    def test_google_status_and_unauthenticated_import(self):
        with urlopen(self.base + "/api/google/status") as response:
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertFalse(json.load(response)["connected"])
        request = Request(self.base + "/api/google/preview",
                          data=json.dumps({"url": "https://docs.google.com/spreadsheets/d/" + "a"*40 + "/edit"}).encode(),
                          headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 401)
        self.assertEqual(error.exception.headers["Cache-Control"], "no-store")

    def test_input_errors_and_ssrf(self):
        for route, status in (
            ("/api/analyze", 422),
            ("/api/analyze?url=http://127.0.0.1/", 400),
            ("/api/analyze?url=http://127.0.0.1/&max_pages=500", 400),
            ("/api/analyze?url=http://127.0.0.1/&max_pages=501", 422),
            ("/api/analyze-page?url=http://127.0.0.1/", 400),
            ("/api/analyze?url=https://example.com&max_pages=0", 422),
            ("/api/analyze?url=https://example.com&basis=invalid", 422),
        ):
            with self.subTest(route=route), self.assertRaises(HTTPError) as error:
                urlopen(self.base + route, timeout=5)
            self.assertEqual(error.exception.code, status)


class AnalyzeTests(unittest.TestCase):
    def call(self):
        return main.analyze("https://example.com/stock", max_pages=1, basis="auto")

    def test_success(self):
        data = {"vehicles": [{"price": 100, "year": 2024, "mileage": 20}], "pages": 1, "warnings": []}
        with patch.object(main, "scrape", return_value=data) as scrape:
            self.assertEqual(self.call(), data)
            scrape.assert_called_once_with("https://example.com/stock", max_pages=1, basis="auto")

    def test_failure_releases_capacity(self):
        for failure, status in ((ValueError("invalid"), 400), (requests.ConnectionError("unavailable"), 502)):
            with patch.object(main, "scrape", side_effect=failure):
                with self.assertRaises(HTTPException) as error:
                    self.call()
                self.assertEqual(error.exception.status_code, status)
        with patch.object(main, "scrape", return_value={"vehicles": []}):
            self.assertEqual(self.call(), {"vehicles": []})

    def test_single_page_endpoint(self):
        data = {"vehicles": [], "pages": 1, "warnings": ["1ページで打ち切りました（次ページが残っています）。"], "next_url": "https://example.com/?page=2"}
        with patch.object(main, "scrape", return_value=data):
            result = main.analyze_page("https://example.com/", basis="auto")
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["next_url"], "https://example.com/?page=2")

    def test_busy_response(self):
        main.SCRAPE_SLOTS.acquire()
        main.SCRAPE_SLOTS.acquire()
        try:
            with patch.object(main, "scrape") as scrape:
                with self.assertRaises(HTTPException) as error:
                    self.call()
                self.assertEqual(error.exception.status_code, 503)
                self.assertEqual(error.exception.headers, {"Retry-After": "5"})
                scrape.assert_not_called()
        finally:
            main.SCRAPE_SLOTS.release()
            main.SCRAPE_SLOTS.release()


if __name__ == "__main__":
    unittest.main()
