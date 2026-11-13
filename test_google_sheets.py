import base64
import hashlib
import json
from http.cookies import SimpleCookie
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import HTTPException
from starlette.requests import Request
import google_sheets as gs
from sheet_data import convert_rows

IDENTITY = "a" * 40
URL = "https://docs.google.com/spreadsheets/d/" + IDENTITY + "/edit"


def request(cookie="", query="", origin=""):
    headers = [(b"cookie", (gs.COOKIE + "=" + cookie).encode())] if cookie else []
    if origin:
        headers.append((b"origin", origin.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "query_string": query.encode(),
                    "headers": headers, "scheme": "http", "server": ("127.0.0.1", 80)})


class GoogleTests(unittest.TestCase):
    def setUp(self):
        gs.SESSIONS.clear()
        self.env = patch.dict("os.environ", {"GOOGLE_CLIENT_ID": "test-client",
            "GOOGLE_CLIENT_SECRET": "test-secret", "GOOGLE_REDIRECT_URI": "http://127.0.0.1/auth/google/callback"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_pkce_login_callback_and_replay(self):
        login = gs.login()
        cookie = SimpleCookie(); cookie.load(login.headers["set-cookie"])
        key = cookie[gs.COOKIE].value
        self.assertTrue(cookie[gs.COOKIE]["httponly"])
        params = parse_qs(urlparse(login.headers["location"]).query)
        self.assertEqual(params["scope"], [gs.SCOPE])
        verifier = gs.SESSIONS[key]["verifier"]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        self.assertEqual(params["code_challenge"], [challenge])
        token = Mock()
        token.json.return_value = {"access_token": "token-a", "token_type": "Bearer", "expires_in": 3600}
        query = urlencode({"state": params["state"][0], "code": "one-use-code"})
        with patch.object(gs.requests, "post", return_value=token) as post:
            result = gs.callback(request(key, query))
        self.assertEqual(result.headers["location"], "/?google=connected")
        self.assertEqual(post.call_args.kwargs["data"]["code_verifier"], verifier)
        with self.assertRaises(HTTPException):
            gs.callback(request(key, query))
        self.assertTrue(gs.status(request(key))["connected"])

    def test_callback_state_and_origin_rejected(self):
        gs.SESSIONS["a"] = {"state": "correct", "expires": time.time() + 300}
        with self.assertRaises(HTTPException) as error:
            gs.callback(request("a", "state=wrong&code=code"))
        self.assertEqual(error.exception.status_code, 400)
        with self.assertRaises(HTTPException) as error:
            gs.same_origin(request(origin="https://unrelated.example"))
        self.assertEqual(error.exception.status_code, 403)

    def test_sessions_are_isolated(self):
        gs.SESSIONS.update(a={"token": "token-a", "expires": time.time()+300},
                           b={"token": "token-b", "expires": time.time()+300})
        with patch.object(gs, "read_sheet", return_value={"rows": []}) as read:
            gs.preview(gs.PreviewRequest(url=URL), request("a"))
            self.assertEqual(read.call_args.args[1], "token-a")
            gs.preview(gs.PreviewRequest(url=URL), request("b"))
            self.assertEqual(read.call_args.args[1], "token-b")
        gs.logout(request("a"))
        self.assertFalse(gs.status(request("a"))["connected"])
        self.assertTrue(gs.status(request("b"))["connected"])

    def test_expired_session_and_missing_configuration(self):
        gs.SESSIONS["a"] = {"token":"expired", "expires": time.time()-1}
        with self.assertRaises(HTTPException) as error:
            gs.session(request("a"))
        self.assertEqual(error.exception.status_code, 401)
        with patch.dict("os.environ", {"GOOGLE_CLIENT_SECRET": ""}):
            with self.assertRaises(HTTPException) as error:
                gs.login()
            self.assertEqual(error.exception.status_code, 503)

    def test_selected_gid_and_google_destination(self):
        meta = Mock(status_code=200); meta.json.return_value = {
            "properties":{"title":"在庫表"},
            "sheets":[{"properties":{"title":"A","sheetId":0}},{"properties":{"title":"B's","sheetId":8}}]}
        values = Mock(status_code=200); values.json.return_value = {"values":[["価格","年式"],["150","2024"]]}
        meta.iter_content.return_value = [json.dumps(meta.json.return_value).encode()]
        values.iter_content.return_value = [json.dumps(values.json.return_value).encode()]
        with patch.object(gs.requests, "get", side_effect=[meta,values]) as get:
            result = gs.read_sheet(gs.PreviewRequest(url=URL+"#gid=8"), "user-token")
        self.assertEqual(result["sheet"],"B's")
        for call in get.call_args_list:
            self.assertTrue(call.args[0].startswith("https://sheets.googleapis.com/v4/spreadsheets/"))
            self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer user-token")
        self.assertIn("%27B%27%27s%27%21",get.call_args_list[1].args[0])

    def test_oversized_google_response_is_rejected(self):
        response = Mock(status_code=200)
        response.iter_content.return_value = [b"x" * (8 * 1024 * 1024 + 1)]
        with patch.object(gs.requests, "get", return_value=response):
            with self.assertRaises(HTTPException) as error:
                gs.api_get(IDENTITY, "test-token", {})
        self.assertEqual(error.exception.status_code, 413)
        response.close.assert_called_once()

    def test_invalid_destinations(self):
        for value in ["http://127.0.0.1/", "https://example.com/spreadsheets/d/"+IDENTITY, "https://docs.google.com/document/d/"+IDENTITY]:
            with self.subTest(value=value), self.assertRaises(HTTPException):
                gs.sheet_id(value)

    def test_invalid_token_clears_only_current_session(self):
        gs.SESSIONS.update(a={"token":"a", "expires":time.time()+300}, b={"token":"b","expires":time.time()+300})
        with patch.object(gs, "read_sheet", side_effect=HTTPException(401,"expired")):
            with self.assertRaises(HTTPException):
                gs.read_authorized(gs.PreviewRequest(url=URL), request("a"))
        self.assertFalse(gs.status(request("a"))["connected"])
        self.assertTrue(gs.status(request("b"))["connected"])

    def test_import_and_multiple_own_companies_rejected(self):
        gs.SESSIONS["a"] = {"token":"a","expires":time.time()+300}
        table = {"id":IDENTITY,"sheet":"在庫","headers":["会社","価格","年式","走行"],
                 "rows":[["A","150","2024",0],["B","250","R5","0.2万km"]],"truncated":False}
        body = gs.ImportRequest(url=URL, mapping={"company":0,"price":1,"year":2,"mileage":3})
        with patch.object(gs, "read_authorized", return_value=table):
            result = gs.import_sheet(body, request("a"))
            self.assertEqual(len(result["stores"]),2)
            self.assertEqual(result["stores"][0]["data"]["vehicles"][0]["mileage"],0)
            body.role = "own"
            with self.assertRaises(HTTPException) as error:
                gs.import_sheet(body, request("a"))
            self.assertEqual(error.exception.status_code,400)


class MappingTests(unittest.TestCase):
    def test_units_and_invalid_rows(self):
        result = convert_rows(["価格","年式","距離"],[["1,500,000","2024",0],["158万円","R6","0.3万km"],["応相談","2024","20"]],
            {"price":0,"year":1,"mileage":2},"自社","yen","km","source")
        vehicles = result["stores"][0]["data"]["vehicles"]
        self.assertEqual([v["price"] for v in vehicles],[150,158])
        self.assertEqual([v["mileage"] for v in vehicles],[0,3000])
        self.assertEqual([v["year"] for v in vehicles],[2024,2024])
        self.assertEqual(result["skipped_rows"],1)

    def test_ambiguous_or_missing_mapping(self):
        for mapping in [{"price":0}, {"price":0,"year":0}, {"price":3,"year":1}]:
            with self.assertRaises(ValueError):
                convert_rows(["価格","年式"],[["150","2024"]],mapping,"A","man","km","source")


if __name__ == "__main__":
    unittest.main()
