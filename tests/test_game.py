"""Four-Color prototype rule and state-invariant regression tests."""

import copy
import unittest

from app.game import CARDS, GameError, Match


def match(players=3):
    return Match.new([{"id": f"p{i}", "name": f"Player {i}", "kind": "human"} for i in range(players)], seed=57)


def position(m: Match, player: int, card: str):
    """Put a card into a specific hand while maintaining exact conservation."""
    s = m.state
    if card in s["players"][player]["hand"]:
        return
    pinned = getattr(m, "_test_pinned", set())
    old = next(x for x in s["players"][player]["hand"] if x not in pinned)
    for pile in [s["draw"], s["discard"]] + [p["hand"] for p in s["players"]]:
        if card in pile:
            pile.remove(card)
            pile.append(old)
            break
    s["players"][player]["hand"].remove(old)
    s["players"][player]["hand"].append(card)
    m._test_pinned = pinned | {card}
    m.validate()


def top(m: Match, card: str):
    s = m.state
    old = s["discard"][-1]
    for pile in [s["draw"]] + [p["hand"] for p in s["players"]]:
        if card in pile:
            pile.remove(card)
            pile.append(old)
            break
    s["discard"][-1] = card
    s["active_color"] = CARDS[card]["color"] or "blue"
    s["wild_rank"] = None
    m.validate()


class FourColorTests(unittest.TestCase):
    def test_full_inventory_and_initial_hand(self):
        m = match(8)
        self.assertEqual(len(CARDS), 119)
        self.assertTrue(all(len(p["hand"]) == 7 for p in m.state["players"]))
        self.assertIsNone(CARDS[m.state["discard"][-1]]["action"])
        self.assertEqual(len(m.state["draw"]), 62)

    def test_rejected_move_is_atomic(self):
        m = match()
        before = copy.deepcopy(m.state)
        with self.assertRaises(GameError):
            m.act("p1", "play", card=m.state["players"][1]["hand"][0])
        self.assertEqual(m.state, before)

    def test_matching_rank_letter_and_neutral(self):
        m = match()
        top(m, "A-blue")
        position(m, 0, "A-red")
        position(m, 0, "skip-neutral")
        self.assertIn("A-red", m.legal_cards("p0"))
        self.assertIn("skip-neutral", m.legal_cards("p0"))
        self.assertNotEqual(CARDS["A-red"]["rank"], CARDS["01-red"]["rank"])

    def test_reverse_two_player_extra_turn(self):
        m = match(2)
        top(m, "07-blue")
        position(m, 0, "reverse-blue")
        m.act("p0", "play", card="reverse-blue")
        self.assertEqual(m.state["current"], 0)
        self.assertEqual(m.state["direction"], -1)

    def test_stop_restricts_actions_but_not_plain_rank(self):
        m = match()
        top(m, "stop-blue")
        m.state["current"] = 1
        m.state["stop_player"] = 1
        position(m, 1, "07-blue")
        position(m, 1, "skip-blue")
        self.assertIn("07-blue", m.legal_cards("p1"))
        self.assertNotIn("skip-blue", m.legal_cards("p1"))

    def test_draw_then_only_just_drawn_is_playable(self):
        m = match()
        top(m, "09-blue")
        m.state["draw"].remove("08-blue")
        m.state["draw"].append("08-blue")
        m.act("p0", "draw")
        self.assertEqual(m.state["turn_drawn"], "08-blue")
        self.assertEqual(m.legal_cards("p0"), ["08-blue"])

    def test_verdict_skips_two_scheduled_visits(self):
        m = match()
        top(m, "07-blue")
        position(m, 0, "verdict-neutral")
        m.act("p0", "play", card="verdict-neutral", color="red", target="p2")
        self.assertEqual(m.state["players"][2]["verdict"], 2)
        self.assertEqual(m.state["current"], 1)
        m._advance()
        self.assertEqual(m.state["players"][2]["verdict"], 1)
        m._advance()
        m._advance()
        self.assertEqual(m.state["players"][2]["verdict"], 0)

    def test_last_card_victory_precedes_ability(self):
        m = match()
        top(m, "07-blue")
        position(m, 0, "equality-neutral")
        hand = m.state["players"][0]["hand"]
        for item in hand[:]:
            if item != "equality-neutral":
                hand.remove(item)
                m.state["draw"].append(item)
        m.act("p0", "play", card="equality-neutral", color="green")
        self.assertEqual(m.state["winner"], "p0")
        self.assertIsNone(m.state["pending"])

    def test_swap_requires_both_private_choices(self):
        m = match()
        top(m, "07-blue")
        position(m, 0, "swap-neutral")
        m.act("p0", "play", card="swap-neutral", color="yellow")
        self.assertEqual(m.state["pending"]["kind"], "swap")
        a = m.state["players"][0]["hand"][0]
        b = m.state["players"][1]["hand"][0]
        m.act("p0", "select", cards=[a])
        self.assertIsNotNone(m.state["pending"])
        m.act("p1", "select", cards=[b])
        self.assertIsNone(m.state["pending"])
        self.assertIn(b, m.state["players"][0]["hand"])
        self.assertIn(a, m.state["players"][1]["hand"])

    def test_steal_may_take_previous_top(self):
        m = match()
        top(m, "07-blue")
        position(m, 0, "steal-neutral")
        m.act("p0", "play", card="steal-neutral", color="red", steal="07-blue")
        self.assertIn("07-blue", m.state["players"][0]["hand"])
        self.assertEqual(m.state["discard"][-1], "steal-neutral")

    def test_equality_keeps_card_conservation(self):
        m = match()
        top(m, "07-blue")
        position(m, 0, "equality-neutral")
        m.act("p0", "play", card="equality-neutral", color="blue")
        self.assertEqual(len(m.state["players"][0]["hand"]), 6)
        for selection in m.outstanding_choices():
            i = m._player_index(selection["player"])
            m.act(selection["player"], "select", cards=m.state["players"][i]["hand"][:selection["count"]])
        self.assertEqual([len(p["hand"]) for p in m.state["players"]], [6, 6, 6])
        m.validate()

    def test_save_resume_and_private_views(self):
        m = match()
        saved = Match.from_state(m.state)
        self.assertEqual(saved.state, m.state)
        view = saved.view("p0")
        self.assertEqual(len(view["players"][0]["hand"]), 7)
        self.assertEqual(view["players"][1]["hand"], [])
        self.assertNotIn("draw", view)


if __name__ == "__main__":
    unittest.main()
