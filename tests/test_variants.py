"""Regressions for newly registered game families and shared deck subsets."""

from __future__ import annotations

import unittest

from app.game import GameError
from app.variants import (COLORS, ENGINES, SKIP_DECK, STANDARD_DECK, KnucklesMatch,
                          SkipBoMatch, TwentyOneMatch, face, hand_total, knuckles_value, new_variant)
from slai.bridge.agents import rank_variant_action


PARTICIPANTS = [{"id": "human", "name": "Human", "kind": "human"},
                {"id": "agent", "name": "SLAI", "kind": "ai"}]


class VariantRulesTests(unittest.TestCase):
    def test_inventory_and_presentation_subset(self):
        self.assertEqual(set(ENGINES), {"skip-bo", "21", "blackjack", "knuckles"})
        self.assertEqual(len(SKIP_DECK), 162)
        self.assertEqual(len(set(SKIP_DECK)), 162)
        self.assertEqual(len({face(x) for x in SKIP_DECK}), 52)
        self.assertTrue(all(face(x).startswith("Wild-") or 1 <= int(face(x).split("-")[0]) <= 12 for x in SKIP_DECK))
        self.assertEqual(len(STANDARD_DECK), 52)
        self.assertTrue(all("-neutral" not in card and not card.startswith("+") for card in STANDARD_DECK))

    def test_skip_bo_stock_dealing_unique_cards_and_authorized_view(self):
        m = SkipBoMatch.new(PARTICIPANTS, seed=11)
        self.assertEqual([len(p["stock"]) for p in m.state["players"]], [30, 30])
        self.assertEqual(len(m.state["players"][0]["hand"]), 5)
        self.assertEqual(len(m.state["draw"]), 97)
        view = m.view("human")
        self.assertEqual(len(view["players"][0]["hand"]), 5)
        self.assertFalse(view["players"][1]["hand"])
        self.assertNotIn("draw", view)
        self.assertTrue(view["players"][1]["stock_top"])
        self.assertEqual([len(p["stock"]) for p in SkipBoMatch.new(
            [{"id": str(i)} for i in range(5)], seed=1).state["players"]], [20] * 5)

    def test_invalid_actions_do_not_change_state(self):
        import json
        for game in ENGINES:
            with self.subTest(game=game):
                m = new_variant(game, PARTICIPANTS, seed=3)
                before = json.dumps(m.state, sort_keys=True)
                with self.assertRaises(GameError):
                    m.act("agent", "hit")
                with self.assertRaises(GameError):
                    m.act("human", "play", card="fake")
                self.assertEqual(json.dumps(m.state, sort_keys=True), before)

    def test_blackjack_and_competitive_21_are_distinct(self):
        self.assertEqual(hand_total(["A-hearts", "K-diamonds"]), 21)
        self.assertEqual(hand_total(["A-hearts", "A-clubs", "09-spades"]), 21)
        self.assertEqual(hand_total(["K-spades", "Q-spades", "02-clubs"]), 22)
        blackjack = TwentyOneMatch.new(PARTICIPANTS, seed=4, game="blackjack")
        competitive = TwentyOneMatch.new(PARTICIPANTS, seed=4, game="21")
        self.assertEqual(len(blackjack.state["dealer"]), 2)
        self.assertEqual(len(competitive.state["dealer"]), 0)
        self.assertEqual(blackjack.view("human")["dealer"]["count"], 2)
        self.assertFalse(blackjack.view("human")["dealer"]["hand"])
        self.assertFalse(competitive.view("human")["players"][1]["hand"])

    def test_knuckles_five_card_low_score_and_knock(self):
        self.assertEqual([knuckles_value(x) for x in ("J-clubs", "A-spades", "Q-diamonds", "08-hearts")], [0, 1, 10, 8])
        match = KnucklesMatch.new(PARTICIPANTS, seed=8)
        self.assertEqual(len(match.view("human")["players"][0]["hand"]), 5)
        self.assertEqual(match.view("human")["players"][1]["hand"], [])
        match.act("human", "knock")
        self.assertEqual(match.state["knocker"], "human")
        self.assertEqual(match.state["remaining"], 1)
        self.assertEqual(match.state["players"][match.state["current"]]["id"], "agent")
        take = next(a for a in match.legal_actions("agent") if a["command"] == "take")
        match.act("agent", take["command"], **take["args"])
        card = match.state["players"][1]["hand"][-1]
        match.act("agent", "discard", card=card)
        self.assertEqual(match.state["phase"], "complete")
        self.assertTrue(match.state["winners"])

    def test_difficulty_profiles_produce_different_legal_decisions(self):
        blackjack = TwentyOneMatch.new(PARTICIPANTS, seed=4, game="blackjack")
        view = blackjack.view("human")
        view["players"][view["current"]]["total"] = 16
        view["dealer"]["upcard"] = "06-spades"
        self.assertEqual(rank_variant_action({**view, "difficulty": "easy"})["command"], "stand")
        self.assertEqual(rank_variant_action({**view, "difficulty": "hard"})["command"], "hit")
        self.assertEqual(rank_variant_action({**view, "difficulty": "expert"})["command"], "stand")

        knuckles = KnucklesMatch.new(PARTICIPANTS, seed=8)
        view = knuckles.view("human")
        view["step"] = "discard"
        view["legal_actions"] = [{"command": "discard", "args": {"card": card}}
                                 for card in ("02-clubs", "K-spades")]
        self.assertEqual(rank_variant_action({**view, "difficulty": "easy"})["args"]["card"], "02-clubs")
        self.assertEqual(rank_variant_action({**view, "difficulty": "medium"})["args"]["card"], "K-spades")

    def test_full_matches_preserve_cards_and_finish_with_legal_ai_decisions(self):
        for game in ENGINES:
            for seed in range(4):
                with self.subTest(game=game, seed=seed):
                    match = new_variant(game, PARTICIPANTS, seed=seed)
                    for step in range(3500):
                        if match.state["phase"] == "complete":
                            break
                        actor = match.state["players"][match.state["current"]]["id"]
                        observation = match.view(actor)
                        proposal = rank_variant_action(observation)
                        self.assertIn(proposal, observation["legal_actions"])
                        match.act(actor, proposal["command"], **proposal["args"])
                        match.validate()
                    self.assertEqual(match.state["phase"], "complete")
                    self.assertLess(step, 3500)
                    self.assertEqual(len(list(match._located())), len(match.DECK))


if __name__ == "__main__":
    unittest.main()
