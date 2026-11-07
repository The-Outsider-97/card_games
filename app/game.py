"""Authoritative, serializable Four-Color v1 game state machine.

The 119 card definitions follow the prototype's documented physical inventory.
No presentation or agent code is allowed to mutate a match directly.
"""

from __future__ import annotations

from copy import deepcopy
from random import Random, SystemRandom
import time
from typing import Any
from uuid import uuid4

COLORS = ("blue", "green", "red", "yellow")
LETTERS = ("A", "J", "Q", "K")
COLOR_ACTIONS = ("+1", "+2", "+4", "+5", "cycle", "reverse", "skip", "stop", "Wild")
NEUTRAL_ACTIONS = ("+2", "+4", "cycle", "reverse", "skip", "stop", "Wild", "equality", "verdict", "swap", "steal")
RULE_VERSION = "four-color-1.0-prototype"


class GameError(ValueError):
    """A rejected player action; it never changes the game state."""


def card_definitions() -> dict[str, dict[str, Any]]:
    """One definition per actual color-deck face; never generate missing images."""
    cards: dict[str, dict[str, Any]] = {}
    for color in COLORS:
        for number in range(14):
            rank = f"{number:02d}"
            cards[f"{rank}-{color}"] = {"color": color, "rank": str(number), "action": None}
        for letter in LETTERS:
            cards[f"{letter}-{color}"] = {"color": color, "rank": letter, "action": None}
        for action in COLOR_ACTIONS:
            cards[f"{action}-{color}"] = {"color": color, "rank": None, "action": action}
    for action in NEUTRAL_ACTIONS:
        cards[f"{action}-neutral"] = {"color": None, "rank": None, "action": action}
    assert len(cards) == 119
    return cards


CARDS = card_definitions()


class Match:
    """Mutates a private snapshot and rolls back all rejected commands.

    Persist ``state`` after each successful action; ``from_state`` rechecks card
    conservation and basic player invariants before a save is resumed.
    """

    def __init__(self, state: dict[str, Any]):
        self.state = state
        self.validate()

    @classmethod
    def new(cls, participants: list[dict[str, str]], *, seed: int | None = None) -> "Match":
        if not 2 <= len(participants) <= 8:
            raise GameError("Four-Color requires 2–8 participants")
        ids = [p.get("id") for p in participants]
        if len(set(ids)) != len(ids) or not all(isinstance(i, str) and i for i in ids):
            raise GameError("Participants require distinct, nonempty IDs")
        rng = Random(seed) if seed is not None else SystemRandom()
        pile = list(CARDS)
        rng.shuffle(pile)
        players = []
        for participant in participants:
            kind = participant.get("kind", "human")
            if kind not in ("human", "ai"):
                raise GameError("Unknown player type")
            players.append({"id": participant["id"], "name": str(participant.get("name") or participant["id"])[:40],
                            "kind": kind, "hand": [pile.pop() for _ in range(7)], "verdict": 0})
        rejected = []
        while True:
            first = pile.pop()
            if CARDS[first]["action"] is None:
                break
            rejected.append(first)
        pile.extend(rejected)
        rng.shuffle(pile)
        state = {"id": uuid4().hex, "game": "four-color", "rules": RULE_VERSION, "revision": 0,
                 "created_at": time.time(), "completed_at": None,
                 "players": players, "draw": pile, "discard": [first], "current": 0, "direction": 1,
                 "test_seed": seed, "recycle_count": 0,
                 "active_color": CARDS[first]["color"], "wild_rank": None,
                 "stop_player": None, "turn_drawn": None, "pending": None,
                 "winner": None, "last_uncalled": None, "challenge_open": False, "events": []}
        return cls(state)

    @classmethod
    def from_state(cls, data: dict[str, Any]) -> "Match":
        return cls(deepcopy(data))

    def validate(self) -> None:
        s = self.state
        if s.get("game") != "four-color" or s.get("rules") != RULE_VERSION:
            raise GameError("Unsupported rules version")
        players = s["players"]
        if not 2 <= len(players) <= 8 or not 0 <= s["current"] < len(players):
            raise GameError("Invalid player state")
        if s["direction"] not in (-1, 1) or s["active_color"] not in COLORS:
            raise GameError("Invalid play direction or color")
        ids = [p["id"] for p in players]
        if len(set(ids)) != len(ids):
            raise GameError("Duplicate player identity")
        located = list(s["draw"]) + list(s["discard"])
        for p in players:
            if p["verdict"] not in (0, 1, 2):
                raise GameError("Invalid Verdict counter")
            located.extend(p["hand"])
        if len(located) != len(CARDS) or set(located) != set(CARDS):
            raise GameError("Cards have been lost, duplicated or fabricated")
        if not s["discard"]:
            raise GameError("Discard top is missing")
        if s["turn_drawn"] is not None and s["turn_drawn"] not in players[s["current"]]["hand"]:
            raise GameError("Just-drawn card is not in current hand")

    def _player_index(self, player_id: str) -> int:
        for i, p in enumerate(self.state["players"]):
            if p["id"] == player_id:
                return i
        raise GameError("Unknown player")

    def _event(self, kind: str, **data: Any) -> None:
        self.state["events"].append({"type": kind, **data})
        self.state["events"] = self.state["events"][-300:]

    def _draw_one(self, target: int) -> str | None:
        s = self.state
        if not s["draw"]:
            if len(s["discard"]) > 1:
                recyclable = s["discard"][:-1]
                s["discard"] = s["discard"][-1:]
                s["recycle_count"] += 1
                rng = (Random(f"{s['test_seed']}:{s['recycle_count']}")
                       if s["test_seed"] is not None else SystemRandom())
                rng.shuffle(recyclable)
                s["draw"] = recyclable
                self._event("recycle", count=len(recyclable))
        if not s["draw"]:
            return None
        card = s["draw"].pop()
        s["players"][target]["hand"].append(card)
        return card

    def _draw_many(self, target: int, count: int) -> int:
        drawn = sum(self._draw_one(target) is not None for _ in range(count))
        self._event("draw", player=self.state["players"][target]["id"], count=drawn)
        return drawn

    def _next(self, start: int, *, exclude: int | None = None) -> int | None:
        """Consume Verdict slots. Do not apply a new skip/draw to its caster."""
        s = self.state
        n = len(s["players"])
        seat = start
        for _ in range(n * 3):
            seat = (seat + s["direction"]) % n
            p = s["players"][seat]
            if p["verdict"]:
                p["verdict"] -= 1
                self._event("verdict_skip", player=p["id"], remaining=p["verdict"])
                continue
            if seat == exclude:
                return None
            return seat
        return None

    def _advance(self, effect: str | None = None) -> None:
        s = self.state
        origin = s["current"]
        s["turn_drawn"] = None
        s["stop_player"] = None
        target = self._next(origin, exclude=origin if effect else None)
        if target is None:
            target = origin
            effect = None
        if effect in ("skip", "+1", "+2", "+4", "+5"):
            if effect.startswith("+"):
                self._draw_many(target, int(effect[1:]))
            self._event("skip", player=s["players"][target]["id"], reason=effect)
            following = self._next(target)
            target = following if following is not None else origin
        elif effect == "stop":
            s["stop_player"] = target
        s["current"] = target
        self._event("turn", player=s["players"][target]["id"])

    def legal_cards(self, player_id: str) -> list[str]:
        s = self.state
        if s["winner"] is not None or s["pending"] is not None:
            return []
        index = self._player_index(player_id)
        if index != s["current"]:
            return []
        hand = [s["turn_drawn"]] if s["turn_drawn"] is not None else s["players"][index]["hand"]
        top = CARDS[s["discard"][-1]]
        legal = []
        for card in hand:
            c = CARDS[card]
            if s["stop_player"] == index and c["action"] is not None:
                continue
            if c["action"] == "Wild" or c["color"] is None:
                legal.append(card)
            elif c["color"] == s["active_color"]:
                legal.append(card)
            elif c["rank"] is not None and (c["rank"] == top["rank"] or c["rank"] == s["wild_rank"]):
                legal.append(card)
            elif c["action"] is not None and c["action"] == top["action"]:
                legal.append(card)
        return legal

    def act(self, actor: str, command: str, **args: Any) -> dict[str, Any]:
        """Atomic command entrypoint with validation/rollback and revision update."""
        snapshot = deepcopy(self.state)
        try:
            result = self._act(actor, command, **args)
            self.validate()
            self.state["revision"] += 1
            return result
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            self.state = snapshot
            if isinstance(exc, GameError):
                raise
            raise GameError("Invalid move or selection") from exc

    def _act(self, actor: str, command: str, **args: Any) -> dict[str, Any]:
        s = self.state
        index = self._player_index(actor)
        if s["winner"] is not None:
            raise GameError("This match has already ended")
        if command == "challenge":
            offender = s["last_uncalled"]
            if not s["challenge_open"] or offender is None or index == offender:
                raise GameError("No outstanding LAST CARD call to challenge")
            self._draw_many(offender, 2)
            s["challenge_open"] = False
            s["last_uncalled"] = None
            self._event("challenge", by=actor)
            return {"challenged": True}
        if s["pending"] is not None:
            if command != "select":
                raise GameError("Resolve the pending card choice first")
            self._select(index, args.get("cards"))
            return {"pending": s["pending"] is not None}
        if index != s["current"]:
            raise GameError("It is not this player's turn")
        if command not in ("play", "draw", "pass"):
            raise GameError("Unknown move")
        s["challenge_open"] = False
        s["last_uncalled"] = None
        if command == "draw":
            if s["turn_drawn"] is not None:
                raise GameError("Only one voluntary draw is allowed")
            card = self._draw_one(index)
            self._event("draw", player=actor, count=1 if card else 0)
            if card is None:
                self._advance()
            else:
                s["turn_drawn"] = card
                if card not in self.legal_cards(actor):
                    self._advance()
            return {"drawn": card is not None}
        if command == "pass":
            if s["turn_drawn"] is None:
                raise GameError("Draw a card before passing")
            self._advance()
            return {"passed": True}

        card = args.get("card")
        if not isinstance(card, str) or card not in self.legal_cards(actor):
            raise GameError("Card is not legal for this turn")
        definition = CARDS[card]
        action = definition["action"]
        color = args.get("color") if definition["color"] is None else definition["color"]
        if color not in COLORS:
            raise GameError("A neutral card requires a valid color")
        number = args.get("number")
        if action == "Wild" and (type(number) is not int or number not in range(14)):
            raise GameError("Wild requires a number from 0 through 13")
        target = args.get("target")
        if action == "verdict" and (not isinstance(target, str) or target == actor or target not in [p["id"] for p in s["players"]]):
            raise GameError("Verdict requires another player as target")
        steal = args.get("steal")
        if action == "steal" and steal not in s["discard"]:
            raise GameError("Select an old discard to steal")
        hand = s["players"][index]["hand"]
        hand.remove(card)
        s["discard"].append(card)
        s["active_color"] = color
        s["wild_rank"] = str(number) if action == "Wild" else None
        s["turn_drawn"] = None
        self._event("play", player=actor, card=card)
        if not hand:
            s["winner"] = actor
            s["completed_at"] = time.time()
            self._event("win", player=actor)
            return {"winner": actor}
        if action == "reverse":
            s["direction"] *= -1
            self._event("reverse", direction=s["direction"])
        if action == "verdict":
            target_index = self._player_index(target)
            s["players"][target_index]["verdict"] = 2
            self._event("verdict", target=target)
        if action == "steal":
            s["discard"].remove(steal)
            hand.append(steal)
            self._event("steal", player=actor, card=steal)
        if len(hand) == 1 and not args.get("last_card", False):
            s["last_uncalled"] = index
            s["challenge_open"] = True
        if action == "reverse" and len(s["players"]) == 2:
            self._event("turn", player=actor)
            return {"extra_turn": True}
        if action == "swap":
            neighbor = (index + s["direction"]) % len(s["players"])
            s["pending"] = {"kind": "swap", "caster": index, "neighbor": neighbor, "choices": {}}
        elif action == "cycle":
            s["pending"] = {"kind": "cycle", "caster": index, "choices": {}}
        elif action == "equality":
            target_size = len(hand)
            s["pending"] = {"kind": "equality", "caster": index, "size": target_size, "choices": {}}
        if s["pending"] is not None:
            self._finish_pending_if_ready()
        else:
            self._advance(action if action in ("skip", "stop", "+1", "+2", "+4", "+5") else None)
        return {"played": card}

    def _requirements(self) -> dict[int, int]:
        pending = self.state["pending"]
        if pending is None:
            return {}
        kind = pending["kind"]
        if kind == "swap":
            return {pending["caster"]: 1, pending["neighbor"]: 1}
        if kind == "cycle":
            return {i: 1 for i in range(len(self.state["players"]))}
        return {i: len(p["hand"]) - pending["size"] for i, p in enumerate(self.state["players"])
                if i != pending["caster"] and len(p["hand"]) > pending["size"]}

    def _select(self, index: int, cards: Any) -> None:
        s = self.state
        pending = s["pending"]
        required = self._requirements()
        if index not in required or str(index) in pending["choices"]:
            raise GameError("This player has no outstanding card selection")
        if not isinstance(cards, list) or len(cards) != required[index] or len(set(cards)) != len(cards):
            raise GameError(f"Select exactly {required[index]} distinct cards")
        if any(card not in s["players"][index]["hand"] for card in cards):
            raise GameError("Selection includes a card outside this hand")
        pending["choices"][str(index)] = cards[:]
        self._event("selected", player=s["players"][index]["id"], count=len(cards))
        self._finish_pending_if_ready()

    def _finish_pending_if_ready(self) -> None:
        s = self.state
        pending = s["pending"]
        required = self._requirements()
        if pending is None or any(str(i) not in pending["choices"] for i in required):
            return
        picks = {int(k): list(v) for k, v in pending["choices"].items()}
        kind = pending["kind"]
        if kind == "swap":
            a, b = pending["caster"], pending["neighbor"]
            x, y = picks[a][0], picks[b][0]
            s["players"][a]["hand"].remove(x)
            s["players"][b]["hand"].remove(y)
            s["players"][a]["hand"].append(y)
            s["players"][b]["hand"].append(x)
            self._event("swap", players=[s["players"][a]["id"], s["players"][b]["id"]])
        elif kind == "cycle":
            for i, selected in picks.items():
                s["players"][i]["hand"].remove(selected[0])
            for i, selected in picks.items():
                recipient = (i + s["direction"]) % len(s["players"])
                s["players"][recipient]["hand"].append(selected[0])
            self._event("cycle")
        elif kind == "equality":
            target_size = pending["size"]
            n = len(s["players"])
            # Return all excess before allocating any draws.
            for step in range(1, n):
                i = (pending["caster"] + step) % n
                for card in picks.get(i, []):
                    s["players"][i]["hand"].remove(card)
                    s["draw"].insert(0, card)
            for step in range(1, n):
                i = (pending["caster"] + step) % n
                self._draw_many(i, max(0, target_size - len(s["players"][i]["hand"])))
            self._event("equality", size=target_size)
        s["pending"] = None
        self._advance()

    def outstanding_choices(self) -> list[dict[str, Any]]:
        required = self._requirements()
        pending = self.state["pending"]
        if pending is None:
            return []
        return [{"player": self.state["players"][i]["id"], "count": count, "kind": pending["kind"]}
                for i, count in required.items() if str(i) not in pending["choices"]]

    def view(self, viewer: str | None = None) -> dict[str, Any]:
        """Authorized local seat view: other hands and the draw order are hidden."""
        s = self.state
        visible = {k: deepcopy(v) for k, v in s.items()
                   if k not in ("draw", "players", "events", "pending", "test_seed", "recycle_count")}
        visible["draw_count"] = len(s["draw"])
        visible["players"] = []
        for player in s["players"]:
            p = {key: value for key, value in player.items() if key != "hand"}
            p["count"] = len(player["hand"])
            p["hand"] = player["hand"][:] if player["id"] == viewer else []
            visible["players"].append(p)
        visible["choices"] = [c for c in self.outstanding_choices() if c["player"] == viewer]
        visible["outstanding"] = self.outstanding_choices()
        visible["legal"] = self.legal_cards(viewer) if viewer else []
        visible["events"] = [e for e in s["events"][-15:] if e["type"] not in ("selected",)]
        visible["stealable"] = s["discard"][:] if viewer == s["players"][s["current"]]["id"] else []
        return visible
