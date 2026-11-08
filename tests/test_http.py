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
        self.assertEqual(catalog[1]["status"], "playable")
        self.assertEqual([entry["id"] for entry in catalog],
                         ["four-color", "fourfold", "skip-bo", "21", "blackjack", "knuckles"])
        self.assertTrue(all(entry["status"] == "playable" for entry in catalog))
        self.assertEqual(self.request("/api/assets")[0]["faces"], 119)
        asset_report = {entry["collection"]: entry for entry in self.request("/api/assets")}
        self.assertTrue(asset_report["colors"]["game_subsets"]["skip-bo"]["ready"])
        self.assertEqual(asset_report["colors"]["game_subsets"]["skip-bo"]["faces"], 52)
        self.assertEqual(asset_report["colors"]["game_subsets"]["skip-bo"]["instances"], 162)
        for game in ("21", "blackjack", "knuckles"):
            self.assertTrue(asset_report["symbols"]["game_subsets"][game]["ready"])
            self.assertEqual(asset_report["symbols"]["game_subsets"][game]["faces"], 52)
        match = self.request("/api/matches", {"difficulty": "hard", "participants": [
            {"id": "me", "name": "Me", "kind": "human"}, {"id": "bot", "name": "SLAI", "kind": "ai"}]})
        self.assertEqual(match["ai_difficulty"], "hard")
        self.assertEqual(match["draw_count"], 104)
        self.assertEqual(len(match["players"][0]["hand"]), 7)
        self.assertEqual(len(match["players"][1]["hand"]), 0)
        self.assertEqual(len(self.request(f"/api/matches/{match['id']}?viewer=bot")["players"][1]["hand"]), 0)
        result = self.request(f"/api/matches/{match['id']}/actions", {
            "actor": "me", "revision": 0, "command": "draw", "args": {}})
        self.assertGreaterEqual(result["revision"], 1)
        with self.assertRaises(HTTPError) as raised:
            self.request(f"/api/matches/{match['id']}/actions", {
                "actor": "me", "revision": 0, "command": "draw", "args": {}})
        self.assertEqual(raised.exception.code, 400)
        self.assertEqual(len(self.request("/api/matches")), 1)
        self.assertEqual(self.request("/api/stats")["total"], 1)

    def test_fourfold_http_round_and_concealed_orders(self):
        match = self.request("/api/matches", {"game": "fourfold", "participants": [
            {"id": "alice", "kind": "human"}, {"id": "bob", "kind": "human"}]})
        self.assertEqual(match["round"], 1)
        first = self.request(f"/api/matches/{match['id']}/actions", {
            "actor": "alice", "command": "submit", "revision": 0,
            "args": {"orders": [{"card": "04-hearts"}]}})
        self.assertTrue(first["players"][0]["ready"])
        concealed = self.request(f"/api/matches/{match['id']}?viewer=bob")
        self.assertNotIn("orders", concealed["players"][0])
        self.request(f"/api/matches/{match['id']}/actions", {
            "actor": "bob", "command": "submit", "revision": 1,
            "args": {"orders": [{"card": "04-hearts"}]}})
        self.assertEqual(self.request(f"/api/matches/{match['id']}")["round"], 2)

    def test_fourfold_slai_ai_commits_without_exposing_its_order(self):
        match = self.request("/api/matches", {"game": "fourfold", "participants": [
            {"id": "me", "kind": "human"}, {"id": "agent", "kind": "ai"}]})
        self.assertTrue(match["players"][1]["ready"])
        self.assertNotIn("orders", match["players"][1])
        result = self.request(f"/api/matches/{match['id']}/actions", {
            "actor": "me", "command": "submit", "revision": match["revision"], "args": {"orders": []}})
        self.assertEqual(result["round"], 2)
        self.assertTrue(result["players"][1]["ready"])

    def test_new_game_families_use_authoritative_http_and_recovery(self):
        for game in ("skip-bo", "21", "blackjack", "knuckles"):
            with self.subTest(game=game):
                match = self.request("/api/matches", {"game": game, "difficulty": "expert", "participants": [
                    {"id": "me", "kind": "human"}, {"id": "agent", "kind": "ai"}]})
                self.assertEqual(match["game"], game)
                if match["phase"] == "play":
                    self.assertEqual(match["players"][1]["hand"], [])
                recovered = self.request(f"/api/matches/{match['id']}?viewer=me")
                self.assertEqual(recovered["revision"], match["revision"])
                self.assertEqual(recovered["legal_actions"], match["legal_actions"])
                with self.assertRaises(HTTPError) as denied:
                    self.request(f"/api/matches/{match['id']}/actions", {
                        "actor": "agent", "revision": match["revision"], "command": "hit", "args": {}})
                self.assertEqual(denied.exception.code, 400)
                if match["phase"] == "play":
                    action = match["legal_actions"][0]
                    updated = self.request(f"/api/matches/{match['id']}/actions", {
                        "actor": "me", "revision": match["revision"], **action})
                    self.assertGreater(updated["revision"], match["revision"])
                    if updated["phase"] == "play":
                        self.assertEqual(updated["players"][1]["hand"], [])
                    with self.assertRaises(HTTPError) as stale:
                        self.request(f"/api/matches/{match['id']}/actions", {
                            "actor": "me", "revision": match["revision"], **action})
                    self.assertEqual(stale.exception.code, 400)

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

    def test_plus_action_art_uses_existing_unmodified_card_images(self):
        # SLAI's generic static allowlist excludes '+'. Card Games provides a
        # whitelisted alias without renaming or duplicating the original files.
        for face in ("+1-blue", "+2-neutral", "+4-red", "+5-yellow"):
            alias = "plus" + face[1:]
            response = self.browser.open(self.base + f"/api/card-art/{alias}")
            self.assertEqual(response.headers.get_content_type(), "image/jpeg")
            self.assertEqual(response.read(), (ROOT / "cards" / "colors" / f"{face}.jpg").read_bytes())
        for invalid in ("plus99-blue", "plus5-purple", "cover", "plus5-yellow.jpg"):
            with self.subTest(invalid=invalid), self.assertRaises(HTTPError) as rejected:
                self.browser.open(self.base + f"/api/card-art/{invalid}")
            self.assertEqual(rejected.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
