"""Reusable collection inventory; artwork is not a game or rules definition."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .game import CARDS


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
        if collection == "colors":
            missing = sorted(set(CARDS) - set(actual))
        elif collection == "fourfold":
            # Fourfold's actual rules are unspecified. Only check the observed art-family naming.
            normalized: dict[str, list[str]] = {}
            for name in actual:
                if name == "cover":
                    continue
                key = name.lower().replace(" (2)", "").replace("-heart", "-hearts").replace("-spade", "-spades")
                normalized.setdefault(key, []).append(name)
            duplicates = [entries for entries in normalized.values() if len(entries) > 1]
            missing = ["king-hearts"] if "king-hearts" not in normalized else []
        return {"collection": collection, "files": len(actual), "faces": len(actual) - int("cover" in actual),
                "missing": missing, "duplicate_labels": duplicates, "cover": "cover" in actual,
                "status": "complete" if not missing and not duplicates and "cover" in actual else "needs-review"}

    def report(self) -> list[dict[str, Any]]:
        return [self.inspect(collection) for collection in self.COLLECTIONS]
