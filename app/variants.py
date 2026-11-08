"""Additional, independently validated card games using existing artwork.

Art is presentation only: Skip-Bo reuses 52 color faces for 162 distinct
virtual cards; the other variants use only the conventional 52 suit faces.
The competitive 21 and five-card Knuckles profiles are documented local
rulesets, distinct from standard dealer Blackjack.
"""

from __future__ import annotations

from copy import deepcopy
from random import Random, SystemRandom
import time
from typing import Any
from uuid import uuid4

from .game import GameError

SUITS = ("clubs", "diamonds", "hearts", "spades")
COLORS = ("blue", "green", "red", "yellow")
RANKS = ("A", *(f"{i:02d}" for i in range(2, 11)), "J", "Q", "K")
STANDARD_DECK = tuple(f"{rank}-{suit}" for suit in SUITS for rank in RANKS)
SKIP_DECK = tuple(
    f"{rank:02d}-{color}~{copy}"
    for rank in range(1, 13) for color in COLORS for copy in range(3)
) + tuple(f"Wild-{color}~{copy}" for color, count in zip(COLORS, (5, 5, 4, 4)) for copy in range(count))
assert len(SKIP_DECK) == 162 and len(set(SKIP_DECK)) == 162


def face(card: str) -> str:
    return card.split("~", 1)[0]


def _participants(items: list[dict[str, str]], low: int, high: int) -> list[dict[str, Any]]:
    if not low <= len(items) <= high:
        raise GameError(f"This game requires {low}–{high} participants")
    ids = [p.get("id") for p in items]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise GameError("Participants must have distinct nonempty IDs")
    result = []
    for p in items:
        if p.get("kind", "human") not in ("human", "ai"):
            raise GameError("Invalid player kind")
        result.append({"id": p["id"], "name": str(p.get("name") or p["id"])[:40],
                       "kind": p.get("kind", "human")})
    return result


def _shuffle(cards: list[str], seed: int | None) -> list[str]:
    (Random(seed) if seed is not None else SystemRandom()).shuffle(cards)
    return cards


class VariantMatch:
    """Atomic actions and public events shared by three distinct engines."""

    def __init__(self, state: dict[str, Any]):
        self.state = state
        self.validate()

    @classmethod
    def from_state(cls, state: dict[str, Any]):
        return cls(deepcopy(state))

    def _index(self, actor: str) -> int:
        for i, player in enumerate(self.state["players"]):
            if player["id"] == actor:
                return i
        raise GameError("Unknown player")

    def _event(self, event: str, **fields: Any) -> None:
        self.state["events"].append({"type": event, **fields})
        self.state["events"] = self.state["events"][-300:]

    def _complete(self, winners: list[str]) -> None:
        self.state["phase"] = "complete"
        self.state["winners"] = winners
        self.state["winner"] = winners[0] if winners else None
        self.state["completed_at"] = time.time()
        self._event("complete", winners=winners)

    def act(self, actor: str, command: str, **args: Any) -> dict[str, Any]:
        snapshot = deepcopy(self.state)
        try:
            allowed = self.legal_actions(actor)
            if not any(x["command"] == command and x["args"] == args for x in allowed):
                raise GameError("Action is not legal in this game state")
            self._act(actor, command, args)
            self.validate()
            self.state["revision"] += 1
            return {"revision": self.state["revision"]}
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            self.state = snapshot
            if isinstance(exc, GameError):
                raise
            raise GameError("Invalid action or game state") from exc

    def validate(self) -> None:
        s = self.state
        ids = [p["id"] for p in s["players"]]
        if len(set(ids)) != len(ids) or not 0 <= s["current"] < len(ids):
            raise GameError("Invalid player state")
        located = list(self._located())
        if len(located) != len(self.DECK) or set(located) != set(self.DECK):
            raise GameError("Game cards have been lost, duplicated, or fabricated")


class SkipBoMatch(VariantMatch):
    """162-card Skip-Bo rules, reusing only numbers 1–12 and Wild color art."""

    DECK = SKIP_DECK

    @classmethod
    def new(cls, participants: list[dict[str, str]], seed: int | None = None):
        players = _participants(participants, 2, 6)
        draw = _shuffle(list(cls.DECK), seed)
        stock_size = 30 if len(players) <= 4 else 20
        for p in players:
            p.update(stock=[draw.pop() for _ in range(stock_size)], hand=[], discards=[[], [], [], []])
        state = {"id": uuid4().hex, "game": "skip-bo", "rules": "skip-bo-162-adapted-art-v1",
                 "revision": 0, "created_at": time.time(), "completed_at": None, "phase": "play",
                 "current": 0, "players": players, "draw": draw, "building": [[], [], [], []],
                 "completed": [], "recycles": 0, "seed": seed, "events": [], "winner": None, "winners": []}
        match = cls(state)
        match._refill()
        match.validate()
        return match

    def _located(self):
        s = self.state
        yield from s["draw"]
        yield from s["completed"]
        for pile in s["building"]:
            yield from (item["card"] for item in pile)
        for p in s["players"]:
            yield from p["stock"]
            yield from p["hand"]
            for pile in p["discards"]:
                yield from pile

    def _refill(self) -> None:
        s = self.state
        hand = s["players"][s["current"]]["hand"]
        while len(hand) < 5:
            if not s["draw"] and s["completed"]:
                s["recycles"] += 1
                seed = f"{s['seed']}:{s['recycles']}" if s["seed"] is not None else None
                s["draw"] = _shuffle(s["completed"], seed)
                s["completed"] = []
                self._event("recycle")
            if not s["draw"]:
                break
            hand.append(s["draw"].pop())

    @staticmethod
    def _fits(card: str, rank: int) -> bool:
        return face(card).startswith("Wild-") or int(face(card).split("-", 1)[0]) == rank

    def legal_actions(self, actor: str) -> list[dict[str, Any]]:
        s = self.state
        if s["phase"] != "play" or s["players"][s["current"]]["id"] != actor:
            return []
        player = s["players"][s["current"]]
        sources = ([] if not player["stock"] else [("stock", player["stock"][-1])])
        sources += [("hand", card) for card in player["hand"]]
        sources += [(f"discard:{i}", pile[-1]) for i, pile in enumerate(player["discards"]) if pile]
        actions = []
        for i, pile in enumerate(s["building"]):
            rank = len(pile) + 1
            actions.extend({"command": "build", "args": {"source": source, "card": card, "pile": i}}
                           for source, card in sources if self._fits(card, rank))
        actions.extend({"command": "discard", "args": {"card": card, "pile": i}}
                       for card in player["hand"] for i in range(4))
        if not actions:
            actions.append({"command": "pass", "args": {}})
        return actions

    def _act(self, actor: str, command: str, args: dict[str, Any]) -> None:
        s = self.state
        p = s["players"][s["current"]]
        if command == "build":
            source, card, index = args["source"], args["card"], args["pile"]
            pile = p["stock"] if source == "stock" else p["hand"] if source == "hand" else p["discards"][int(source.split(":")[1])]
            if source == "hand":
                pile.remove(card)
            else:
                pile.pop()
            rank = len(s["building"][index]) + 1
            s["building"][index].append({"card": card, "rank": rank})
            self._event("play", player=actor, card=face(card), pile=index, source=source)
            if rank == 12:
                s["completed"].extend(x["card"] for x in s["building"][index])
                s["building"][index] = []
                self._event("pile_complete", pile=index)
            if not p["stock"]:
                self._complete([actor])
            elif not p["hand"]:
                self._refill()
            return
        if command == "discard":
            p["hand"].remove(args["card"])
            p["discards"][args["pile"]].append(args["card"])
            self._event("discard", player=actor, card=face(args["card"]), pile=args["pile"])
        else:
            self._event("pass", player=actor)
        s["current"] = (s["current"] + 1) % len(s["players"])
        self._event("turn", player=s["players"][s["current"]]["id"])
        self._refill()
        # A depleted draw and inaccessible stock can otherwise deadlock forever.
        if not s["draw"] and not s["completed"] and all(not p["hand"] for p in s["players"]):
            self._complete([])

    def view(self, viewer: str | None = None) -> dict[str, Any]:
        s = self.state
        result = {k: deepcopy(s[k]) for k in ("id", "game", "rules", "revision", "phase", "current", "winner", "winners")}
        result.update(draw_count=len(s["draw"]), building=deepcopy(s["building"]), events=deepcopy(s["events"][-15:]))
        result["players"] = [{"id": p["id"], "name": p["name"], "kind": p["kind"],
                              "stock_top": p["stock"][-1] if p["stock"] else None,
                              "stock_count": len(p["stock"]), "hand_count": len(p["hand"]),
                              "hand": deepcopy(p["hand"]) if viewer == p["id"] else [],
                              "discards": [pile[-1] if pile else None for pile in p["discards"]]}
                             for p in s["players"]]
        result["legal_actions"] = self.legal_actions(viewer) if viewer else []
        return result


def hand_total(hand: list[str]) -> int:
    values = [face(card).split("-", 1)[0] for card in hand]
    total = sum(11 if c == "A" else 10 if c in ("J", "Q", "K") else int(c) for c in values)
    for _ in range(values.count("A")):
        if total <= 21:
            break
        total -= 10
    return total


class TwentyOneMatch(VariantMatch):
    """Two explicit profiles: competitive 21 and fixed-dealer Blackjack."""

    DECK = STANDARD_DECK

    @classmethod
    def new(cls, participants: list[dict[str, str]], seed: int | None = None, game: str = "blackjack"):
        if game not in ("21", "blackjack"):
            raise GameError("Invalid Twenty-One profile")
        players = _participants(participants, 2, 6)
        draw = _shuffle(list(cls.DECK), seed)
        for p in players:
            p.update(hand=[draw.pop(), draw.pop()], done=False)
        dealer = [draw.pop(), draw.pop()] if game == "blackjack" else []
        state = {"id": uuid4().hex, "game": game, "rules": f"{game}-no-wager-v1",
                 "revision": 0, "created_at": time.time(), "completed_at": None,
                 "phase": "play", "current": 0, "players": players, "draw": draw, "dealer": dealer,
                 "winner": None, "winners": [], "events": []}
        match = cls(state)
        for p in players:
            if hand_total(p["hand"]) == 21:
                p["done"] = True
        match._advance()
        match.validate()
        return match

    def _located(self):
        yield from self.state["draw"]
        yield from self.state["dealer"]
        for p in self.state["players"]:
            yield from p["hand"]

    def legal_actions(self, actor: str) -> list[dict[str, Any]]:
        s = self.state
        if s["phase"] != "play" or s["players"][s["current"]]["id"] != actor:
            return []
        hand = s["players"][s["current"]]["hand"]
        return ([{"command": "hit", "args": {}}] if s["draw"] and hand_total(hand) < 21 else []) + [
            {"command": "stand", "args": {}}]

    def _act(self, actor: str, command: str, args: dict[str, Any]) -> None:
        s = self.state
        player = s["players"][s["current"]]
        if command == "hit":
            player["hand"].append(s["draw"].pop())
            self._event("hit", player=actor)
            if hand_total(player["hand"]) >= 21:
                player["done"] = True
        else:
            player["done"] = True
            self._event("stand", player=actor)
        if player["done"]:
            self._advance()

    def _advance(self) -> None:
        s = self.state
        for offset in range(len(s["players"])):
            index = (s["current"] + offset) % len(s["players"])
            if not s["players"][index]["done"]:
                s["current"] = index
                self._event("turn", player=s["players"][index]["id"])
                return
        if s["game"] == "blackjack":
            while hand_total(s["dealer"]) < 17 and s["draw"]:
                s["dealer"].append(s["draw"].pop())
            self._event("dealer_stands", total=hand_total(s["dealer"]))
            dealer_total = hand_total(s["dealer"])
            dealer_natural = len(s["dealer"]) == 2 and dealer_total == 21
            winners = []
            for p in s["players"]:
                score = hand_total(p["hand"])
                natural = len(p["hand"]) == 2 and score == 21
                if score <= 21 and (dealer_total > 21 or (natural and not dealer_natural) or
                                    (score > dealer_total and not dealer_natural)):
                    winners.append(p["id"])
        else:
            scores = {p["id"]: hand_total(p["hand"]) for p in s["players"]}
            best = max((v for v in scores.values() if v <= 21), default=-1)
            winners = [pid for pid, score in scores.items() if score == best] if best >= 0 else []
        self._complete(winners)

    def view(self, viewer: str | None = None) -> dict[str, Any]:
        s = self.state
        result = {k: deepcopy(s[k]) for k in ("id", "game", "rules", "revision", "phase", "current", "winner", "winners")}
        result["players"] = [{"id": p["id"], "name": p["name"], "kind": p["kind"], "done": p["done"],
                              "count": len(p["hand"]), "hand": deepcopy(p["hand"]) if viewer == p["id"] or s["phase"] == "complete" else [],
                              "total": hand_total(p["hand"]) if viewer == p["id"] or s["phase"] == "complete" else None}
                             for p in s["players"]]
        result["dealer"] = {"upcard": s["dealer"][0] if s["dealer"] else None,
                            "count": len(s["dealer"]), "hand": deepcopy(s["dealer"]) if s["phase"] == "complete" else [],
                            "total": hand_total(s["dealer"]) if s["phase"] == "complete" and s["dealer"] else None}
        result["draw_count"] = len(s["draw"])
        result["events"] = deepcopy(s["events"][-15:])
        result["legal_actions"] = self.legal_actions(viewer) if viewer else []
        return result


def knuckles_value(card: str) -> int:
    rank = face(card).split("-", 1)[0]
    return 0 if rank == "J" else 1 if rank == "A" else 10 if rank in ("Q", "K") else int(rank)


class KnucklesMatch(VariantMatch):
    """Documented five-card, low-score knock variant; no physical punishments."""

    DECK = STANDARD_DECK

    @classmethod
    def new(cls, participants: list[dict[str, str]], seed: int | None = None):
        players = _participants(participants, 2, 6)
        draw = _shuffle(list(cls.DECK), seed)
        for p in players:
            p["hand"] = [draw.pop() for _ in range(5)]
        state = {"id": uuid4().hex, "game": "knuckles", "rules": "five-card-low-score-v1",
                 "revision": 0, "created_at": time.time(), "completed_at": None, "phase": "play",
                 "step": "take", "current": 0, "players": players, "draw": draw,
                 "discard": [draw.pop()], "knocker": None, "remaining": None, "winner": None, "winners": [], "events": []}
        return cls(state)

    def _located(self):
        yield from self.state["draw"]
        yield from self.state["discard"]
        for p in self.state["players"]:
            yield from p["hand"]

    def legal_actions(self, actor: str) -> list[dict[str, Any]]:
        s = self.state
        if s["phase"] != "play" or s["players"][s["current"]]["id"] != actor:
            return []
        if s["step"] == "take":
            actions = [{"command": "take", "args": {"source": "stock"}}] if s["draw"] else []
            if s["discard"]:
                actions.append({"command": "take", "args": {"source": "discard"}})
            if s["knocker"] is None:
                actions.append({"command": "knock", "args": {}})
            return actions
        return [{"command": "discard", "args": {"card": card}} for card in s["players"][s["current"]]["hand"]]

    def _finish_scores(self) -> None:
        scores = {p["id"]: sum(knuckles_value(card) for card in p["hand"]) for p in self.state["players"]}
        best = min(scores.values())
        self._event("scores", scores=scores)
        self._complete([pid for pid, score in scores.items() if score == best])

    def _advance(self) -> None:
        s = self.state
        if s["knocker"] is not None:
            s["remaining"] -= 1
            if s["remaining"] <= 0:
                self._finish_scores()
                return
        if not s["draw"]:
            self._finish_scores()
            return
        s["current"] = (s["current"] + 1) % len(s["players"])
        s["step"] = "take"
        self._event("turn", player=s["players"][s["current"]]["id"])

    def _act(self, actor: str, command: str, args: dict[str, Any]) -> None:
        s = self.state
        hand = s["players"][s["current"]]["hand"]
        if command == "knock":
            s["knocker"] = actor
            s["remaining"] = len(s["players"])
            self._event("knock", player=actor)
            self._advance()
        elif command == "take":
            hand.append(s["draw"].pop() if args["source"] == "stock" else s["discard"].pop())
            s["step"] = "discard"
            self._event("take", player=actor, source=args["source"])
        else:
            hand.remove(args["card"])
            s["discard"].append(args["card"])
            self._event("discard", player=actor, card=args["card"])
            self._advance()

    def view(self, viewer: str | None = None) -> dict[str, Any]:
        s = self.state
        result = {k: deepcopy(s[k]) for k in ("id", "game", "rules", "revision", "phase", "current", "step",
                                                 "winner", "winners", "knocker", "remaining")}
        result["players"] = [{"id": p["id"], "name": p["name"], "kind": p["kind"], "count": len(p["hand"]),
                              "hand": deepcopy(p["hand"]) if viewer == p["id"] or s["phase"] == "complete" else [],
                              "total": sum(knuckles_value(card) for card in p["hand"])
                              if viewer == p["id"] or s["phase"] == "complete" else None}
                             for p in s["players"]]
        result["draw_count"] = len(s["draw"])
        result["discard"] = s["discard"][-4:]
        result["events"] = deepcopy(s["events"][-15:])
        result["legal_actions"] = self.legal_actions(viewer) if viewer else []
        return result


ENGINES = {"skip-bo": SkipBoMatch, "21": TwentyOneMatch, "blackjack": TwentyOneMatch, "knuckles": KnucklesMatch}


def new_variant(game: str, participants: list[dict[str, str]], seed: int | None = None) -> VariantMatch:
    if game not in ENGINES:
        raise GameError("Unknown game")
    if game in ("21", "blackjack"):
        return TwentyOneMatch.new(participants, seed=seed, game=game)
    return ENGINES[game].new(participants, seed=seed)

