"""Run with ``python -m applications.card_games`` inside an SLAI checkout."""

import sys
from pathlib import Path

repo_root = str(Path(__file__).resolve().parent)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from .slai.app import main

if __name__ == "__main__":
    raise SystemExit(main())
