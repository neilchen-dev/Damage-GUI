"""Sign an independently verified legacy model without deserializing it.

Usage: DAMAGE_GUI_MODEL_KEY_FILE=/private/key python scripts/sign_model.py \\
    /trusted/model.joblib --approve-trusted-source
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.model.signing import sign_existing_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument(
        "--approve-trusted-source",
        action="store_true",
        required=True,
        help="Confirm the model came from an independently verified trusted source",
    )
    args = parser.parse_args()
    print(sign_existing_model(args.model))


if __name__ == "__main__":
    main()
