# Card Games

A local-first desktop-style launcher for original card games, powered by SLAI's shared application toolkit.

**Status: six registered playable games (five rules engines, including two 21 profiles), local account/profile support and a separate self-hosted online room service for Four-Color and Fourfold. Not independently production-certified.**

## Currently available

- Four-Color v1.0 prototype: 119-face color deck, 2–8 seats, documented action rules, turn validation, draw/recycle, one-card turns, pending selections, last-card challenge, winner detection.
- **Fourfold Mandate First Edition v1.0**: 2–6 players, 56 cards per player, 12 rounds of simultaneously committed orders, exact-match targets, CP/Treasury economics, Foundations, Jack/Queen/King abilities, estate contests, seals, era rewards, set bonuses and tie breakers. See [Fourfold rules and artwork register](doc/FOURFOLD.md).
- **Skip-Bo**: 2–6 players, a 162-instance logical deck reusing 52 original `colors/` face designs (1–12 and Wild); build four 1–12 sequences and be first to empty your stockpile.
- **Competitive 21**: 2–6-player explicitly labeled *house variant*, without a dealer, played on the standard 52 suited faces.
- **Blackjack**: 2–6 human/AI players against a fixed dealer; hit, stand, natural Blackjack, dealer stands on all 17s. No wagering/splits/doubles.
- **Five-card Knuckles**: 2–6 players, five-card lowest-score game, draw/discard or knock; no physical forfeit mechanics.
- All new games are **local/hot-seat/AI only**; the separate online room service currently supports Four-Color and Fourfold. See [rules, card subsets and limits](doc/GAME_VARIANTS.md).
- Local human and AI seats, including mixed matches and hot-seat privacy screens.
- Compact, in-table hot-seat handoffs with card-flip/reveal animations. Solo-human matches against SLAI opponents continue without a pointless pass-the-device prompt. Motion honors both the SLAI preference and OS reduced-motion settings.
- Visual Steal card selection, explicit current/next-player status, and Four-Color SLAI card-play animations that flip from cover **to the revealed face** and land on a four-card, face-up fanned discard stack (with a reduced-motion fallback). Original `+1`/`+2`/`+4`/`+5` card art is served through a whitelist-validated compatibility route because the shared static toolkit rejects `+` filenames.
- Browser launcher, game cards, setup, table, settings, recent matches and history.
- SQLite match recovery and preferences through `applications.tools.database.Database`.
- SLAI's hardened loopback server and shared CSS (`applications/tools`).
- Account registration/login with SLAI AuthService, refresh-token rotation, logout, editable profile display names/avatars and guest play. Full auth requires SLAI's optional auth dependencies.
- SLAI `BaseAgent` specialization for both games. Structured decisions are revalidated by the rules engine, bounded by a decision timeout, with diagnostics for any fallback.
- Optional separately hosted network room service for human players: one-use invitations, per-seat secret tokens, server-controlled actions, idempotent revisions, reconnection and remote table polling.

## Requirements

- Python 3.12+
- A local checkout of [SLAI v2.4](https://github.com/The-Outsider-97/SLAI) with `applications/tools/` present.
- A recent browser with ES modules.
- Original artwork in `cards/colors/`, `cards/symbols/` and `cards/fourfold/`.

The client uses native browser ES modules; no npm compilation step is required for this prototype.

## Windows / PowerShell startup

From an independent Card Games checkout:

```powershell
cd G:\GAIA\AI\card_games
python -m slai --slai-root G:\GAIA\AI\SLAI --port 8774
```

If installed as `SLAI/applications/card_games/`, from the SLAI checkout root:

```powershell
python -m applications.card_games --port 8774
```

The launcher prints a one-time URL; open it to establish the local session cookie. The server refuses non-loopback network interfaces. Do not expose it directly to the internet.

### Online rooms

Run the **separate** network room service; never expose the privileged SLAI loopback server. For testing locally:

```powershell
cd G:\GAIA\AI\card_games
python -m slai.online --host 127.0.0.1 --port 8775 --data .\rooms.sqlite3 --allowed-origin http://127.0.0.1:8774
```

Launch the regular Card Games app and choose **Online rooms**, then create or join using a one-time invitation. The host generates the invitation for each seat. Room participants use seat-specific bearer capabilities, not their SLAI local access cookie. The exact browser origin must match `--allowed-origin`.

For internet-hosted rooms, configure a real hostname, `--tls-cert` and `--tls-key`; a non-loopback listener **refuses to start without TLS**. Provision firewalls, DNS, backups, certificate renewal, monitoring and user-facing service policies before public deployment. This is a self-hosted room service, not a hosted global matchmaking service or a cloud account provider.

Other options: `--no-browser`, `--data-dir`, `--host` (loopback only), `--token` (tests only).

## Tests

```powershell
cd G:\GAIA\AI\card_games
python -m unittest discover -s tests -v
node tests/test_handoff.cjs
```

For tests of the actual shared SLAI HTTP toolkit, add the SLAI checkout root to `PYTHONPATH` (or run from a development environment where `applications.tools` is importable). Tests without it will skip the shared-server integration module.

AI benchmark (controlled scripted matches, not a scientific human balance study):

```powershell
$env:PYTHONPATH='G:\GAIA\AI\SLAI'
python -m utils.benchmark_ai --game fourfold --games 20 --seed 41
python -m utils.benchmark_ai --game four-color --games 20 --seed 7
```

## Project boundaries

| Path | Responsibility |
| --- | --- |
| `app/game.py` | Authoritative Four-Color rules and serializable match state |
| `app/fourfold.py` | Independent authoritative Fourfold v1.0 round resolver |
| `app/variants.py` | Skip-Bo, competitive 21, dealer Blackjack and Knuckles authoritative local engines |
| `app/service.py` | SQLite persistence, sessions, preferences, registry and account adapter |
| `slai/app.py` | Shared SLAI loopback HTTP host and routes |
| `slai/bridge/agents.py` | Optional structured SLAI card decision adapter and legal fallback |
| `slai/online.py` | Independent network room authority; TLS-required remote access |
| `src/client/` | Launcher and interactive web client |
| `cards/` | Original card art collections; no game mechanics inferred from images |

The launcher registers **six games** as playable. The three standard-suit games use a validated 52-face **subset** of `symbols/`; the hypothetical *Four-Color with symbols* variant remains unavailable pending missing faces and an approved mapping. Card artwork and game registration remain independent.

## Prototype rules and known limitations

- Four-Color mechanics are based on `four_color_card_game_rules_v1_0.pdf` supplied with the development request. See [rules decision register](doc/FOUR_COLOR.md).
- The PDF's Cycle rule is **proposed, not approved**. This prototype currently implements that proposed rotation literally; physical-production approval and playtesting are still required.
- `cards/symbols/` is 15 faces short of a canonical Four-Color-equivalent 119-face deck: four Reverse and eleven neutral actions. No suit-to-color correspondence or distinct rules have been approved. See [reconciliation](doc/FOUR_COLOR.md).
- The registered Skip-Bo deck uses 162 **logical card instances** but only 52 source artworks. Its colors are decorative; it does not use `+` action cards or the other 67 color-collection faces. The 21 and Knuckles implementations have explicitly documented local-rule assumptions rather than claiming these are approved proprietary rules.
- Four-Color's public AI flip and discard-fan animations have headless DOM regression coverage; genuine browser-based visual inspection remains outstanding. Additional games use immediate authoritative table updates, not the Four-Color discard animation.
- `cards/fourfold/` has duplicate Spades King naming and lacks a King of Hearts image. The digital game uses the logical 56-card deck independently of artwork and shows a labeled missing-image placeholder.
- Live SLAI BaseAgent specialization and timed calls were exercised against the SLAI v2.4 checkout. Benchmarks compare scripted policies over controlled matches; no claims of optimal strategy or human play balance are made.
- The online room service uses explicit invitations and authenticated seat tokens but has **no global identity provider**, ranked matchmaking, spectators, or deployed cloud hosting. Browser clients poll rather than maintain a WebSocket.
- Guest and hot-seat modes assume trusted users of one device. Hand-hiding screens are a privacy courtesy, not a security boundary between hostile local users.
- Account login depends on the full SLAI auth subsystem and its optional dependencies (in the verification container, `phonenumbers` was unavailable). The UI offers signup, login, refresh, logout and profile editing. Email verification and credential recovery remain SLAI-auth deployment concerns; password changes are not exposed until the shared auth service provides a supported API.
- Client uses plain JavaScript rather than compiled strict TypeScript. Rich animations and independent visual browser end-to-end QA remain incomplete; this verification environment's browser cannot reach its isolated local test server.

No balance or production-readiness claim is made without empirical playtests, security verification, and more extensive integration testing.

See the [security and release-verification register](doc/SECURITY.md) for verified protections and the remaining release blockers.
