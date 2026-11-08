"""Reusable collection inventory; artwork is not a game or rules definition."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .game import CARDS
from .fourfold import DECK, SUITS
from .variants import SKIP_DECK, STANDARD_DECK, face


class AssetRegistry:
    COLLECTIONS = ("colors", "symbols", "fourfold")

    def __init__(self, root: Path):
        self.root = Path(root)

    def files(self, collection: str) -> dict[str, Path]:
        if collection not in self.COLLECTIONS:
            raise ValueError("Unrecognized asset collection")
        folder = self.root / collection
        if not folder.is_dir():
            return {}
        return {path.stem: path for path in sorted(folder.iterdir())
                if path.is_file() and path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")}

    def inspect(self, collection: str) -> dict[str, Any]:
        actual = self.files(collection)
        missing: list[str] = []
        duplicates: list[list[str]] = []
        game_subsets: dict[str, dict[str, Any]] = {}
        if collection == "colors":
            missing = sorted(set(CARDS) - set(actual))
            subset_missing = sorted({face(card) for card in SKIP_DECK} - set(actual))
            game_subsets["skip-bo"] = {"faces": len({face(card) for card in SKIP_DECK}),
                                        "instances": len(SKIP_DECK), "missing": subset_missing,
                                        "ready": not subset_missing and "cover" in actual}
        elif collection == "symbols":
            subset_missing = sorted(set(STANDARD_DECK) - set(actual))
            for game in ("21", "blackjack", "knuckles"):
                game_subsets[game] = {"faces": len(STANDARD_DECK), "instances": len(STANDARD_DECK),
                                      "missing": subset_missing, "ready": not subset_missing and "cover" in actual}
            # A complete *equivalent* Four-Color variant needs every colored
            # face plus the 11 neutral actions. No suit/color meaning is assigned.
            expected = {f"{key}-{suit}" for suit in SUITS for key in
                        (f"{n:02d}" for n in range(14))}
            expected |= {f"{name}-{suit}" for suit in SUITS for name in
                         ("A", "J", "Q", "K", "+1", "+2", "+4", "+5", "cycle", "reverse", "skip", "stop", "Wild")}
            missing = sorted(expected - set(actual))
            # Neutral actions have no approved suit-based representation.
            missing += sorted(f"{action}-neutral" for action in
                              ("+2", "+4", "cycle", "reverse", "skip", "stop", "Wild", "equality", "verdict", "swap", "steal"))
        elif collection == "fourfold":
            # Normalize historic plural/singular estate labels, not rules.
            normalized: dict[str, list[str]] = {}
            for name in actual:
                if name == "cover":
                    continue
                key = name.lower().replace(" (2)", "")
                if key.endswith("-heart") or key.endswith("-spade"):
                    key += "s"
                normalized.setdefault(key, []).append(name)
            duplicates = [entries for entries in normalized.values() if len(entries) > 1]
            missing = sorted(set(DECK) - set(normalized))
        return {"collection": collection, "files": len(actual), "faces": len(actual) - int("cover" in actual),
                "missing": missing, "duplicate_labels": duplicates, "cover": "cover" in actual,
                "game_subsets": game_subsets,
                "status": "complete" if not missing and not duplicates and "cover" in actual else "needs-review",
                "note": ("Neutral actions and Reverse art are missing; a suit-to-color semantics mapping is not approved."
                         if collection == "symbols" else
                         "Use a labeled placeholder for missing images; never fabricate a card face."
                         if collection == "fourfold" else "")}

    def report(self) -> list[dict[str, Any]]:
        return [self.inspect(collection) for collection in self.COLLECTIONS]
