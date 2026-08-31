"""Capture the current desktop workbench for README visual QA."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from damage_gui.gui.main_window import DamagePredictionGUI, create_root  # noqa: E402


def capture(app: DamagePredictionGUI, root, output: Path) -> None:
    root.deiconify()
    root.state("normal")
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()
    root.update_idletasks()
    root.update()
    time.sleep(0.25)
    root.update_idletasks()
    root.update()
    x1, y1 = root.winfo_rootx(), root.winfo_rooty()
    x2, y2 = x1 + root.winfo_width(), y1 + root.winfo_height()
    ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True).save(output)


def main() -> None:
    output_dir = ROOT / "examples" / "screenshots"
    output_dir.mkdir(parents=True, exist_ok=True)
    root = create_root()
    app = DamagePredictionGUI(root)
    root.withdraw()
    root.after(300, lambda: None)
    root.update()
    capture(app, root, output_dir / "gui.png")
    app._set_language("en")
    capture(app, root, output_dir / "gui_en.png")
    root.attributes("-topmost", False)
    root.destroy()


if __name__ == "__main__":
    main()
