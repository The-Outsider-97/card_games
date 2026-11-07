"""Reproducible bounded smoke benchmarks (not a proof of strategy quality).

Example: python -m utils.benchmark_ai --game fourfold --games 10 --seed 41
Use the full SLAI installation in PYTHONPATH to measure the real agent bridge.
"""

from __future__ import annotations

import argparse
import json
from statistics import median
from time import perf_counter

from app.fourfold import FourfoldMatch
from app.game import Match
from slai.bridge.agents import CardAgentBridge


def benchmark(game: str, games: int, seed: int) -> dict:
    if game not in ("four-color", "fourfold") or not 1 <= games <= 500:
        raise ValueError("Select one game and between 1 and 500 matches")
    bridge = CardAgentBridge()
    bridge._ensure_agent()
    results = {}
    for opponent_level in ("medium", "hard", "expert"):
        wins = {"easy": 0, opponent_level: 0, "tie": 0, "unfinished": 0}
        latencies = []
        decisions = 0
        for iteration in range(games):
            # Rotate seats to make first-player effects visible in comparisons.
            levels = ("easy", opponent_level) if iteration % 2 == 0 else (opponent_level, "easy")
            cls = FourfoldMatch if game == "fourfold" else Match
            match = cls.new([{"id": "a", "kind": "ai"}, {"id": "b", "kind": "ai"}], seed=seed + iteration)
            for _ in range(5000):
                complete = match.state["phase"] == "complete" if game == "fourfold" else match.state["winner"] is not None
                if complete:
                    break
                if game == "fourfold":
                    current = next(p for p in match.state["players"] if p["orders"] is None)
                else:
                    outstanding = match.outstanding_choices()
                    current = next(p for p in match.state["players"] if p["id"] == outstanding[0]["player"]) if outstanding else match.state["players"][match.state["current"]]
                bridge.difficulty = levels[match.state["players"].index(current)]
                start = perf_counter()
                if game == "fourfold":
                    command, args = "submit", {"orders": bridge.fourfold_orders(match, current["id"])}
                elif match.outstanding_choices():
                    command, args = "select", {"cards": bridge.selection(match, current["id"], match.outstanding_choices()[0]["count"])}
                else:
                    command, args = bridge.move(match, current["id"])
                match.act(current["id"], command, **args)
                latencies.append((perf_counter() - start) * 1000)
                decisions += 1
            else:
                wins["unfinished"] += 1
                continue
            if game == "fourfold":
                ids = match.state["winners"]
                winner_level = levels[[p["id"] for p in match.state["players"]].index(ids[0])] if len(ids) == 1 else "tie"
            else:
                winner_level = levels[[p["id"] for p in match.state["players"]].index(match.state["winner"])]
            wins[winner_level] += 1
        results[f"easy_vs_{opponent_level}"] = {"wins": wins, "decisions": decisions,
                                                 "median_decision_ms": round(median(latencies), 3) if latencies else None,
                                                 "max_decision_ms": round(max(latencies), 3) if latencies else None}
    return {"game": game, "matches_per_pair": games, "seed": seed,
            "agent_status": bridge.status, "agent_diagnostic": bridge.last_diagnostic,
            "comparisons": results,
            "interpretation": "Scripted smoke benchmark only; no optimality or human-play balance claim."}


def main():
    parser = argparse.ArgumentParser(description="SLAI card-opponent smoke benchmark")
    parser.add_argument("--game", choices=("four-color", "fourfold"), default="fourfold")
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--seed", type=int, default=41)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.game, args.games, args.seed), indent=2))


if __name__ == "__main__":
    main()
