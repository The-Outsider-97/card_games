"""SLAI agent adapter for card decisions; the rules engine remains authoritative.

This bridge intentionally does not pretend an unavailable planning agent ran.
Fallback decisions are recorded and exposed to the caller.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.game import CARDS, COLORS, Match


class CardAgentBridge:
    def __init__(self, difficulty: str = "medium"):
        self.difficulty = difficulty if difficulty in {"easy", "medium", "hard", "expert"} else "medium"
        self._agent: Any = None
        self._initialized = False
        self.status = "fallback"

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

            factory = AgentFactory()
            self._agent = CardGameAgent(shared_memory=None, agent_factory=factory)
            self.status = "slai-card-agent"
        except Exception:  # The optional subsystem must not prevent a local game from starting.
            self._agent = None

    def _proposal(self, observation: dict[str, Any]) -> str | None:
        self._ensure_agent()
        if self._agent is None:
            return None
        # Only call an explicitly supported structured decision entrypoint.
        method = getattr(self._agent, "choose_card_move", None)
        if not callable(method):
            return None
        try:
            result = method(observation)
            if isinstance(result, dict):
                return result.get("card") if isinstance(result.get("card"), str) else None
        except (TypeError, ValueError, RuntimeError, TimeoutError):
            pass
        return None

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
