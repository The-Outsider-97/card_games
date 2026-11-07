import tempfile
import unittest
from pathlib import Path

from app.assets import AssetRegistry


class AssetRegistryTests(unittest.TestCase):
    def test_missing_and_duplicate_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("colors", "symbols", "fourfold"):
                (root / name).mkdir()
            for file in ("cover.jpg", "king-spade.jpg", "king-spade (2).jpg", "queen-heart.jpg"):
                (root / "fourfold" / file).touch()
            report = AssetRegistry(root).report()
            self.assertIn("00-blue", report[0]["missing"])
            self.assertEqual(report[0]["status"], "needs-review")
            self.assertEqual(report[1]["faces"], 0)
            self.assertIn("king-hearts", report[2]["missing"])
            self.assertIn(["king-spade (2)", "king-spade"], report[2]["duplicate_labels"])


if __name__ == "__main__":
    unittest.main()
