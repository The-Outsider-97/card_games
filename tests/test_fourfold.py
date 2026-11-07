"""Fixtures from Fourfold Mandate First Edition v1.0, pp. 8, 12 and 13."""

import unittest

from app.fourfold import DECK, FourfoldMatch, card_cost, target
from app.game import GameError
from slai.bridge.agents import rank_fourfold_orders


def match(n=2):
    return FourfoldMatch.new([{"id": f"p{i}", "kind": "human"} for i in range(n)])


def submit(m, player, *orders):
    return m.act(player, "submit", orders=list(orders))


def claim(card, boost=0, target_id=None):
    return {"card": card, "kind": "claim", "treasury": boost, **({"target": target_id} if target_id else {})}


class FourfoldTests(unittest.TestCase):
    def test_decks_targets_costs_and_no_shuffle(self):
        self.assertEqual(len(DECK), 56)
        self.assertEqual([target(1, x) for x in ("hearts", "diamonds", "clubs", "spades")], [4, 6, 8, 10])
        self.assertEqual([target(5, x) for x in ("hearts", "diamonds", "clubs", "spades")], [8, 10, 2, 4])
        self.assertEqual(card_cost("queen-hearts", 1), 5)
        self.assertEqual(card_cost("ace-diamonds", 1), 6)
        m = match()
        self.assertEqual(m.state["players"][0]["spent"], [])
        self.assertEqual(m.state["round"], 1)

    def test_private_orders_are_hidden_and_locked(self):
        m = match()
        submit(m, "p0", claim("04-hearts"))
        self.assertTrue(m.view("p1")["players"][0]["ready"])
        self.assertNotIn("orders", m.view("p1")["players"][0])
        self.assertEqual(m.view("p0")["players"][0]["orders"][0]["card"], "04-hearts")
        with self.assertRaises(GameError):
            submit(m, "p0")

    def test_two_player_official_round_one(self):
        m = match()
        submit(m, "p0", claim("04-hearts"), claim("08-clubs", 1), claim("04-spades"))
        submit(m, "p1", claim("07-hearts", 1), claim("06-diamonds"), claim("03-spades"))
        self.assertEqual([(p["mp"], p["treasury"]) for p in m.state["players"]], [(8, 1), (7, 3)])
        self.assertEqual(m.state["players"][0]["seals"]["clubs"], 1)
        self.assertEqual(m.state["players"][1]["seals"]["diamonds"], 1)
        self.assertEqual(m.state["round"], 2)

    def test_four_player_official_round_one(self):
        m = match(4)
        submit(m, "p0", claim("04-hearts"), claim("05-diamonds"), claim("07-spades"))
        submit(m, "p1", claim("07-hearts"), claim("08-clubs"), claim("01-spades"))
        submit(m, "p2", claim("jack-hearts", target_id="p1"), claim("06-diamonds"), claim("06-spades"))
        submit(m, "p3", claim("queen-hearts"), claim("04-diamonds"), claim("06-clubs"))
        self.assertEqual([p["mp"] for p in m.state["players"]], [5, 4, 4, 5])
        self.assertEqual([p["treasury"] for p in m.state["players"]], [2, 2, 4, 2])

    def test_invalid_orders_do_not_change_state(self):
        m = match()
        for orders in ([claim("10-hearts"), claim("10-clubs")],
                       [claim("04-hearts"), claim("05-hearts")],
                       [claim("jack-hearts")],
                       [claim("04-hearts", boost=3)],
                       [{"card": "10-hearts", "kind": "foundation", "treasury": 1}]):
            with self.assertRaises(GameError):
                m.act("p0", "submit", orders=orders)
            self.assertEqual(m.state["revision"], 0)
            self.assertIsNone(m.state["players"][0]["orders"])

    def test_foundation_bonus_and_era_expiry(self):
        m = match()
        submit(m, "p0", {"card": "09-hearts", "kind": "foundation", "treasury": 0})
        submit(m, "p1")
        self.assertEqual(m.state["players"][0]["foundation"]["active_from"], 2)
        submit(m, "p0", claim("01-hearts"))
        submit(m, "p1", claim("02-hearts"))
        self.assertEqual(m.state["events"][-1]["awards"][0]["winner"], "p0")
        for _ in range(2):
            submit(m, "p0")
            submit(m, "p1")
        self.assertEqual(m.state["round"], 5)
        self.assertIsNone(m.state["players"][0]["foundation"])

    def test_unresolved_first_tie_has_no_seals(self):
        m = match()
        submit(m, "p0", claim("04-hearts"))
        submit(m, "p1", claim("04-hearts"))
        self.assertEqual([p["mp"] for p in m.state["players"]], [1, 1])
        self.assertEqual([p["seals"]["hearts"] for p in m.state["players"]], [0, 0])

    def test_twelve_rounds_and_shared_final_victory(self):
        m = match()
        for _ in range(12):
            submit(m, "p0")
            submit(m, "p1")
        self.assertEqual(m.state["phase"], "complete")
        self.assertEqual(set(m.state["winners"]), {"p0", "p1"})
        self.assertIsNone(m.state["winner"])
        with self.assertRaises(GameError):
            submit(m, "p0")
        self.assertEqual(FourfoldMatch.from_state(m.state).view("p0")["round"], 12)

    def test_ai_planner_legal_and_private(self):
        for difficulty in ("easy", "medium", "hard", "expert"):
            m = match()
            obs = m.view("p0")
            orders = rank_fourfold_orders(obs, difficulty)
            m._validate_orders(m.state["players"][0], orders)
            self.assertTrue(orders)


if __name__ == "__main__":
    unittest.main()
