"""Persistent session/application service backed by SLAI's shared Database."""

from __future__ import annotations

import json
import hashlib
import re
import threading
from pathlib import Path
from typing import Any

from .game import GameError, Match
from .assets import AssetRegistry
from slai.bridge.agents import CardAgentBridge


class CardGamesService:
    def __init__(self, data_dir: Path):
        from applications.tools.database import Database, Migration

        self._lock = threading.RLock()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.assets = AssetRegistry(Path(__file__).resolve().parents[1] / "cards")
        self.db = Database(self.data_dir / "card_games.sqlite3", [
            Migration(1, "matches and preferences", (
                "CREATE TABLE matches (id TEXT PRIMARY KEY, owner TEXT NOT NULL, data TEXT NOT NULL, revision INTEGER NOT NULL, completed INTEGER NOT NULL DEFAULT 0)",
                "CREATE TABLE preferences (owner TEXT PRIMARY KEY, data TEXT NOT NULL)",
            )),
            Migration(2, "account sessions", (
                "CREATE TABLE account_sessions (token_hash TEXT PRIMARY KEY, owner TEXT NOT NULL, username TEXT NOT NULL)",
            )),
        ], backups_dir=self.data_dir / "backups")
        self.agent = CardAgentBridge()
        self.auth = None
        self.auth_status = "unavailable"
        try:
            from src.functions.auth import AuthService  # type: ignore[import-not-found]

            self.auth = AuthService(memory_path=str(self.data_dir / "accounts.json"),
                                    token_ttl_minutes=60, require_verified=False)
            self.auth_status = "ready"
        except Exception:  # An unavailable optional SLAI subsystem leaves guest play usable.
            self.auth = None

    def close(self) -> None:
        self.db.close()

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def signup(self, username: str, password: str) -> dict[str, str]:
        if self.auth is None:
            raise GameError("SLAI authentication is not available")
        if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
            raise GameError("Username must contain 3–32 letters, digits, underscore, dot or dash")
        if not isinstance(password, str) or len(password) > 200:
            raise GameError("Invalid password")
        try:
            self.auth.sign_up(username, password)
        except Exception as exc:
            raise GameError(f"Signup rejected: {type(exc).__name__}") from exc
        return {"username": username, "status": "registered"}

    def login(self, username: str, password: str) -> tuple[str, dict[str, str]]:
        if self.auth is None:
            raise GameError("SLAI authentication is not available")
        if not isinstance(username, str) or not isinstance(password, str):
            raise GameError("Invalid credentials")
        try:
            token = self.auth.log_in(username, password)
        except Exception as exc:
            raise GameError("Invalid credentials or temporarily locked account") from exc
        with self._lock, self.db.transaction():
            self.db.execute("INSERT OR REPLACE INTO account_sessions(token_hash,owner,username) VALUES(?,?,?)",
                            (self._hash_token(token.token), token.user_id, username))
        return token.token, {"username": username, "status": "signed-in"}

    def account(self, token: str | None) -> dict[str, str]:
        if self.auth is None or not token:
            return {"owner": "guest", "username": "Guest", "status": "guest", "available": str(self.auth is not None).lower()}
        with self._lock:
            row = self.db.row("SELECT owner,username FROM account_sessions WHERE token_hash=?", (self._hash_token(token),))
        if row is None or not self.auth.is_token_valid(token):
            return {"owner": "guest", "username": "Guest", "status": "guest", "available": "true"}
        return {**row, "status": "signed-in", "available": "true"}

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._lock, self.db.transaction():
            self.db.execute("DELETE FROM account_sessions WHERE token_hash=?", (self._hash_token(token),))
        if self.auth is not None:
            self.auth.log_out(token)

    def catalog(self) -> list[dict[str, Any]]:
        color_ready = self.assets.inspect("colors")["status"] == "complete"
        return [
            {"id": "four-color", "title": "Four-Color", "description": "Match colors, ranks and actions in a tactical 2–8 player card game.",
             "image": "/assets/colors/cover.jpg", "players": "2–8", "status": "playable" if color_ready else "assets-missing", "asset_set": "colors"},
            {"id": "fourfold", "title": "Fourfold Mandate", "description": "Strategic card game; authoritative rules are still required.",
             "image": "/assets/fourfold/cover.jpg", "players": "Rules pending", "status": "rules-pending", "asset_set": "fourfold"},
            {"id": "symbols", "title": "Symbol-based games", "description": "Reusable suit card family; deck/rules mapping awaiting approval.",
             "image": "/assets/symbols/cover.jpg", "players": "Variant pending", "status": "rules-pending", "asset_set": "symbols"},
        ]

    def create(self, owner: str, participants: list[dict[str, str]], seed: int | None = None,
               difficulty: str | None = None) -> dict[str, Any]:
        if not owner or len(owner) > 80:
            raise GameError("Invalid owner")
        difficulty = difficulty or self.preferences(owner)["difficulty"]
        if difficulty not in ("easy", "medium", "hard", "expert"):
            raise GameError("Invalid AI difficulty")
        match = Match.new(participants, seed=seed)
        match.state["ai_difficulty"] = difficulty
        with self._lock, self.db.transaction():
            self._save(owner, match)
        return match.view(participants[0]["id"])

    def _save(self, owner: str, match: Match) -> None:
        self.db.execute("INSERT INTO matches(id,owner,data,revision,completed) VALUES(?,?,?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET data=excluded.data,revision=excluded.revision,completed=excluded.completed",
                        (match.state["id"], owner, json.dumps(match.state, separators=(",", ":")),
                         match.state["revision"], int(match.state["winner"] is not None)))

    def _load(self, owner: str, match_id: str) -> Match:
        row = self.db.row("SELECT data FROM matches WHERE owner=? AND id=?", (owner, match_id))
        if row is None:
            raise GameError("Match not found")
        return Match.from_state(json.loads(row["data"]))

    def get(self, owner: str, match_id: str, viewer: str | None) -> dict[str, Any]:
        with self._lock:
            return self._load(owner, match_id).view(viewer)

    def list(self, owner: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.rows("SELECT id,revision,completed,data FROM matches WHERE owner=? ORDER BY rowid DESC LIMIT 40", (owner,))
        result = []
        for row in rows:
            match = json.loads(row["data"])
            result.append({"id": row["id"], "revision": row["revision"], "completed": bool(row["completed"]),
                           "winner": match["winner"], "players": [p["name"] for p in match["players"]]})
        return result

    def statistics(self, owner: str) -> dict[str, Any]:
        with self._lock:
            rows = self.db.rows("SELECT data FROM matches WHERE owner=?", (owner,))
        total = len(rows)
        complete = 0
        human_wins = 0
        ai_wins = 0
        duration = []
        for row in rows:
            match = json.loads(row["data"])
            winner = match.get("winner")
            if winner is None:
                continue
            complete += 1
            participant = next((p for p in match["players"] if p["id"] == winner), None)
            if participant is not None:
                if participant["kind"] == "human":
                    human_wins += 1
                elif participant["kind"] == "ai":
                    ai_wins += 1
            if match.get("completed_at") is not None and match.get("created_at") is not None:
                duration.append(max(0, match["completed_at"] - match["created_at"]))
        return {"total": total, "completed": complete, "in_progress": total - complete,
                "human_wins": human_wins, "ai_wins": ai_wins,
                "avg_duration_seconds": round(sum(duration) / len(duration)) if duration else None}

    def delete(self, owner: str, match_id: str) -> None:
        with self._lock, self.db.transaction():
            if self.db.execute("DELETE FROM matches WHERE owner=? AND id=?", (owner, match_id)).rowcount == 0:
                raise GameError("Match not found")

    def command(self, owner: str, match_id: str, actor: str, command: str, args: dict[str, Any],
                expected_revision: int) -> dict[str, Any]:
        with self._lock, self.db.transaction():
            match = self._load(owner, match_id)
            if match.state["revision"] != expected_revision:
                raise GameError("Match changed; refresh before trying again")
            participant = next((p for p in match.state["players"] if p["id"] == actor), None)
            if participant is None or participant["kind"] != "human":
                raise GameError("Human player identity is required")
            match.act(actor, command, **args)
            self._run_ai(match)
            self._save(owner, match)
            return match.view(actor)

    def _run_ai(self, match: Match, max_steps: int = 200) -> None:
        for _ in range(max_steps):
            if match.state["winner"] is not None:
                return
            choices = match.outstanding_choices()
            ai_choice = next((c for c in choices if self._kind(match, c["player"]) == "ai"), None)
            if ai_choice is not None:
                match.act(ai_choice["player"], "select", cards=self.agent.selection(match, ai_choice["player"], ai_choice["count"]))
                continue
            if choices:
                return
            current = match.state["players"][match.state["current"]]
            if current["kind"] != "ai":
                return
            self.agent.difficulty = match.state.get("ai_difficulty", "medium")
            action, kwargs = self.agent.move(match, current["id"])
            match.act(current["id"], action, **kwargs)
        # A bounded decision loop prevents long AI-only games from monopolizing an HTTP request.

    @staticmethod
    def _kind(match: Match, player_id: str) -> str:
        return next(p["kind"] for p in match.state["players"] if p["id"] == player_id)

    def preferences(self, owner: str, update: dict[str, Any] | None = None) -> dict[str, Any]:
        defaults = {"theme": "dark", "motion": True, "difficulty": "medium", "sound": False}
        with self._lock:
            row = self.db.row("SELECT data FROM preferences WHERE owner=?", (owner,))
            values = {**defaults, **(json.loads(row["data"]) if row else {})}
            if update is None:
                return values
            allowed = {"theme": ("dark", "light", "contrast"), "difficulty": ("easy", "medium", "hard", "expert")}
            for key, value in update.items():
                if key in allowed and value in allowed[key]:
                    values[key] = value
                elif key in ("motion", "sound") and type(value) is bool:
                    values[key] = value
                else:
                    raise GameError(f"Invalid preference: {key}")
            with self.db.transaction():
                self.db.execute("INSERT INTO preferences(owner,data) VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET data=excluded.data",
                                (owner, json.dumps(values)))
            self.agent.difficulty = values["difficulty"]
            return values
