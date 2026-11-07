# Card Games

A local-first desktop-style launcher for original card games, powered by SLAI's shared application toolkit.

**Status: working Four-Color prototype; not a complete production release.** The shared card registry, account integration, online play and other games need further work (see limitations).

## Currently available

- Four-Color v1.0 prototype: 119-face color deck, 2–8 seats, documented action rules, turn validation, draw/recycle, one-card turns, pending selections, last-card challenge, winner detection.
- Local human and AI seats, including mixed matches and hot-seat privacy screens.
- Browser launcher, game cards, setup, table, settings, recent matches and history.
- SQLite match recovery and preferences through `applications.tools.database.Database`.
- SLAI's hardened loopback server and shared CSS (`applications/tools`).
- Account registration and login **when** `src.functions.auth.AuthService` is available; guest play works without it.
- Optional SLAI Planning Agent adapter. If it cannot provide a compatible structured card move, the game explicitly uses a legal heuristic fallback; that fallback is **not** an SLAI decision.

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

Other options: `--no-browser`, `--data-dir`, `--host` (loopback only), `--token` (tests only).

## Tests

```powershell
cd G:\GAIA\AI\card_games
python -m unittest discover -s tests -v
```

For tests of the actual shared SLAI HTTP toolkit, add the SLAI checkout root to `PYTHONPATH` (or run from a development environment where `applications.tools` is importable). Tests without it will skip the shared-server integration module.

## Project boundaries

| Path | Responsibility |
| --- | --- |
| `app/game.py` | Authoritative Four-Color rules and serializable match state |
| `app/service.py` | SQLite persistence, sessions, preferences and account adapter |
| `slai/app.py` | Shared SLAI loopback HTTP host and routes |
| `slai/bridge/agents.py` | Optional structured SLAI card decision adapter and legal fallback |
| `src/client/` | Launcher and interactive web client |
| `cards/` | Original card art collections; no game mechanics inferred from images |

The current launcher registers Four-Color as playable. Fourfold and the symbols variant are shown as rules pending.

## Prototype rules and known limitations

- Four-Color mechanics are based on `four_color_card_game_rules_v1_0.pdf` supplied with the development request. See [rules decision register](doc/FOUR_COLOR.md).
- The PDF's Cycle rule is **proposed, not approved**. This prototype currently implements that proposed rotation literally; physical-production approval and playtesting are still required.
- `cards/symbols/` has a different inventory, including no neutral cards or Reverse art. It is **not** silently treated as a complete interchangeable 119-card deck.
- `cards/fourfold/` has potentially inconsistent filenames and no authoritative playable rules in the repository. Fourfold is not advertised as playable.
- The AI bridge can fall back to simple deterministic legal choices. Full SLAI agent decision integration, strategic skill calibration, and performance evaluation remain open.
- Online multiplayer, remote accounts and live synchronization are not implemented. The server is local-only.
- Guest and hot-seat modes assume trusted users of one device. Hand-hiding screens are a privacy courtesy, not a security boundary between hostile local users.
- Account login depends on the full SLAI auth subsystem and its configuration. Account refresh/verification UI and profile editing are not yet complete.
- Client uses plain JavaScript rather than compiled strict TypeScript, and rich animations and visual end-to-end browser testing are incomplete.

No balance or production-readiness claim is made without empirical playtests, security verification, and more extensive integration testing.
