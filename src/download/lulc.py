"""Download LULC rasters for the AOI + buffer (PRD FR-2.1, FR-2.2; decision D2).

- ESRI IO LULC v02 (``io-lulc-annual-v02``), 10 m, every year from ``years.baseline``
  to ``years.latest``: the source for features and growth labels.
- ESA WorldCover (``esa-worldcover``), 10 m, ``lulc.worldcover_check``: cross-check only.

Run: python -m src.download.lulc [--force]
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from rasterio.enums import Resampling

from src.config import load_config
from src.download.stac import fetch_raster
from src.io_utils import Manifest, setup_logging

log = logging.getLogger(__name__)

ESRI_COLLECTION = "io-lulc-annual-v02"
WORLDCOVER_COLLECTION = "esa-worldcover"


def esri_path(cfg, year: int) -> Path:
    return Path(cfg.paths["data_raw"]) / "lulc" / f"esri_lulc_{year}.tif"


def worldcover_path(cfg, year: int) -> Path:
    return Path(cfg.paths["data_raw"]) / "lulc" / f"worldcover_{year}.tif"


def esri_years(cfg) -> list[int]:
    """ESRI LULC years to download (baseline to latest)."""
    y = cfg["years"]
    return list(range(int(y["baseline"]), int(y["latest"]) + 1))


def download_esri_lulc(cfg, years: list[int] | None = None, force: bool = False) -> list[Path]:
    """ESRI IO LULC v02 for each year (nearest-neighbour; classes stay untouched)."""
    manifest = Manifest.for_config(cfg)
    out = []
    for year in years or esri_years(cfg):
        out.append(
            fetch_raster(
                cfg,
                collection=ESRI_COLLECTION,
                asset="data",
                out=esri_path(cfg, year),
                dataset="esri-io-lulc-v02",
                resampling=Resampling.nearest,
                datetime=str(year),
                # one annual map per tile; the datetime filter can also match the
                # neighbouring year at the boundary, so keep only ids ending in -<year>
                item_filter=lambda i, y=year: i.id.endswith(f"-{y}"),
                year=year,
                nodata=0,
                force=force,
                manifest=manifest,
            )
        )
    return out


def download_worldcover(cfg, year: int | None = None, force: bool = False) -> Path:
    """ESA WorldCover map for ``year`` (default ``lulc.worldcover_check``)."""
    year = int(year or cfg["lulc"]["worldcover_check"])
    return fetch_raster(
        cfg,
        collection=WORLDCOVER_COLLECTION,
        asset="map",
        out=worldcover_path(cfg, year),
        dataset="esa-worldcover",
        resampling=Resampling.nearest,
        datetime=str(year),
        item_filter=lambda i, y=year: f"_{y}_" in i.id,
        year=year,
        nodata=0,
        force=force,
        manifest=Manifest.for_config(cfg),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="download even if files exist")
    args = parser.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "download")
    download_esri_lulc(cfg, force=args.force)
    download_worldcover(cfg, force=args.force)


if __name__ == "__main__":
    main()
