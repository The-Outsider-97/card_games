"""SLAI agent adapter for card decisions; the rules engine remains authoritative.

This bridge intentionally does not pretend an unavailable planning agent ran.
Fallback decisions are recorded and exposed to the caller.
"""

from __future__ import annotations

from typing import Any, Mapping
import threading

from app.fourfold import FourfoldMatch, SUITS, card_cost

from app.game import CARDS, COLORS, Match


class CardAgentBridge:
    def __init__(self, difficulty: str = "medium"):
        self.difficulty = difficulty if difficulty in {"easy", "medium", "hard", "expert"} else "medium"
        self._agent: Any = None
        self._initialized = False
        self.status = "fallback"
        self.last_diagnostic = "Agent has not been initialized"
        self.timeout_seconds = 0.25

    def _ensure_agent(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        try:
            from src.agents.base_agent import BaseAgent  # type: ignore[import-not-found]
            from src.agents.agent_factory import AgentFactory  # type: ignore[import-not-found]

            class CardGameAgent(BaseAgent):
                """Game-specialized SLAI BaseAgent; receives only authorized observations."""

                def perform_task(self, task_data: Mapping[str, Any]) -> dict[str, str]:
                    observation = task_data.get("observation", {})
                    if not isinstance(observation, dict):
                        raise ValueError("Card game observation must be structured")
                    return {"card": rank_legal_card(observation)}

                def choose_card_move(self, observation: dict[str, Any]) -> dict[str, str]:
                    return self.perform_task({"observation": observation})

                def choose_fourfold_orders(self, observation: dict[str, Any]) -> dict[str, Any]:
                    return {"orders": rank_fourfold_orders(observation, observation.get("difficulty", "medium"))}

            factory = AgentFactory()
            self._agent = CardGameAgent(shared_memory=None, agent_factory=factory)
            self.status = "slai-card-agent"
            self.last_diagnostic = "SLAI BaseAgent specialization constructed"
        except Exception as exc:  # The optional subsystem must not prevent a local game from starting.
            self._agent = None
            self.last_diagnostic = f"SLAI initialization unavailable: {type(exc).__name__}"

    def _bounded(self, method_name: str, observation: dict[str, Any]) -> Any:
        self._ensure_agent()
        if self._agent is None:
            return None
        method = getattr(self._agent, method_name, None)
        if not callable(method):
            return None
        result: list[Any] = []
        error: list[Exception] = []

        def run() -> None:
            try:
                result.append(method(observation))
            except Exception as exc:
                error.append(exc)

        thread = threading.Thread(target=run, daemon=True, name="card-games-agent")
        thread.start()
        thread.join(self.timeout_seconds)
        if thread.is_alive():
            self.last_diagnostic = "SLAI decision timed out; switching to deterministic fallback"
            self._agent = None  # Prevent unbounded further timed-out threads.
        elif error:
            self.last_diagnostic = f"SLAI decision rejected: {type(error[0]).__name__}"
        else:
            return result[0] if result else None
        self.status = "fallback"
        return None

    def _proposal(self, observation: dict[str, Any]) -> str | None:
        result = self._bounded("choose_card_move", observation)
        return result.get("card") if isinstance(result, dict) and isinstance(result.get("card"), str) else None

    def fourfold_orders(self, match: FourfoldMatch, player_id: str) -> list[dict[str, Any]]:
        observation = match.view(player_id)
        observation["difficulty"] = self.difficulty
        result = self._bounded("choose_fourfold_orders", observation)
        player = next(p for p in match.state["players"] if p["id"] == player_id)
        if isinstance(result, dict) and isinstance(result.get("orders"), list):
            try:
                match._validate_orders(player, result["orders"])
                return result["orders"]
            except (ValueError, TypeError, KeyError):
                self.last_diagnostic = "SLAI submitted invalid Fourfold orders; fallback used"
        self.status = "fallback"
        return rank_fourfold_orders(observation, self.difficulty)

    def move(self, match: Match, player_id: str) -> tuple[str, dict[str, Any]]:
        legal = match.legal_cards(player_id)
        if not legal:
            return ("pass" if match.state["turn_drawn"] is not None else "draw", {})
        observation = match.view(player_id)
        observation["difficulty"] = self.difficulty
        suggested = self._proposal(observation)
        if suggested not in legal:
            # A transparent, legal fallback; not misrepresented as an SLAI decision.
            suggested = rank_legal_card(observation)
            self.status = "fallback"
        card = CARDS[suggested]
        choices: dict[str, Any] = {"card": suggested, "last_card": True}
        if card["color"] is None:
            hand = match.state["players"][match.state["current"]]["hand"]
            choices["color"] = max(COLORS, key=lambda c: sum(CARDS[x]["color"] == c for x in hand))
        if card["action"] == "Wild":
            choices["number"] = 7
        if card["action"] == "verdict":
            others = [p for p in match.state["players"] if p["id"] != player_id]
            choices["target"] = min(others, key=lambda p: len(p["hand"]))["id"]
        if card["action"] == "steal":
            choices["steal"] = match.state["discard"][-1]
        return "play", choices

    def selection(self, match: Match, player_id: str, count: int) -> list[str]:
        player = next(p for p in match.state["players"] if p["id"] == player_id)
        return player["hand"][:count]


def rank_legal_card(observation: dict[str, Any]) -> str:
    """Bounded imperfect-information policy. Never examines another private hand."""
    legal = observation.get("legal", [])
    if not isinstance(legal, list) or not legal:
        raise ValueError("No legal cards in observation")
    difficulty = observation.get("difficulty", "medium")
    current = observation["players"][observation["current"]]
    hand = current.get("hand", [])
    opponents = [p for p in observation["players"] if p["id"] != current["id"]]
    threatened = any(p["count"] <= 2 for p in opponents)
    if difficulty == "easy":
        return sorted(legal, key=lambda card: (CARDS[card]["action"] is not None, card))[0]

    def score(card: str) -> tuple[float, str]:
        definition = CARDS[card]
        action = definition["action"]
        color = definition["color"] or observation.get("active_color")
        own_color = sum(CARDS[x]["color"] == color for x in hand if x != card)
        pressure = 0
        if threatened and action in ("+1", "+2", "+4", "+5", "skip", "stop", "verdict"):
            pressure = 8 if difficulty in ("hard", "expert") else 3
        if action in ("Wild", "equality") and len(hand) > 3:
            pressure -= 2  # Keep powerful neutral actions for a critical turn when possible.
        if difficulty == "medium":
            return (own_color + pressure - (2 if action is not None else 0), card)
        if difficulty == "hard":
            return (own_color * 1.5 + pressure - (1 if action is not None else 0), card)
        return (own_color * 2 + pressure + (1 if action is None else 0), card)

    return max(legal, key=score)


def rank_fourfold_orders(observation: dict[str, Any], difficulty: str) -> list[dict[str, Any]]:
    """Bounded public-information planner; never reads another player's orders."""
    own = next((p for p in observation["players"] if "available" in p and p["id"] == observation.get("actor")), None)
    if own is None:
        own = next(p for p in observation["players"] if "available" in p)
    remaining = set(own["available"])
    round_no = observation["round"]
    max_orders = 1 if difficulty == "easy" else 2 if difficulty == "medium" else 3
    candidates = []
    for suit in SUITS:
        target_num = observation["targets"][suit]
        for card in remaining:
            if not card.endswith("-" + suit):
                continue
            cost = card_cost(card, round_no)
            if cost > 16:
                continue
            face = card.split("-")[0]
            strength = (target_num + 3 if face == "ace" else
                        {"jack": 4, "queen": 6, "king": 8}.get(face, int(face) if face.isdigit() else 0))
            if face.isdigit() and int(face) == target_num:
                strength += 3
            seal_gap = min(own["seals"].values()) == own["seals"][suit]
            utility = (strength - cost * (0.4 if difficulty in ("hard", "expert") else 0.8)
                       + (3 if seal_gap and difficulty == "expert" else 0))
            if difficulty == "easy":
                utility = -cost
            candidates.append((utility, suit, card, cost))
    candidates.sort(key=lambda t: (-t[0], t[2]))
    cp = 0
    used: set[str] = set()
    orders = []
    for _, suit, card, cost in candidates:
        if suit in used or cp + cost > 16:
            continue
        order: dict[str, Any] = {"card": card, "kind": "claim", "treasury": 0}
        if card.startswith("jack-"):
            opponents = [p for p in observation["players"] if p["id"] != own["id"]]
            order["target"] = max(opponents, key=lambda p: (p["seals"][suit], p["mp"]))["id"]
        if difficulty == "expert" and own["treasury"] > 0 and not orders:
            order["treasury"] = min(2, own["treasury"])
        orders.append(order)
        cp += cost
        used.add(suit)
        if len(orders) >= max_orders:
            break
    return orders
