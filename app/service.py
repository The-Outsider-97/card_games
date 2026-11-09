"""Persistent session/application service backed by SLAI's shared Database."""

from __future__ import annotations

import json
import hashlib
import re
import threading
from pathlib import Path
from typing import Any

from .game import GameError, Match
from .fourfold import FourfoldMatch
from .variants import ENGINES, VariantMatch, new_variant
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
            Migration(3, "profiles and refresh session pairs", (
                "CREATE TABLE profiles (owner TEXT PRIMARY KEY, display_name TEXT NOT NULL, avatar TEXT NOT NULL DEFAULT 'initials')",
                "CREATE TABLE refresh_sessions (refresh_hash TEXT PRIMARY KEY, access_hash TEXT NOT NULL, owner TEXT NOT NULL, username TEXT NOT NULL)",
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

    def login(self, username: str, password: str) -> tuple[str, str, dict[str, str]]:
        if self.auth is None:
            raise GameError("SLAI authentication is not available")
        if not isinstance(username, str) or not isinstance(password, str):
            raise GameError("Invalid credentials")
        try:
            session = self.auth.log_in_with_refresh(username, password)
        except Exception as exc:
            raise GameError("Invalid credentials or temporarily locked account") from exc
        with self._lock, self.db.transaction():
            self.db.execute("INSERT OR REPLACE INTO account_sessions(token_hash,owner,username) VALUES(?,?,?)",
                            (self._hash_token(session.access.token), session.access.user_id, username))
            self.db.execute("INSERT INTO refresh_sessions(refresh_hash,access_hash,owner,username) VALUES(?,?,?,?)",
                            (self._hash_token(session.refresh.token), self._hash_token(session.access.token),
                             session.access.user_id, username))
        return session.access.token, session.refresh.token, {"username": username, "status": "signed-in"}

    def refresh(self, refresh_token: str | None) -> tuple[str, str, dict[str, str]]:
        if self.auth is None or not refresh_token:
            raise GameError("Invalid or expired account session")
        hashed = self._hash_token(refresh_token)
        with self._lock:
            row = self.db.row("SELECT * FROM refresh_sessions WHERE refresh_hash=?", (hashed,))
            if row is None:
                raise GameError("Invalid or expired account session")
            try:
                session = self.auth.rotate_refresh_token(refresh_token)
            except Exception as exc:
                raise GameError("Invalid or expired account session") from exc
            if session.access.user_id != row["owner"]:
                raise GameError("Account session owner mismatch")
            with self.db.transaction():
                self.db.execute("DELETE FROM account_sessions WHERE token_hash=?", (row["access_hash"],))
                self.db.execute("DELETE FROM refresh_sessions WHERE refresh_hash=?", (hashed,))
                self.db.execute("INSERT INTO account_sessions(token_hash,owner,username) VALUES(?,?,?)",
                                (self._hash_token(session.access.token), row["owner"], row["username"]))
                self.db.execute("INSERT INTO refresh_sessions(refresh_hash,access_hash,owner,username) VALUES(?,?,?,?)",
                                (self._hash_token(session.refresh.token), self._hash_token(session.access.token),
                                 row["owner"], row["username"]))
        return session.access.token, session.refresh.token, {"username": row["username"], "status": "signed-in"}

    def account(self, token: str | None) -> dict[str, str]:
        if self.auth is None or not token:
            return {"owner": "guest", "username": "Guest", "status": "guest", "available": str(self.auth is not None).lower()}
        with self._lock:
            row = self.db.row("SELECT owner,username FROM account_sessions WHERE token_hash=?", (self._hash_token(token),))
        if row is None or not self.auth.is_token_valid(token):
            return {"owner": "guest", "username": "Guest", "status": "guest", "available": "true"}
        return {**row, "status": "signed-in", "available": "true"}

    def logout(self, token: str | None, refresh_token: str | None = None) -> None:
        if not token and not refresh_token:
            return
        with self._lock, self.db.transaction():
            if token:
                hashed = self._hash_token(token)
                self.db.execute("DELETE FROM refresh_sessions WHERE access_hash=?", (hashed,))
                self.db.execute("DELETE FROM account_sessions WHERE token_hash=?", (hashed,))
            if refresh_token:
                hashed_refresh = self._hash_token(refresh_token)
                row = self.db.row("SELECT access_hash FROM refresh_sessions WHERE refresh_hash=?", (hashed_refresh,))
                if row:
                    self.db.execute("DELETE FROM account_sessions WHERE token_hash=?", (row["access_hash"],))
                self.db.execute("DELETE FROM refresh_sessions WHERE refresh_hash=?", (hashed_refresh,))
        if self.auth is not None:
            if token:
                self.auth.log_out(token)
            if refresh_token:
                self.auth.revoke_token(refresh_token)

    def profile(self, owner: str, update: dict[str, Any] | None = None) -> dict[str, str]:
        if owner == "guest":
            return {"display_name": "Guest", "avatar": "initials"}
        with self._lock:
            row = self.db.row("SELECT display_name,avatar FROM profiles WHERE owner=?", (owner,))
            value = {"display_name": row["display_name"] if row else "Player",
                     "avatar": row["avatar"] if row else "initials"}
            if update is None:
                return value
            if not isinstance(update, dict) or not set(update) <= {"display_name", "avatar"}:
                raise GameError("Invalid profile changes")
            if "display_name" in update:
                name = update["display_name"]
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40 or any(ord(ch) < 32 for ch in name):
                    raise GameError("Display name must have 1–40 visible characters")
                value["display_name"] = name.strip()
            if "avatar" in update:
                if update["avatar"] not in ("initials", "circle", "suit"):
                    raise GameError("Invalid avatar style")
                value["avatar"] = update["avatar"]
            with self.db.transaction():
                self.db.execute("INSERT INTO profiles(owner,display_name,avatar) VALUES(?,?,?) ON CONFLICT(owner) "
                                "DO UPDATE SET display_name=excluded.display_name,avatar=excluded.avatar",
                                (owner, value["display_name"], value["avatar"]))
            return value

    def catalog(self) -> list[dict[str, Any]]:
        color_ready = self.assets.inspect("colors")["status"] == "complete"
        skip_ready = self.assets.inspect("colors")["game_subsets"]["skip-bo"]["ready"]
        standard_ready = self.assets.inspect("symbols")["game_subsets"]["blackjack"]["ready"]
        return [
            {"id": "four-color", "title": "Four-Color", "description": "Match colors, ranks and actions in a tactical 2–8 player card game.",
             "image": "/assets/colors/cover.jpg", "players": "2–8", "status": "playable" if color_ready else "assets-missing", "asset_set": "colors"},
            {"id": "fourfold", "title": "Fourfold Mandate", "description": "12 rounds of secret orders, estate contests and deterministic scoring.",
             "image": "/assets/fourfold/cover.jpg", "players": "2–6", "status": "playable", "asset_set": "fourfold",
             "asset_warning": self.assets.inspect("fourfold")["missing"]},
            {"id": "skip-bo", "title": "Skip-Bo", "description": "Build shared sequences from 1 to 12; clear your stockpile using number and Wild cards.",
             "image": "/assets/colors/cover.jpg", "players": "2–6", "status": "playable" if skip_ready else "assets-missing", "asset_set": "colors"},
            {"id": "21", "title": "21 · Competitive", "description": "A no-dealer, no-wager closest-to-21 variant; draw or stand and compare totals.",
             "image": "/assets/symbols/cover.jpg", "players": "2–6", "status": "playable" if standard_ready else "assets-missing", "asset_set": "symbols"},
            {"id": "blackjack", "title": "Blackjack", "description": "Beat a fixed dealer without busting; dealer stands on all 17s. No wagers.",
             "image": "/assets/symbols/cover.jpg", "players": "2–6", "status": "playable" if standard_ready else "assets-missing", "asset_set": "symbols"},
            {"id": "knuckles", "title": "Knuckles · Five-card", "description": "Keep the lowest total; draw, discard and knock to end the round.",
             "image": "/assets/symbols/cover.jpg", "players": "2–6", "status": "playable" if standard_ready else "assets-missing", "asset_set": "symbols"},
        ]

    def create(self, owner: str, participants: list[dict[str, str]], seed: int | None = None,
               difficulty: str | None = None, game: str = "four-color",
               options: dict[str, Any] | None = None) -> dict[str, Any]:
        if not owner or len(owner) > 80:
            raise GameError("Invalid owner")
        difficulty = difficulty or self.preferences(owner)["difficulty"]
        if difficulty not in ("easy", "medium", "hard", "expert"):
            raise GameError("Invalid AI difficulty")
        if game not in ("four-color", "fourfold", *ENGINES):
            raise GameError("Game rules are not available")
        if options is not None and not isinstance(options, dict):
            raise GameError("Game options must be an object")
        if options and game not in ENGINES:
            raise GameError("This game does not support rule options")
        match = (Match.new(participants, seed=seed) if game == "four-color" else
                 FourfoldMatch.new(participants, seed=seed) if game == "fourfold" else
                 new_variant(game, participants, seed=seed, options=options))
        match.state["ai_difficulty"] = difficulty
        with self._lock, self.db.transaction():
            self._run_ai(match)
            self._save(owner, match)
        viewer = next((p["id"] for p in participants if p.get("kind", "human") == "human"), None)
        return match.view(viewer)

    def rematch(self, owner: str, match_id: str) -> dict[str, Any]:
        """Idempotently restart a completed local match with the same seats.

        Skip-Bo advances the dealer and preserves official optional series
        scores without trusting client-supplied scores or dealer position.
        """
        with self._lock, self.db.transaction():
            old = self._load(owner, match_id)
            if not self._complete(old):
                raise GameError("Finish the current match before playing again")
            if old.state.get("rematch_id"):
                match = self._load(owner, old.state["rematch_id"])
            else:
                participants = [{key: p[key] for key in ("id", "name", "kind")}
                                for p in old.state["players"]]
                game = old.state["game"]
                if game == "four-color":
                    match = Match.new(participants)
                elif game == "fourfold":
                    match = FourfoldMatch.new(participants)
                elif game == "skip-bo":
                    scores = None if old.state.get("series_complete") else old.state.get("series_scores")
                    match = ENGINES[game].new(participants, short_game=old.state.get("short_game", False),
                                              partnership=old.state.get("partnership", False),
                                              dealer=(old.state.get("dealer", 0) + 1) % len(participants),
                                              series_scores=scores)
                else:
                    match = new_variant(game, participants)
                match.state["ai_difficulty"] = old.state.get("ai_difficulty", "medium")
                match.state["rematch_of"] = match_id
                old.state["rematch_id"] = match.state["id"]
                self._save(owner, old)
                self._run_ai(match)
                self._save(owner, match)
            viewer = next((p["id"] for p in match.state["players"] if p["kind"] == "human"), None)
            return match.view(viewer)

    def _save(self, owner: str, match: Match | FourfoldMatch | VariantMatch) -> None:
        self.db.execute("INSERT INTO matches(id,owner,data,revision,completed) VALUES(?,?,?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET data=excluded.data,revision=excluded.revision,completed=excluded.completed",
                        (match.state["id"], owner, json.dumps(match.state, separators=(",", ":")),
                         match.state["revision"], int(self._complete(match))))

    def _load(self, owner: str, match_id: str) -> Match | FourfoldMatch | VariantMatch:
        row = self.db.row("SELECT data FROM matches WHERE owner=? AND id=?", (owner, match_id))
        if row is None:
            raise GameError("Match not found")
        state = json.loads(row["data"])
        klass = ({"four-color": Match, "fourfold": FourfoldMatch, **ENGINES}).get(state.get("game"))
        if klass is None:
            raise GameError("Unsupported saved game")
        return klass.from_state(state)

    @staticmethod
    def _complete(match: Match | FourfoldMatch | VariantMatch) -> bool:
        return match.state["phase"] == "complete" if match.state["game"] != "four-color" else match.state["winner"] is not None

    def get(self, owner: str, match_id: str, viewer: str | None) -> dict[str, Any]:
        with self._lock:
            match = self._load(owner, match_id)
            participant = next((p for p in match.state["players"] if p["id"] == viewer), None)
            # Hot-seat can reveal other local humans, but never AI private state.
            if participant is None or participant["kind"] != "human":
                viewer = None
            return match.view(viewer)

    def list(self, owner: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.rows("SELECT id,revision,completed,data FROM matches WHERE owner=? ORDER BY rowid DESC LIMIT 40", (owner,))
        result = []
        for row in rows:
            match = json.loads(row["data"])
            result.append({"id": row["id"], "game": match["game"], "revision": row["revision"],
                           "completed": bool(row["completed"]), "winner": match["winner"],
                           "winners": match.get("winners", []), "players": [p["name"] for p in match["players"]]})
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
            winners = match.get("winners", []) if match["game"] != "four-color" else [match.get("winner")]
            if not (match["phase"] == "complete" if match["game"] != "four-color" else any(winners)):
                continue
            complete += 1
            for winner in winners:
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

    def _run_ai(self, match: Match | FourfoldMatch | VariantMatch, max_steps: int = 200) -> None:
        if match.state["game"] == "fourfold":
            for p in match.state["players"]:
                if p["kind"] == "ai" and p["orders"] is None and match.state["phase"] == "plan":
                    self.agent.difficulty = match.state.get("ai_difficulty", "medium")
                    match.act(p["id"], "submit", orders=self.agent.fourfold_orders(match, p["id"]))
            return
        if isinstance(match, VariantMatch):
            for _ in range(max_steps):
                if match.state["phase"] == "complete":
                    return
                player = match.state["players"][match.state["current"]]
                if player["kind"] != "ai":
                    return
                self.agent.difficulty = match.state.get("ai_difficulty", "medium")
                action = self.agent.variant_action(match, player["id"])
                match.act(player["id"], action["command"], **action["args"])
            return
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
