"""Assemble the static website (GitHub Pages) in ``outputs/site`` (Tasks P8.3).

- pages, style and scripts from ``site/`` (landing page, "find places like A");
- the tool's data (``python -m src.viz.web_data``; re-exported with ``--data``, or if missing);
- the interactive map ``outputs/map.html``, the report and slides PDFs (compile them first),
  and the figures shown on the landing page.

Run: python scripts/build_site.py [--data]
Preview: python -m http.server -d outputs/site   (the tool fetches its data, so file:// fails)
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from src.config import load_config
from src.viz import web_data

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ["map_suitability_classes.png", "chart_roc.png"]


def build(cfg, data: bool = False) -> Path:
    outputs = Path(cfg.paths["outputs"])
    out = outputs / "site"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "site", out, dirs_exist_ok=True)
    if data or not (out / "data" / "meta.json").exists():
        web_data.export(cfg, out / "data")
    files = {
        "map.html": outputs / "map.html",
        "report.pdf": ROOT / "report" / "final" / "report.pdf",
        "slides.pdf": ROOT / "report" / "final_slides" / "slides.pdf",
        **{f"img/{f}": outputs / "figures" / f for f in FIGURES},
    }
    missing = [str(src) for src in files.values() if not src.exists()]
    if missing:
        sys.exit(
            "missing (run the pipeline / compile the report first):\n  " + "\n  ".join(missing)
        )
    (out / "img").mkdir(exist_ok=True)
    for dst, src in files.items():
        shutil.copy2(src, out / dst)
    (out / ".nojekyll").touch()
    print(f"site built in {out}")
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", action="store_true", help="re-export the tool's data")
    args = parser.parse_args(argv)
    build(load_config(), data=args.data)


if __name__ == "__main__":
    main()
