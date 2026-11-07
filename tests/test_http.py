"""Shared SLAI server integration, requiring the actual applications/tools checkout."""

import http.cookiejar
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


try:
    from applications.tools.server import Identity, LocalServer, ServerOptions
    from app.service import CardGamesService
    from slai.app import ROOT, build_router
except ImportError:
    LocalServer = None


@unittest.skipIf(LocalServer is None, "Run with SLAI_ROOT on PYTHONPATH for shared-toolkit tests")
class SharedServerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.service = CardGamesService(Path(self.folder.name))
        app = type("TestApp", (), {"service": self.service})()
        self.server = LocalServer(app, Identity("card_games", "Card Games"), build_router(), ServerOptions(
            token="local-test-token", client_dir=ROOT / "src" / "client", port=0,
        ))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.browser = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.base = self.server.base_url
        self.browser.open(self.base + "/?token=local-test-token").read()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.service.close()
        self.folder.cleanup()

    def request(self, path, data=None, method=None):
        payload = json.dumps(data).encode() if data is not None else None
        request = Request(self.base + path, data=payload, method=method or ("POST" if payload is not None else "GET"),
                          headers={"X-SLAI-card_games": "1", "Content-Type": "application/json"})
        return json.loads(self.browser.open(request).read())["data"]

    def test_create_view_and_reject_stale_revision(self):
        catalog = self.request("/api/catalog")
        self.assertEqual(catalog[0]["status"], "playable")
        self.assertEqual(catalog[1]["status"], "rules-pending")
        self.assertEqual(self.request("/api/assets")[0]["faces"], 119)
        match = self.request("/api/matches", {"difficulty": "hard", "participants": [
            {"id": "me", "name": "Me", "kind": "human"}, {"id": "bot", "name": "SLAI", "kind": "ai"}]})
        self.assertEqual(match["ai_difficulty"], "hard")
        self.assertEqual(match["draw_count"], 104)
        self.assertEqual(len(match["players"][0]["hand"]), 7)
        self.assertEqual(len(match["players"][1]["hand"]), 0)
        result = self.request(f"/api/matches/{match['id']}/actions", {
            "actor": "me", "revision": 0, "command": "draw", "args": {}})
        self.assertGreaterEqual(result["revision"], 1)
        with self.assertRaises(HTTPError) as raised:
            self.request(f"/api/matches/{match['id']}/actions", {
                "actor": "me", "revision": 0, "command": "draw", "args": {}})
        self.assertEqual(raised.exception.code, 400)
        self.assertEqual(len(self.request("/api/matches")), 1)
        self.assertEqual(self.request("/api/stats")["total"], 1)

    def test_settings_roundtrip_and_security_marker(self):
        settings = self.request("/api/settings")
        self.assertEqual(settings["theme"], "dark")
        updated = self.request("/api/settings", {"theme": "light", "difficulty": "hard"}, method="PUT")
        self.assertEqual(updated["theme"], "light")
        self.assertEqual(self.request("/api/settings")["difficulty"], "hard")
        with self.assertRaises(HTTPError) as raised:
            self.browser.open(Request(self.base + "/api/settings", data=b"{}", method="PUT",
                                      headers={"Content-Type": "application/json"}))
        self.assertEqual(raised.exception.code, 401)


if __name__ == "__main__":
    unittest.main()
