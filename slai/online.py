"""Independently hosted authoritative online rooms for Card Games.

This service is deliberately NOT the privileged SLAI LocalServer. A seat token is
an authenticated room capability. Run behind TLS before serving remote clients.
The implementation does not claim integrated global accounts or matchmaking.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sqlite3
import ssl
import threading
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from app.fourfold import FourfoldMatch
from app.game import GameError, Match


def digest(token: str) -> str:
    if not isinstance(token, str) or not 1 <= len(token) <= 200:
        raise RoomError("Invalid authentication token", 401)
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class RoomError(GameError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class OnlineRooms:
    """SQLite-backed server authority: clients never submit actor identity/state."""

    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        with self._write():
            self.db.execute("CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, host_hash TEXT NOT NULL, state TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS seats (token_hash TEXT PRIMARY KEY, room_id TEXT NOT NULL, player_id TEXT NOT NULL, expires REAL NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS invites (invite_hash TEXT PRIMARY KEY, room_id TEXT NOT NULL, player_id TEXT NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0)")
            self.db.execute("CREATE TABLE IF NOT EXISTS actions (room_id TEXT NOT NULL, player_id TEXT NOT NULL, action_id TEXT NOT NULL, PRIMARY KEY(room_id,player_id,action_id))")

    @contextmanager
    def _write(self):
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            else:
                self.db.execute("COMMIT")

    def close(self):
        self.db.close()

    def _row(self, sql: str, args: tuple[Any, ...]):
        return self.db.execute(sql, args).fetchone()

    def _room(self, room_id: str) -> tuple[sqlite3.Row, Match | FourfoldMatch]:
        row = self._row("SELECT * FROM rooms WHERE id=?", (room_id,))
        if not row:
            raise RoomError("Room not found", 404)
        state = json.loads(row["state"])
        return row, (FourfoldMatch if state["game"] == "fourfold" else Match).from_state(state)

    def _seat(self, room_id: str, token: str) -> str:
        row = self._row("SELECT player_id,expires FROM seats WHERE room_id=? AND token_hash=?",
                        (room_id, digest(token)))
        if not row or row["expires"] <= time.time():
            raise RoomError("Missing, revoked or expired seat token", 401)
        return row["player_id"]

    def create(self, game: str, participants: list[dict[str, str]]) -> dict[str, Any]:
        if game not in ("four-color", "fourfold"):
            raise RoomError("Unsupported online game")
        if not isinstance(participants, list) or any(not isinstance(p, dict) or p.get("kind", "human") != "human" for p in participants):
            raise RoomError("Online rooms currently require human players")
        match = (FourfoldMatch if game == "fourfold" else Match).new(participants)
        room_id = uuid4().hex
        token = secrets.token_urlsafe(36)
        with self._write():
            self.db.execute("INSERT INTO rooms(id,host_hash,state) VALUES(?,?,?)",
                            (room_id, digest(token), json.dumps(match.state)))
            self.db.execute("INSERT INTO seats(token_hash,room_id,player_id,expires) VALUES(?,?,?,?)",
                            (digest(token), room_id, participants[0]["id"], time.time() + 7 * 86400))
        return {"room": room_id, "token": token, "seat": participants[0]["id"], "state": match.view(participants[0]["id"])}

    def invite(self, room_id: str, host_token: str, player_id: str) -> dict[str, Any]:
        with self._write():
            row, match = self._room(room_id)
            if digest(host_token) != row["host_hash"] or self._seat(room_id, host_token) != match.state["players"][0]["id"]:
                raise RoomError("Only the active room host can invite players", 403)
            if player_id == match.state["players"][0]["id"] or player_id not in [p["id"] for p in match.state["players"]]:
                raise RoomError("Unknown guest seat")
            if self._row("SELECT 1 FROM seats WHERE room_id=? AND player_id=?", (room_id, player_id)):
                raise RoomError("Seat already occupied")
            invite = secrets.token_urlsafe(36)
            self.db.execute("INSERT INTO invites(invite_hash,room_id,player_id,expires) VALUES(?,?,?,?)",
                            (digest(invite), room_id, player_id, time.time() + 86400))
        return {"room": room_id, "invite": invite, "seat": player_id, "expires_in_seconds": 86400}

    def join(self, room_id: str, invite: str) -> dict[str, Any]:
        with self._write():
            row = self._row("SELECT * FROM invites WHERE invite_hash=? AND room_id=?", (digest(invite), room_id))
            if not row or row["used"] or row["expires"] <= time.time():
                raise RoomError("Invalid, consumed or expired invitation", 403)
            seat = row["player_id"]
            if self._row("SELECT 1 FROM seats WHERE room_id=? AND player_id=?", (room_id, seat)):
                raise RoomError("Seat already occupied")
            token = secrets.token_urlsafe(36)
            self.db.execute("UPDATE invites SET used=1 WHERE invite_hash=?", (digest(invite),))
            self.db.execute("INSERT INTO seats(token_hash,room_id,player_id,expires) VALUES(?,?,?,?)",
                            (digest(token), room_id, seat, time.time() + 7 * 86400))
            _, match = self._room(room_id)
        return {"room": room_id, "token": token, "seat": seat, "state": match.view(seat)}

    def view(self, room_id: str, token: str) -> dict[str, Any]:
        with self._lock:
            seat = self._seat(room_id, token)
            _, match = self._room(room_id)
            return match.view(seat)

    def act(self, room_id: str, token: str, revision: int, action_id: str, command: str,
            args: dict[str, Any]) -> dict[str, Any]:
        if type(revision) is not int or not isinstance(args, dict) or not isinstance(command, str):
            raise RoomError("Invalid action payload")
        if not isinstance(action_id, str) or not 1 <= len(action_id) <= 100 or any(ord(c) < 33 for c in action_id):
            raise RoomError("Each action needs a stable action_id")
        with self._write():
            seat = self._seat(room_id, token)
            _, match = self._room(room_id)
            if self._row("SELECT 1 FROM actions WHERE room_id=? AND player_id=? AND action_id=?",
                         (room_id, seat, action_id)):
                return {"replayed": True, "state": match.view(seat)}
            if match.state["revision"] != revision:
                raise RoomError("Revision changed; refresh room state", 409)
            match.act(seat, command, **args)
            self.db.execute("UPDATE rooms SET state=? WHERE id=?", (json.dumps(match.state), room_id))
            self.db.execute("INSERT INTO actions(room_id,player_id,action_id) VALUES(?,?,?)",
                            (room_id, seat, action_id))
            return {"replayed": False, "state": match.view(seat)}

    def revoke(self, room_id: str, host_token: str, player_id: str) -> dict[str, bool]:
        with self._write():
            row, match = self._room(room_id)
            if digest(host_token) != row["host_hash"] or self._seat(room_id, host_token) != match.state["players"][0]["id"]:
                raise RoomError("Only the host may revoke a seat", 403)
            if player_id == match.state["players"][0]["id"]:
                raise RoomError("The host cannot revoke their own seat")
            self.db.execute("DELETE FROM seats WHERE room_id=? AND player_id=?", (room_id, player_id))
            self.db.execute("UPDATE invites SET used=1 WHERE room_id=? AND player_id=?", (room_id, player_id))
        return {"revoked": True}


def handler_factory(rooms: OnlineRooms, allowed_origin: str | None = None):
    rate_lock = threading.Lock()
    creation_times: dict[str, list[float]] = {}

    class Handler(BaseHTTPRequestHandler):
        server_version = "CardGamesRooms/0.1"

        def _send(self, code, body):
            encoded = json.dumps(body, separators=(",", ":")).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if allowed_origin and self.headers.get("Origin") == allowed_origin:
                self.send_header("Access-Control-Allow-Origin", allowed_origin)
                self.send_header("Access-Control-Allow-Headers", "Authorization,Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(encoded)

        def _read(self):
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise RoomError("JSON content type required", 415)
            try:
                length = int(self.headers.get("Content-Length", "-1"))
                if not 0 <= length <= 32768:
                    raise RoomError("Request body exceeds 32 KiB", 413)
                data = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError) as exc:
                raise RoomError("Invalid JSON body") from exc
            if not isinstance(data, dict):
                raise RoomError("JSON object required")
            return data

        def _token(self):
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or len(auth) > 200:
                raise RoomError("Bearer seat token required", 401)
            return auth[7:]

        def _handle(self, method):
            origin = self.headers.get("Origin")
            if origin and origin != allowed_origin:
                raise RoomError("Origin not allowed", 403)
            parts = [p for p in urlsplit(self.path).path.split("/") if p]
            data = self._read() if method == "POST" else {}
            if parts == ["health"] and method == "GET":
                return {"status": "ready", "service": "online-rooms"}
            if parts == ["rooms"] and method == "POST":
                ip = self.client_address[0]
                with rate_lock:
                    now = time.monotonic()
                    recent = [t for t in creation_times.get(ip, []) if now - t < 60]
                    if len(recent) >= 6:
                        raise RoomError("Room creation rate limit exceeded", 429)
                    creation_times[ip] = [*recent, now]
                return rooms.create(data.get("game"), data.get("participants"))
            if len(parts) < 2 or parts[0] != "rooms":
                raise RoomError("Unknown endpoint", 404)
            room = parts[1]
            if len(parts) == 2 and method == "GET":
                return rooms.view(room, self._token())
            if parts[2:] == ["invites"] and method == "POST":
                return rooms.invite(room, self._token(), data.get("seat"))
            if parts[2:] == ["join"] and method == "POST":
                return rooms.join(room, data.get("invite", ""))
            if parts[2:] == ["actions"] and method == "POST":
                return rooms.act(room, self._token(), data.get("revision"), data.get("action_id"),
                                 data.get("command"), data.get("args", {}))
            if len(parts) == 4 and parts[2] == "seats" and method == "DELETE":
                return rooms.revoke(room, self._token(), parts[3])
            raise RoomError("Unknown endpoint", 404)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def do_OPTIONS(self):
            if allowed_origin and self.headers.get("Origin") == allowed_origin:
                self._send(200, {"ok": True})
            else:
                self._send(403, {"error": "Origin not allowed"})

        def _dispatch(self, method):
            try:
                self._send(200, {"ok": True, "data": self._handle(method)})
            except RoomError as exc:
                self._send(exc.status, {"ok": False, "error": str(exc)})
            except GameError as exc:
                self._send(400, {"ok": False, "error": str(exc)})

        def log_message(self, fmt, *args):
            # Default HTTP logger can leak invite tokens if URLs are used incorrectly.
            pass

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description="Card Games remote room service (not SLAI LocalServer)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8775)
    parser.add_argument("--data", required=True, help="Server-owned SQLite path")
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    parser.add_argument("--allowed-origin", help="Exact trusted browser origin, including scheme and port")
    args = parser.parse_args(argv)
    if args.host not in ("127.0.0.1", "::1", "localhost") and (not args.tls_cert or not args.tls_key):
        parser.error("Non-loopback rooms require both TLS certificate and private key")
    rooms = OnlineRooms(Path(args.data))
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(rooms, args.allowed_origin))
    if args.tls_cert and args.tls_key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.tls_cert, args.tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        rooms.close()


if __name__ == "__main__":
    main()
