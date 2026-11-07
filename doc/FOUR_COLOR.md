# Four-Color v1.0 rules decision register

Source: user-supplied `four_color_card_game_rules_v1_0.pdf`, prototype edition of 23 October 2026.

| Area | Status | Digital implementation |
| --- | --- | --- |
| 2–8 players, seven cards, normal match/draw | Provisional prototype | Implemented |
| 119 distinct color-face designs | Design inventory, not independently validated physical copies | One instance per definition; images verified at runtime |
| No stacking, draw one | Provisional | Implemented |
| Last card wins before resolving its action | Explicit prototype editorial decision | Implemented |
| Neutral color and Wild number declaration | Provisional | Implemented |
| Equality, Verdict, Swap, Steal | Confirmed concepts, procedural details provisional | Implemented using PDF procedures |
| Stop restriction | Recommended | Implemented |
| Cycle simultaneous one-card pass | **Proposed; approval pending** | Implemented as a provisional prototype rule, not claimed official |
| Optional same-value stacking | House rule, excluded from standard | Not enabled |
| Score, points and long-term rankings | Not defined | No invented scoring scheme |
| Color-to-suit presentation mapping | Not specified | Not enabled |

## Core decisions

- All card actions are handled by one rules engine. Actions are illegal outside the current player's turn except a valid LAST CARD challenge or an active simultaneous card-selection phase.
- The turn direction is used for neighbor resolution and immediate targeting. Verdict missed slots are consumed on scheduled visits and refreshed to two, not stacked.
- Equality requires surplus players to select returns first; those cards go to the bottom of the draw pile before shortages are drawn.
- Steal may take the previous top card once Steal has been played, but never Steal itself.
- Save files carry the rules version; incompatible versions are refused rather than silently migrated.

## Approval and playtest backlog

1. Approve or reject Cycle as the standard physical rule.
2. Confirm printed copy counts and therefore official deck composition.
3. Confirm neutral excess-card placement and the end-of-turn challenge interpretation in exceptional multi-step actions.
4. Supply an authoritative symbols-based rules/deck manifest where it differs from the 119-card color deck.
5. Conduct the PDF's proposed 12+ structured playtests (2, 3, 4, and 6–8 players), recording duration, action rate, forced draws, and perceived balance.

## Symbols deck reconciliation (7 November 2026)

The `cards/symbols/` family is reusable art, **not a game**. The verified inventory has 104 playable face images plus the cover: four suits, 0–13, A/J/Q/K, +1/+2/+4/+5, Cycle, Skip, Stop and Wild. There are no Reverse faces and no neutral faces. A canonical Four-Color-equivalent deck would require four missing Reverse faces and eleven neutral action faces (+2, +4, Cycle, Reverse, Skip, Stop, Wild, Equality, Verdict, Swap, Steal), and a designer-approved correspondence between suits and colors.

The registry exposes this exact fifteen-face deficit and the pending semantics. No silently altered 104-card ruleset is registered as playable; both the mapping and any intentionally different symbols-game rules need approval before enabling a symbols variant. Original images are retained.

These are outstanding product decisions, not completed empirical validations.
