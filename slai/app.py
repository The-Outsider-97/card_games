"""SLAI shared-toolkit HTTP host for the Card Games desktop application."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _bootstrap_slai(explicit: str | None) -> Path:
    candidates = [Path(explicit)] if explicit else []
    if os.getenv("SLAI_ROOT"):
        candidates.append(Path(os.environ["SLAI_ROOT"]))
    candidates.extend((ROOT.parent, ROOT.parent.parent, Path.cwd(), Path.cwd().parent))
    for candidate in candidates:
        if (candidate / "applications" / "tools" / "server").is_dir():
            location = str(candidate.resolve())
            if location not in sys.path:
                sys.path.insert(0, location)
            return candidate.resolve()
    raise RuntimeError("SLAI v2.4 shared tools not found. Supply --slai-root G:\\GAIA\\AI\\SLAI or set SLAI_ROOT.")


def build_router():
    from applications.tools.errors import BadRequest, NotFound
    from applications.tools.server import Router, Response, ok
    from app.game import CARDS, GameError
    from http.cookies import SimpleCookie

    router = Router()

    def cookie_token(req, name="cg_account"):
        jar = SimpleCookie()
        try:
            jar.load(req.headers.get("cookie", ""))
        except Exception:
            return None
        token = jar.get(name)
        return token.value if token else None

    def session_cookies(access, refresh):
        # Strict same-site cookies + the toolkit's mutation header mitigate CSRF.
        return [f"cg_account={access}; Path=/; HttpOnly; SameSite=Strict; Max-Age=3600",
                f"cg_refresh={refresh}; Path=/api/account; HttpOnly; SameSite=Strict; Max-Age=1209600"]

    def owner(app, req):
        return app.service.account(cookie_token(req))["owner"]

    def handle(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except GameError as exc:
            if str(exc) == "Match not found":
                raise NotFound(str(exc)) from exc
            raise BadRequest(str(exc)) from exc

    @router.route("GET", "/api/catalog")
    def catalog(app, req):
        return app.service.catalog()

    @router.route("GET", "/api/assets")
    def assets(app, req):
        return app.service.assets.report()

    @router.route("GET", "/api/card-art/{id}")
    def card_art(app, req):
        # The shared SLAI static path allowlist intentionally excludes '+'.
        # Resolve just those existing, whitelisted card faces here instead of
        # renaming or copying any original artwork or weakening shared routing.
        alias = req.params["id"]
        card = "+" + alias[4:] if alias.startswith("plus") else ""
        if card not in CARDS or not card.startswith("+"):
            raise NotFound("Card artwork not found")
        path = ROOT / "cards" / "colors" / f"{card}.jpg"
        if not path.is_file():
            raise NotFound("Card artwork not found")
        return Response(200, path.read_bytes(), "image/jpeg", {"Cache-Control": "private, max-age=3600"})

    @router.route("GET", "/api/health")
    def health(app, req):
        return {"status": "ready", "ai": app.service.agent.status,
                "ai_diagnostic": app.service.agent.last_diagnostic,
                "auth": app.service.auth_status, "persistence": "sqlite"}

    @router.route("GET", "/api/account")
    def account(app, req):
        return app.service.account(cookie_token(req))

    @router.route("POST", "/api/account/signup")
    def signup(app, req):
        payload = req.json()
        return handle(app.service.signup, payload.get("username"), payload.get("password"))

    @router.route("POST", "/api/account/login")
    def login(app, req):
        payload = req.json()
        token, refresh_token, profile = handle(app.service.login, payload.get("username"), payload.get("password"))
        response = ok(profile)
        response.cookies.extend(session_cookies(token, refresh_token))
        return response

    @router.route("POST", "/api/account/refresh")
    def refresh(app, req):
        access, refresh_token, profile = handle(app.service.refresh, cookie_token(req, "cg_refresh"))
        response = ok(profile)
        response.cookies.extend(session_cookies(access, refresh_token))
        return response

    @router.route("POST", "/api/account/logout")
    def logout(app, req):
        handle(app.service.logout, cookie_token(req), cookie_token(req, "cg_refresh"))
        response = ok({"status": "guest"})
        response.cookies.append("cg_account=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
        response.cookies.append("cg_refresh=; Path=/api/account; HttpOnly; SameSite=Strict; Max-Age=0")
        return response

    @router.route("GET", "/api/profile")
    def profile(app, req):
        return app.service.profile(owner(app, req))

    @router.route("PUT", "/api/profile")
    def update_profile(app, req):
        who = owner(app, req)
        if who == "guest":
            raise BadRequest("Sign in to edit your profile")
        return handle(app.service.profile, who, req.json())

    @router.route("GET", "/api/matches")
    def matches(app, req):
        return app.service.list(owner(app, req))

    @router.route("GET", "/api/stats")
    def stats(app, req):
        return app.service.statistics(owner(app, req))

    @router.route("POST", "/api/matches")
    def new_match(app, req):
        payload = req.json()
        if payload.get("game", "four-color") not in ("four-color", "fourfold", "skip-bo", "21", "blackjack", "knuckles"):
            raise BadRequest("Game rules are not yet available")
        participants = payload.get("participants")
        if not isinstance(participants, list) or any(not isinstance(p, dict) for p in participants):
            raise BadRequest("Participants must be a list of player definitions")
        return handle(app.service.create, owner(app, req), participants,
                      difficulty=payload.get("difficulty"), game=payload.get("game", "four-color"),
                      options=payload.get("options"))

    @router.route("POST", "/api/matches/{id}/rematch")
    def rematch(app, req):
        return handle(app.service.rematch, owner(app, req), req.params["id"])

    @router.route("GET", "/api/matches/{id}")
    def get_match(app, req):
        return handle(app.service.get, owner(app, req), req.params["id"], req.str_query("viewer", ""))

    @router.route("DELETE", "/api/matches/{id}")
    def delete_match(app, req):
        handle(app.service.delete, owner(app, req), req.params["id"])
        return {"deleted": True}

    @router.route("POST", "/api/matches/{id}/actions")
    def action(app, req):
        payload = req.json()
        name = payload.get("command")
        actor = payload.get("actor")
        revision = payload.get("revision")
        args = payload.get("args", {})
        if not isinstance(name, str) or not isinstance(actor, str) or type(revision) is not int or not isinstance(args, dict):
            raise BadRequest("Invalid action parameters")
        return handle(app.service.command, owner(app, req), req.params["id"], actor, name, args, revision)

    @router.route("GET", "/api/settings")
    def settings(app, req):
        return app.service.preferences(owner(app, req))

    @router.route("PUT", "/api/settings")
    def update_settings(app, req):
        return handle(app.service.preferences, owner(app, req), req.json())

    return router


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Card Games — SLAI-integrated tabletop launcher")
    parser.add_argument("--slai-root", help="SLAI v2.4 checkout")
    parser.add_argument("--port", type=int, default=8774)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--data-dir")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--token", help="Fixed loopback token for testing only")
    args = parser.parse_args(argv)
    slai_root = _bootstrap_slai(args.slai_root)
    from applications.tools.server import Identity, LocalServer, ServerOptions, refuse_remote_host, serve
    from applications.tools.storage import default_data_dir
    from app.service import CardGamesService

    if refuse_remote_host(args.host, "Card Games", "cards, game sessions and profiles"):
        return 2
    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir("card_games", "Card Games")
    service = CardGamesService(data_dir)
    app = type("CardGamesApp", (), {"service": service})()
    token = args.token or secrets.token_urlsafe(36)
    server = LocalServer(app, Identity("card_games", "Card Games"), build_router(), ServerOptions(
        token=token, client_dir=ROOT / "src" / "client", host=args.host, port=args.port,
        tools_web_dir=slai_root / "applications" / "tools" / "web",
        asset_dirs=(ROOT / "cards", slai_root / "applications" / "assets"),
    ))
    url = f"{server.base_url}/?token={token}"
    return serve(server, title="Card Games", version="0.2.0-dev", url=url,
                 details=[("Data", str(data_dir)), ("SLAI", str(slai_root)), ("AI", service.agent.status)],
                 open_browser=not args.no_browser, on_close=service.close)
