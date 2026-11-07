import unittest
import threading

from app.game import CARDS, Match
from slai.bridge.agents import CardAgentBridge, rank_legal_card


class AgentAdapterTests(unittest.TestCase):
    def test_fake_slai_proposal_is_used_only_if_legal(self):
        m = Match.new([{"id": "ai", "kind": "ai"}, {"id": "other", "kind": "human"}], seed=19)
        bridge = CardAgentBridge()
        bridge._initialized = True

        class FakeAgent:
            def choose_card_move(self, observation):
                return {"card": observation["legal"][0]}

        bridge._agent = FakeAgent()
        # Find a test state with at least one legal move.
        if not m.legal_cards("ai"):
            m.state["active_color"] = next(CARDS[x]["color"] for x in m.state["players"][0]["hand"]
                                           if CARDS[x]["color"] is not None)
        command, kwargs = bridge.move(m, "ai")
        self.assertEqual(command, "play")
        self.assertIn(kwargs["card"], m.legal_cards("ai"))

    def test_difficulty_uses_a_legal_observation(self):
        m = Match.new([{"id": "ai", "kind": "ai"}, {"id": "other", "kind": "human"}], seed=21)
        m.state["active_color"] = "blue"
        observation = m.view("ai")
        if observation["legal"]:
            for difficulty in ("easy", "medium", "hard", "expert"):
                observation["difficulty"] = difficulty
                self.assertIn(rank_legal_card(observation), observation["legal"])

    def test_timeout_disables_stalled_agent_and_uses_legal_fallback(self):
        m = Match.new([{"id": "ai", "kind": "ai"}, {"id": "other", "kind": "human"}], seed=19)
        if not m.legal_cards("ai"):
            m.state["active_color"] = next(CARDS[x]["color"] for x in m.state["players"][0]["hand"]
                                           if CARDS[x]["color"] is not None)
        bridge = CardAgentBridge()
        bridge._initialized = True
        bridge.timeout_seconds = 0.01
        gate = threading.Event()

        class SlowAgent:
            def choose_card_move(self, observation):
                gate.wait(0.2)
                return {"card": "not-owned"}

        bridge._agent = SlowAgent()
        try:
            command, args = bridge.move(m, "ai")
            self.assertEqual(command, "play")
            self.assertIn(args["card"], m.legal_cards("ai"))
            self.assertEqual(bridge.status, "fallback")
            self.assertIsNone(bridge._agent)
            self.assertIn("timed out", bridge.last_diagnostic)
        finally:
            gate.set()


if __name__ == "__main__":
    unittest.main()
