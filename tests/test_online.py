"""Authentication, concealed information and concurrent-action properties."""

import tempfile
from pathlib import Path
import unittest
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.game import GameError
from slai.online import OnlineRooms, RoomError, handler_factory


class OnlineRoomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = OnlineRooms(Path(self.temp.name) / "rooms.sqlite3")
        self.participants = [{"id": "host", "kind": "human"}, {"id": "friend", "kind": "human"}]

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_invitation_is_one_time_and_private_cards_are_isolated(self):
        created = self.store.create("four-color", self.participants)
        room, host = created["room"], created["token"]
        invite = self.store.invite(room, host, "friend")
        joined = self.store.join(room, invite["invite"])
        self.assertNotEqual(joined["token"], host)
        with self.assertRaises(RoomError):
            self.store.join(room, invite["invite"])
        self.assertEqual(len(self.store.view(room, host)["players"][0]["hand"]), 7)
        self.assertEqual(len(self.store.view(room, host)["players"][1]["hand"]), 0)
        self.assertEqual(len(self.store.view(room, joined["token"])["players"][0]["hand"]), 0)
        self.assertEqual(len(self.store.view(room, joined["token"])["players"][1]["hand"]), 7)
        with self.assertRaises(RoomError):
            self.store.view(room, invite["invite"])

    def test_actions_are_seat_authorized_idempotent_and_revisions_guarded(self):
        created = self.store.create("four-color", self.participants)
        room, token = created["room"], created["token"]
        guest = self.store.join(room, self.store.invite(room, token, "friend")["invite"])["token"]
        with self.assertRaises(GameError):
            self.store.act(room, guest, 0, "not-my-turn", "draw", {})
        before = self.store.view(room, token)
        accepted = self.store.act(room, token, before["revision"], "request-1", "draw", {})
        self.assertFalse(accepted["replayed"])
        again = self.store.act(room, token, before["revision"], "request-1", "draw", {})
        self.assertTrue(again["replayed"])
        self.assertEqual(again["state"]["revision"], accepted["state"]["revision"])
        with self.assertRaises(RoomError) as raised:
            self.store.act(room, token, before["revision"], "request-2", "draw", {})
        self.assertEqual(raised.exception.status, 409)

    def test_host_revokes_seat_and_guest_cannot_invite(self):
        created = self.store.create("four-color", self.participants)
        room, token = created["room"], created["token"]
        guest = self.store.join(room, self.store.invite(room, token, "friend")["invite"])["token"]
        with self.assertRaises(RoomError):
            self.store.invite(room, guest, "host")
        self.store.revoke(room, token, "friend")
        with self.assertRaises(RoomError) as raised:
            self.store.view(room, guest)
        self.assertEqual(raised.exception.status, 401)

    def test_fourfold_private_orders_and_persistent_reload(self):
        created = self.store.create("fourfold", self.participants)
        room, token = created["room"], created["token"]
        guest = self.store.join(room, self.store.invite(room, token, "friend")["invite"])["token"]
        response = self.store.act(room, token, 0, "first-plan", "submit", {"orders": [{"card": "04-hearts"}]})
        self.assertTrue(response["state"]["players"][0]["ready"])
        self.assertNotIn("orders", self.store.view(room, guest)["players"][0])
        self.store.close()
        self.store = OnlineRooms(Path(self.temp.name) / "rooms.sqlite3")
        self.assertTrue(self.store.view(room, guest)["players"][0]["ready"])
        self.store.act(room, guest, 1, "second-plan", "submit", {"orders": [{"card": "04-hearts"}]})
        self.assertEqual(self.store.view(room, token)["round"], 2)

    def test_http_origin_auth_and_json_limits(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(self.store, "http://127.0.0.1:9999"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def request(path, data=None, token=None, origin=None):
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            if origin:
                headers["Origin"] = origin
            payload = json.dumps(data).encode() if data is not None else None
            return urlopen(Request(base + path, data=payload, headers=headers)).read()

        try:
            created = json.loads(request("/rooms", {"game": "fourfold", "participants": self.participants}))
            self.assertTrue(created["ok"])
            room = created["data"]["room"]
            with self.assertRaises(HTTPError) as unauthorized:
                request(f"/rooms/{room}")
            self.assertEqual(unauthorized.exception.code, 401)
            with self.assertRaises(HTTPError) as forbidden:
                request(f"/rooms/{room}", token=created["data"]["token"], origin="https://unknown.example")
            self.assertEqual(forbidden.exception.code, 403)
            data = json.loads(request(f"/rooms/{room}", token=created["data"]["token"]))
            self.assertEqual(data["data"]["game"], "fourfold")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
