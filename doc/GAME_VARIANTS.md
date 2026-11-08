# Additional card games — rules, card sets and decisions

This register describes four playable game IDs in Card Games, without confusing
their decks with the `cards/colors/` or `cards/symbols/` **asset families**.
`app/variants.py` owns their rules and match state; `app/assets.py` audits
face coverage. No existing artwork has been renamed, altered or fabricated.

## Registrations and card inventory

| Game ID | Rules profile | Card instances | Existing faces reused | Included faces | Exclusions |
| --- | --- | ---: | ---: | --- | --- |
| `skip-bo` | 1–12 shared building piles, Wild | 162 | 52 `colors/` faces | 01–12 in blue/green/red/yellow; four colored Wilds | 00, 13, letters, +1/+2/+4/+5, other actions, neutrals |
| `21` | Competitive 21 house variant | 52 | 52 `symbols/` faces | A, 02–10, J, Q, K in four suits | 01, 11–13, special actions, Wild, neutral |
| `blackjack` | Fixed-dealer no-wager Blackjack | 52 | 52 `symbols/` faces | Same standard 52 faces | As above |
| `knuckles` | Five-card low-score Knuckles | 52 | 52 `symbols/` faces | Same standard 52 faces | As above |

The logical Skip-Bo deck contains **three copies of each of the 48 colored
number faces** (144 cards), plus **18 Wild cards** distributed across the four
existing Wild artworks (5+5+4+4). These are **distinct digital instances**
identified with a `~copy` suffix, not claims of separate printed artwork.
The underlying color is visual decoration and never affects Skip-Bo rules.
Each card is accounted for exactly once across stocks, hands, personal
discards, shared builds, completed piles and draw reserve.

**Artwork coverage is assessed per game**. The `symbols/` folder still lacks
faces for a hypothetical *Four-Color-equivalent* variant, but its standard
52-card subset is complete. The additional games do not change Four-Color's
canonical 119-face deck or Fourfold Mandate's deck.

## Skip-Bo

- 2–6 players; 30-card stockpile per player for 2–4 players, or 20 for 5–6.
- Each turn starts/refills to five hand cards. Build four shared sequences
  upward from 1 to 12, using the **top stock card**, any own hand card, or
  **top** of any of four own discard piles. A Wild stands for the needed rank.
- Completing a 12 returns all 12 cards to a completed-pile reserve that may
  be shuffled into the draw pile when necessary.
- Playing one's last stock card wins immediately. Discarding a hand card to
  one personal discard pile ends a turn; clearing the hand while building
  refills it without ending the turn.
- The `pass` action is enabled only when no build/discard is legal (e.g.,
  after draw exhaustion). The engine records a terminal draw if no cards can
  be drawn or used to keep the match progressing.

Rule reference: [Mattel Skip-Bo instruction sheet](https://service.mattel.com/instruction_sheets/42050-Skip-Bo.pdf).
The logical quantity follows the standard deck; original Card Games artwork
is reused. Skip-Bo is a trademark of Mattel; this repository is not
represented as an official licensed digital adaptation.

## Blackjack

- 2–6 human/AI seats, each against one software-controlled **dealer**.
- A=1 or 11, face cards=10, numbers at face value. Each seat starts with two
  cards. The dealer has one visible upcard and one concealed card until result.
- Players choose **Hit** or **Stand**, in seat order. Reaching 21 or busting
  automatically completes the player's decisions.
- Dealer hits below 17 and stands on hard **and soft 17**. An unbusted score
  higher than the dealer wins; a dealer bust wins for every unbusted player;
  a natural two-card 21 beats a non-natural 21, but not a dealer natural.
- Equal results (push) are not counted as wins. Multiple players may win the
  same round. There are **no stakes, bets, doubling, splitting, surrender,
  insurance, or multi-round bankroll** in this profile.

Reference: [Bicycle Cards Blackjack rules](https://bicyclecards.com/how-to-play/blackjack/).
This is a deliberate simpler local rules profile, not full casino Blackjack.

## Competitive 21 — an explicitly defined house variant

- 2–6 players, **no dealer**; normal A=1/11, face=10 values.
- Each player receives two cards, then chooses Hit or Stand. Busts are out.
- After all players finish, the highest non-busting total wins; exact ties
  share the win. If all players bust, the round is a draw.
- Wagers, splits and any additional scoring are not implemented.

**Rule approval outstanding:** “21” is often another name for Blackjack.
This *competitive/no-dealer* distinction is a transparent design choice to
give the separately requested game its own mechanic. The user may choose to
replace it with an approved distinct Twenty-One specification later.

## Knuckles — five-card low-score rules profile

- 2–6 players, five cards each. A=1, J=0, Q/K=10; others at printed value.
- Draw from the stock or pick up the top discard, then discard one card,
  keeping a five-card hand.
- Instead of drawing, **Knock** announces the end of the round. Each other
  player receives one final turn, then lowest card-sum wins. Ties share a win.
- Exhausting the draw pile ends the round and scores the hands.
- No physical knuckle-rapping, punishments or alternate scoring features.

Illustrative rules reference:
[Family Game Shelf — Knuckles](https://familygameshelf.com/2024/02/20/how-to-play-the-card-game-knuckles/).
**Rule approval outstanding:** “Knuckles” has local variations; this
implementation is identified by its five-card low-score profile, not
presented as the definitive rules for every variant.

## Privacy, AI, storage and UX

- All four use the same local account, settings, match-save and HTTP service
  as Four-Color and Fourfold. Online room service **does not** register them.
- Hot-seat views reveal only the acting human's private hand. Skip-Bo's
  top stock cards and personal discard tops are public. Blackjack's dealer
  hole card and opponents' cards remain hidden until the result. On match
  completion, final scores/hands are visible where relevant.
- Every move must exactly match one server-computed legal action. Failed
  actions cannot alter persisted state; revisions block stale actions.
- SLAI's game-specialized BaseAgent receives sanitized observations and
  returns candidate actions. Different easy/medium/hard/expert policies
  affect choices; invalid, timed-out or absent agent results fall back to a
  deterministic legal policy. These are heuristics, **not proved-optimal AI**.
- Four-Color alone currently has animated AI plays, flipping a card from
  cover to its public face and building a four-card face-up discard fan.
  These new games currently update their public table immediately; their
  card movement animation is a future presentation enhancement.

## Verification and limitations

Run `python -m unittest discover -s tests -q` with the SLAI root on
`PYTHONPATH`, plus `node tests/test_handoff.cjs` and `node --check
src/client/app.js`. Tests cover deck integrity, simulated completed games,
authorized views, legal actions, settings and HTTP recovery.

This is a **local rules/gameplay implementation**, not a license to distribute
third-party card-game artwork or an independently security-certified service.
Browser visual QA, play balance, accessible keyboard journeys, and approval
of the Competitive 21 / Knuckles profiles remain open checks.
