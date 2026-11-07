import unittest

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


if __name__ == "__main__":
    unittest.main()
