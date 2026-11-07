"""Fourfold Mandate First Edition v1.0: deterministic simultaneous-order engine.

Source: Fourfold_Mandate_v1.0_First_Edition.pdf (22 October 2026), pp. 2–17.
Rules have no shuffle, draw, turn order, or random tie-breaker. Each player owns
their own 56-card deck; identical labels in different decks are distinct cards.
"""

from __future__ import annotations

from copy import deepcopy
import time
from typing import Any
from uuid import uuid4

from .game import GameError

SUITS = ("hearts", "diamonds", "clubs", "spades")
FACES = tuple(f"{n:02d}" for n in range(1, 11)) + ("ace", "jack", "queen", "king")
DECK = tuple(f"{face}-{suit}" for suit in SUITS for face in FACES)
RULE_VERSION = "fourfold-first-edition-1.0"


def target(round_no: int, suit: str) -> int:
    if not 1 <= round_no <= 12 or suit not in SUITS:
        raise GameError("Invalid round or estate")
    return ((round_no - 1 + (4, 6, 8, 10)[SUITS.index(suit)] - 1) % 10) + 1


def card_cost(card: str, round_no: int) -> int:
    face, suit = card.split("-", 1)
    return target(round_no, suit) if face == "ace" else {"jack": 4, "queen": 5, "king": 8}.get(face, int(face) if face.isdigit() else 0)


class FourfoldMatch:
    """Single authoritative state with private commitments and atomic actions."""

    def __init__(self, state: dict[str, Any]):
        self.state = state
        self.validate()

    @classmethod
    def new(cls, participants: list[dict[str, str]], *, seed: int | None = None) -> "FourfoldMatch":
        del seed  # Official Fourfold has no random setup or random resolution.
        if not 2 <= len(participants) <= 6:
            raise GameError("Fourfold requires 2–6 participants")
        ids = [p.get("id") for p in participants]
        if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise GameError("Participants require distinct nonempty IDs")
        players = []
        for p in participants:
            if p.get("kind", "human") not in ("human", "ai"):
                raise GameError("Unknown player type")
            players.append({"id": p["id"], "name": str(p.get("name") or p["id"])[:40],
                            "kind": p.get("kind", "human"), "mp": 0, "treasury": 2,
                            "seals": dict.fromkeys(SUITS, 0), "era_seals": dict.fromkeys(SUITS, 0),
                            "spent": [], "foundation": None, "orders": None})
        return cls({"id": uuid4().hex, "game": "fourfold", "rules": RULE_VERSION,
                    "created_at": time.time(), "completed_at": None, "revision": 0, "round": 1,
                    "phase": "plan", "players": players, "winner": None, "winners": [], "events": []})

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "FourfoldMatch":
        return cls(deepcopy(state))

    def validate(self) -> None:
        s = self.state
        if s.get("game") != "fourfold" or s.get("rules") != RULE_VERSION:
            raise GameError("Unsupported Fourfold rules version")
        if not 1 <= s["round"] <= 12 or s["phase"] not in ("plan", "complete"):
            raise GameError("Invalid round or phase")
        players = s["players"]
        if not 2 <= len(players) <= 6 or len({p["id"] for p in players}) != len(players):
            raise GameError("Invalid participant identities")
        for p in players:
            if not 0 <= p["treasury"] <= 8 or p["mp"] < 0:
                raise GameError("Invalid resource amount")
            if set(p["seals"]) != set(SUITS) or set(p["era_seals"]) != set(SUITS):
                raise GameError("Invalid seal counter")
            if any(type(n) is not int or n < 0 for n in p["seals"].values()):
                raise GameError("Invalid seal count")
            if not set(p["spent"]) <= set(DECK) or len(p["spent"]) != len(set(p["spent"])):
                raise GameError("Invalid spent cards")
            foundation = p["foundation"]
            if foundation is not None and (foundation["card"] not in p["spent"] or
                                           foundation["era"] != (s["round"] - 1) // 4):
                raise GameError("Invalid active foundation")
            if p["orders"] is not None:
                self._validate_orders(p, p["orders"])
        if (s["phase"] == "complete") != bool(s["winners"]):
            raise GameError("Invalid match completion")

    def _validate_orders(self, player: dict[str, Any], orders: list[dict[str, Any]]) -> int:
        s = self.state
        if not isinstance(orders, list) or len(orders) > 3:
            raise GameError("Submit zero to three orders")
        spent = set(player["spent"])
        estates: set[str] = set()
        cp = 0
        treasury = 0
        foundation_count = int(player["foundation"] is not None)
        for order in orders:
            if not isinstance(order, dict) or order.get("card") not in DECK:
                raise GameError("Unrecognized card")
            card = order["card"]
            face, suit = card.split("-", 1)
            if card in spent or suit in estates:
                raise GameError("A card is one-use and each estate gets at most one order")
            estates.add(suit)
            if order.get("kind", "claim") not in ("claim", "foundation"):
                raise GameError("Invalid order type")
            kind = order.get("kind", "claim")
            boost = order.get("treasury", 0)
            if type(boost) is not int or not 0 <= boost <= 2:
                raise GameError("Treasury boost must be 0, 1 or 2")
            if kind == "foundation":
                if face not in FACES[:10] or foundation_count or (s["round"] - 1) % 4 > 1 or boost:
                    raise GameError("Foundation requires a number in the first two rounds of an era")
                foundation_count += 1
            if face == "jack" and kind == "claim":
                if order.get("target") not in {p["id"] for p in s["players"] if p["id"] != player["id"]}:
                    raise GameError("A Jack must target another participant")
            elif order.get("target") is not None:
                raise GameError("Only a Jack may declare a target")
            cp += card_cost(card, s["round"])
            treasury += boost
            spent.add(card)
        if cp > 16 or treasury > player["treasury"]:
            raise GameError("CP or Treasury budget exceeded")
        return cp

    def act(self, actor: str, command: str, **args: Any) -> dict[str, Any]:
        snapshot = deepcopy(self.state)
        try:
            if self.state["phase"] != "plan" or command != "submit":
                raise GameError("Fourfold is awaiting secret orders or is complete")
            player = next((p for p in self.state["players"] if p["id"] == actor), None)
            if player is None or player["orders"] is not None:
                raise GameError("Unknown player or orders already locked")
            orders = args.get("orders")
            self._validate_orders(player, orders)
            player["orders"] = deepcopy(orders)
            self.state["events"].append({"type": "ready", "round": self.state["round"], "player": actor})
            if all(p["orders"] is not None for p in self.state["players"]):
                self._resolve_round()
            self.validate()
            self.state["revision"] += 1
            return {"round": self.state["round"], "phase": self.state["phase"]}
        except (ValueError, TypeError, KeyError) as exc:
            self.state = snapshot
            if isinstance(exc, GameError):
                raise
            raise GameError("Invalid Fourfold orders") from exc

    def _resolve_round(self) -> None:
        s = self.state
        players = s["players"]
        round_no = s["round"]
        # Pre-round snapshot prevents accounting order from influencing winners.
        before = {p["id"]: {"mp": p["mp"], "seals": dict(p["seals"])} for p in players}
        contests: dict[str, list[dict[str, Any]]] = {suit: [] for suit in SUITS}
        costs: dict[str, int] = {}
        for p in players:
            costs[p["id"]] = self._validate_orders(p, p["orders"])
            for o in p["orders"]:
                card = o["card"]
                face, suit = card.split("-", 1)
                p["spent"].append(card)
                p["treasury"] -= o.get("treasury", 0)
                if o.get("kind", "claim") == "foundation":
                    p["foundation"] = {"card": card, "era": (round_no - 1) // 4,
                                       "active_from": round_no + 1}
                else:
                    contests[suit].append({"player": p, "order": o, "face": face,
                                           "cost": card_cost(card, round_no)})
        awards: list[dict[str, Any]] = []
        for suit, claims in contests.items():
            jacks = [c for c in claims if c["face"] == "jack"]
            for c in claims:
                p, face, o = c["player"], c["face"], c["order"]
                exact = face == "ace" or (face.isdigit() and int(face) == target(round_no, suit))
                base = target(round_no, suit) + 3 if face == "ace" else (
                    {"jack": 4, "queen": 6, "king": 8}.get(face, int(face) if face.isdigit() else 0))
                bonus = 3 if face.isdigit() and exact else 0
                if face == "queen" and any(j["player"]["id"] != p["id"] for j in jacks):
                    bonus += 2
                if face == "king" and any(before[q["id"]]["seals"][suit] > before[p["id"]]["seals"][suit] for q in players):
                    bonus += 2
                f = p["foundation"]
                if f is not None and f["active_from"] <= round_no and f["card"].endswith("-" + suit):
                    n = int(f["card"].split("-")[0])
                    bonus += 1 if n <= 4 else 2 if n <= 8 else 3
                penalty = 0 if face == "queen" else 3 * sum(j["order"].get("target") == p["id"] for j in jacks)
                c["strength"] = max(0, base + bonus + o.get("treasury", 0) * 2 - penalty)
                c["exact"] = exact
            ranked = sorted((c for c in claims if c["strength"] > 0), key=lambda c: (
                -c["strength"], before[c["player"]["id"]]["seals"][suit],
                before[c["player"]["id"]]["mp"], c["cost"]))
            if not ranked:
                continue
            rank_key = lambda c: (c["strength"], before[c["player"]["id"]]["seals"][suit],
                                  before[c["player"]["id"]]["mp"], c["cost"])
            tied_first = [c for c in ranked if rank_key(c) == rank_key(ranked[0])]
            if len(tied_first) > 1:
                for c in tied_first:
                    c["player"]["mp"] += 1
                awards.append({"estate": suit, "tie": [c["player"]["id"] for c in tied_first]})
                continue
            winner = ranked[0]
            p, o = winner["player"], winner["order"]
            p["mp"] += 3
            p["seals"][suit] += 1
            p["era_seals"][suit] += 1
            if suit == "hearts" and not o.get("treasury", 0):
                p["mp"] += 1
            if suit == "diamonds":
                p["treasury"] = min(8, p["treasury"] + 2)
            if suit == "clubs" and winner["exact"]:
                p["mp"] += 1
            if suit == "spades" and len(ranked) > 1 and winner["strength"] - ranked[1]["strength"] >= 3:
                p["mp"] += 1
            if winner["face"] == "king":
                p["mp"] += 1
            if len(ranked) > 1:
                second = rank_key(ranked[1])
                for c in ranked[1:]:
                    if rank_key(c) == second:
                        c["player"]["mp"] += 1
            awards.append({"estate": suit, "winner": p["id"], "strength": winner["strength"]})
        for p in players:
            p["treasury"] = min(8, p["treasury"] + min(2, (16 - costs[p["id"]]) // 4))
        if round_no % 4 == 0:
            for suit in SUITS:
                counts = [p["era_seals"][suit] for p in players]
                best = max(counts)
                if best and counts.count(best) == 1:
                    players[counts.index(best)]["mp"] += 2
            for p in players:
                p["foundation"] = None
                p["era_seals"] = dict.fromkeys(SUITS, 0)
        s["events"].append({"type": "round_resolved", "round": round_no, "awards": awards,
                            "revealed": {p["id"]: deepcopy(p["orders"]) for p in players}})
        if round_no == 12:
            for p in players:
                p["mp"] += 6 * min(p["seals"].values()) + p["treasury"] // 3
            ranking = lambda p: (p["mp"], min(p["seals"].values()), sum(p["seals"].values()), p["treasury"])
            top = max(map(ranking, players))
            s["winners"] = [p["id"] for p in players if ranking(p) == top]
            s["winner"] = s["winners"][0] if len(s["winners"]) == 1 else None
            s["completed_at"] = time.time()
            s["phase"] = "complete"
        else:
            s["round"] += 1
        for p in players:
            p["orders"] = None
        s["events"] = s["events"][-200:]

    def view(self, viewer: str | None) -> dict[str, Any]:
        s = self.state
        result = {k: deepcopy(s[k]) for k in ("id", "game", "rules", "revision", "round", "phase", "winner", "winners", "events")}
        result["targets"] = {suit: target(s["round"], suit) for suit in SUITS}
        result["players"] = []
        for p in s["players"]:
            visible = {k: deepcopy(p[k]) for k in ("id", "name", "kind", "mp", "treasury", "seals", "spent", "foundation")}
            visible["ready"] = p["orders"] is not None
            visible["available_count"] = len(DECK) - len(p["spent"])
            if p["id"] == viewer or s["phase"] == "complete":
                visible["available"] = sorted(set(DECK) - set(p["spent"]))
                visible["orders"] = deepcopy(p["orders"])
            result["players"].append(visible)
        return result
