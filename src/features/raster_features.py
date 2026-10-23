"""Raster features per cell (contract C2) and the grid (C1) (PRD FR-4.2, FR-4.3).

For each year in ``features_years(cfg)`` (baseline and latest):

- own-cell ESRI class fractions ``frac_*`` + ``nodata_frac`` (clustering only, D4);
- ring fractions ``ring{250,500}_{class}`` excluding the centre cell;
- terrain ``elev_mean``, ``slope_mean``, ``slope_max`` (static, from the DEM);
- ``log_dist_built``: log1p of the distance (m) from the cell centre to the nearest
  built pixel **outside the cell**; ``log_dist_water``: to the nearest water pixel.
  Distances are capped at ``features.distance_cap_m``.

Rings and distances use the whole reference grid (AOI + buffer), so cells at the AOI
edge see their real surroundings.

Run: python -m src.features.raster_features
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import rasterio

from src.config import load_config
from src.features import schema
from src.features.context import ring_mean
from src.features.grid import aoi_cell_mask, cell_ids, lattice, write_grid
from src.features.lulc_features import ESRI_CODE, block_max, block_mean, class_fractions
from src.features.proximity import dist_to_class, dist_to_class_outside_cell
from src.io_utils import setup_logging
from src.preprocess.raster import PIXEL_M, processed_dir

log = logging.getLogger(__name__)


def features_years(cfg) -> list[int]:
    """Years with a feature table: baseline and latest."""
    y = cfg["years"]
    return sorted({int(y["baseline"]), int(y["latest"])})


def check_distance_cap(cfg) -> float:
    """The distance cap, after checking it does not exceed the buffer.

    Distances are computed inside the reference grid (AOI + buffer). A cell at the AOI
    edge can only see ``aoi.buffer_m`` beyond it, so any distance above the buffer
    could be too large there. Capping at most at the buffer keeps every distance exact.
    """
    cap = float(cfg["features"]["distance_cap_m"])
    buffer_m = float(cfg["aoi"]["buffer_m"])
    if cap > buffer_m:
        raise ValueError(
            f"features.distance_cap_m ({cap:.0f}) > aoi.buffer_m ({buffer_m:.0f}): distances near "
            "the AOI edge would be wrong. Raise the buffer or lower the cap."
        )
    return cap


def _read(path) -> np.ndarray:
    with rasterio.open(path) as ds:
        return ds.read(1)


def terrain_features(cfg, k: int) -> dict[str, np.ndarray]:
    """Mean elevation, mean and maximum slope per cell."""
    elev = _read(processed_dir(cfg) / "elevation.tif").astype("float64")
    slope = _read(processed_dir(cfg) / "slope.tif").astype("float64")
    return {
        "elev_mean": block_mean(elev, k),
        "slope_mean": block_mean(slope, k),
        "slope_max": block_max(slope, k),
    }


def raster_features(cfg, year: int, terrain: dict[str, np.ndarray] | None = None) -> pd.DataFrame:
    """C2 for one year: one row per grid cell (centre inside the AOI)."""
    lat = lattice(cfg)
    k = lat.px_per_cell
    lulc = _read(processed_dir(cfg) / f"lulc_esri_{year}.tif")
    if lulc.shape != (lat.shape[0] * k, lat.shape[1] * k):
        raise ValueError(
            f"lulc_esri_{year}.tif shape {lulc.shape} does not match the lattice {lat.shape}"
        )

    cells: dict[str, np.ndarray] = class_fractions(lulc, k)
    for radius in schema.RING_RADII_M:
        for cls in schema.RING_CLASSES:
            cells[f"ring{radius}_{cls}"] = np.clip(
                ring_mean(cells[f"frac_{cls}"], radius, lat.cell_m), 0, 1
            )
    cells.update(terrain if terrain is not None else terrain_features(cfg, k))

    keep = aoi_cell_mask(cfg, lat)
    rows, cols = np.nonzero(keep)
    df = pd.DataFrame({"cell_id": cell_ids(lat)[rows, cols]})
    for name, arr in cells.items():
        df[name] = arr[rows, cols]

    cap = check_distance_cap(cfg)
    left, top = lat.left, lat.top
    d_built = dist_to_class_outside_cell(
        lulc == ESRI_CODE["built"], left, top, PIXEL_M, lat.cell_m, rows, cols, cap
    )
    x, y = lat.centres()
    d_water = dist_to_class(
        lulc == ESRI_CODE["water"], left, top, PIXEL_M, x[rows, cols], y[rows, cols], cap
    )
    df["log_dist_built"] = np.log1p(d_built)
    df["log_dist_water"] = np.log1p(d_water)

    df = df[["cell_id", *[c for c in schema.CONTRACTS["C2"].columns if c != "cell_id"]]]
    schema.validate_frame(df, "C2")
    return df


def write_raster_features(cfg) -> dict[int, pd.DataFrame]:
    """Write C1 (grid) and C2 for every feature year."""
    grid = write_grid(cfg)
    log.info("grid: %d cells", len(grid))
    lat = lattice(cfg)
    terrain = terrain_features(cfg, lat.px_per_cell)
    out = {}
    for year in features_years(cfg):
        df = raster_features(cfg, year, terrain)
        if not df["cell_id"].equals(grid["cell_id"]):
            raise ValueError("C2 cells differ from the grid (C1)")
        path = schema.contract_path(cfg, "C2", year=year)
        df.to_parquet(path, index=False)
        log.info("wrote %s (%d cells, %d columns)", path.name, len(df), df.shape[1])
        out[year] = df
    return out


def main() -> None:
    cfg = load_config()
    setup_logging(cfg, "features")
    write_raster_features(cfg)


if __name__ == "__main__":
    main()
