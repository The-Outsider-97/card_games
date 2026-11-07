"""SLAI agent adapter for card decisions; the rules engine remains authoritative.

This bridge intentionally does not pretend an unavailable planning agent ran.
Fallback decisions are recorded and exposed to the caller.
"""

from __future__ import annotations

from typing import Any

from app.game import CARDS, COLORS, Match


class CardAgentBridge:
    def __init__(self, difficulty: str = "medium"):
        self.difficulty = difficulty if difficulty in {"easy", "medium", "hard", "expert"} else "medium"
        self._agent: Any = None
        self.status = "fallback"
        try:
            from src.agents.agent_factory import AgentFactory  # type: ignore[import-not-found]

            factory = AgentFactory()
            self._agent = factory.create_agent("planning")
            self.status = "slai-planning"
        except Exception:  # The optional subsystem must not prevent a local game from starting.
            self._agent = None

    def _proposal(self, observation: dict[str, Any]) -> str | None:
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
            ranked = sorted(legal, key=lambda c: (
                0 if CARDS[c]["action"] is None else 1,
                -sum(CARDS[x]["color"] == CARDS[c]["color"] for x in match.state["players"][match.state["current"]]["hand"]),
                c,
            ))
            suggested = ranked[0] if self.difficulty == "easy" else ranked[-1]
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
