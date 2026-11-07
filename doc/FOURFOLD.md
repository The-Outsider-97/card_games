
# Fourfold Mandate — First Edition v1.0

Source of truth: **`Fourfold_Mandate_v1.0_First_Edition.pdf`**, final edition dated 22 October 2026. The user supplied this finalized First Edition document in earlier project material; it supersedes provisional v0.1 simulations. The following is an implementation summary, not a replacement for the full 29-page rulebook.

## Authoritative game mechanics

- **2–6 players; twelve rounds; three eras of four rounds.** No shuffled cards, randomness, draws, elimination, or first-player priority. Each player independently owns all 56 suit/rank cards: Hearts, Diamonds, Clubs, Spades × 1–10, Ace, Jack, Queen, King.
- **Each round:** Prepare public suit targets → Plan privately → all ready / simultaneous reveal → contest resolution → rewards → close. Each player may commit 0–3 cards from distinct matching-suit estates for a total of at most **16 Command Points**; cards are spent permanently.
- **Targets:** Hearts [4,5,6,7,8,9,10,1,2,3,4,5]; Diamonds [6,7,8,9,10,1,2,3,4,5,6,7]; Clubs [8,9,10,1,2,3,4,5,6,7,8,9]; Spades [10,1,2,3,4,5,6,7,8,9,10,1]. An exact matching numeric rank gains +3 strength.
- **Card costs / strength:** numbers cost and strength = number; Ace costs target and strength = target+3; Jack 4/4 and names a rival whose claim loses 3; Queen 5/6, ignores Jack penalties and gets +2 once if an opposing Jack appears; King 8/8 and gets +2 if a rival had more seals in its estate before the round.
- **Treasury:** start 2; cap 8; each claim may spend 0–2 for +2 strength per Treasury; end-of-round unspent CP recovers up to 2 at one Treasury per 4 unused CP, after Diamonds reward. Rewards cannot finance orders in the same round.
- **Foundations:** one numeric card per era, only in its first two rounds, replaces a contest and occupies a distinct estate. Bonuses apply only from next round through era end: 1–4 gives +1, 5–8 gives +2, 9–10 gives +3.
- **Strength:** `max(0, base + exact + Treasury boost + applicable Foundation/face-card bonuses − Jack attacks)`; zero-strength claims cannot place. Ties resolve by fewer pre-round estate seals, fewer pre-round MP, and lower claim CP cost. Unresolved first-place ties give 1 consolation MP each and no seal or second place.
- **Rewards:** unique first +3 MP and a seal; next eligible rank +1 MP to each tied second-place claim. Hearts +1 MP if unboosted; Diamonds +2 Treasury; Clubs +1 MP if numeric exact or Ace; Spades +1 MP if the victory margin is at least 3 over an eligible runner-up; winning King +1 MP. After rounds 4, 8, 12: unique estate-seal leader of that era +2 MP.
- **Final:** after round 12 add 6 MP per complete four-suit seal set, plus floor(remaining Treasury / 3). Highest MP wins, then complete sets, total seals and Treasury; remaining ties share victory.
- **Invalid physical reveal:** penalty of up to 2 MP, forfeiture of the whole round's orders and CP recovery, and expenditure of legally owned revealed cards and declared available Treasury. The digital UI validates before locking, preventing illegal reveals; it does not expose this penalty as a voluntary move.

## Digital implementation

`app/fourfold.py` independently owns rules and snapshots; `app/service.py` stores versioned full private state; `src/client/app.js` provides a seat-private planning board; `slai/bridge/agents.py` requests structured SLAI decisions, then validates and legally falls back if unavailable. Online rooms use the same authoritative engine, returning only the requesting seat's private choices.

Authoritative worked round regression fixtures: two-player page 8 (Alpha 8 MP/1 Treasury, Beta 7 MP/3 Treasury) and four-player page 12 (MP 5/4/4/5, Treasury 2/2/4/2). Automated tests additionally cover CP and Treasury rejection, Foundations, secrecy, ties and the twelve-round finish.

## Asset reconciliation

The logical First Edition deck has **56 faces per player**. The repository has 56 file faces in `cards/fourfold`, but one of those is a duplicate naming candidate: `king-spade.jpg` and `king-spade (2).jpg`. **`king-hearts.jpg` is missing.** Historical art names `queen-heart.jpg`, `queen-spade.jpg`, and `king-spade.jpg` have explicit presentation aliases. A labeled in-app placeholder represents missing King of Hearts art; it is not a fabricated card. Do not rename or delete any existing artwork until its identity is confirmed by the designer.

## Limitations

- The published PDF's stated playtest times and earlier bot usage figures are not independent validation of human balance.
- Secret planning is protected per authenticated online seat, but trusted-device hot-seat concealment depends on handing over the screen honestly.
- Human visual testing on target Windows display sizes and full manual usability testing remain necessary.
