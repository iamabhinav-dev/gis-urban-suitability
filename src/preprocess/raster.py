"""Align every raster to one 10 m reference grid in the project CRS (PRD FR-3.1–3.3).

The reference grid covers the AOI + buffer. Its edges are multiples of the 100 m
cell size, so each 10 × 10 block of pixels is exactly one grid cell (A3.1).

- ESRI IO LULC: nearest. When the source already sits on the same 10 m lattice
  (the usual case), the values are copied unchanged.
- WorldCover: nearest (classes never mix).
- DEM: warped to UTM at its native 30 m, slope computed there (terrain.py),
  then both resampled bilinearly to the 10 m grid.

Outputs in ``data/processed/``: ``reference_grid.json``, ``lulc_esri_{year}.tif``,
``worldcover_{year}.tif``, ``elevation.tif``, ``slope.tif``.

Run: python -m src.preprocess.raster [--force]
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from pyproj import CRS
from rasterio.enums import Resampling
from rasterio.warp import reproject

from src.config import load_config
from src.download.dem import dem_path
from src.download.lulc import esri_path, esri_years, worldcover_path
from src.io_utils import setup_logging
from src.preprocess.terrain import slope_degrees

log = logging.getLogger(__name__)

PIXEL_M = 10.0
LULC_NODATA = 0
FLOAT_NODATA = -9999.0

# ---------------------------------------------------------------- class harmonisation (A2.3)

# ESRI IO LULC v02 is the class system used everywhere (decision D2). WorldCover is
# mapped onto it for cross-checks: grass/shrub/moss -> rangeland, wetland/mangroves ->
# flooded vegetation (both excluded as wet land).
WORLDCOVER_TO_ESRI = {
    10: 2,  # tree cover -> trees
    20: 11,  # shrubland -> rangeland
    30: 11,  # grassland -> rangeland
    40: 5,  # cropland -> crops
    50: 7,  # built-up -> built area
    60: 8,  # bare / sparse vegetation -> bare ground
    70: 9,  # snow and ice -> snow/ice
    80: 1,  # permanent water -> water
    90: 4,  # herbaceous wetland -> flooded vegetation
    95: 4,  # mangroves -> flooded vegetation
    100: 11,  # moss and lichen -> rangeland
}
ESRI_VALID = (1, 2, 4, 5, 7, 8, 9, 10, 11)


def harmonise_worldcover(arr: np.ndarray) -> np.ndarray:
    """WorldCover codes -> ESRI codes (0 and unknown codes -> 0 = nodata)."""
    lut = np.zeros(256, dtype=np.uint8)
    for wc, esri in WORLDCOVER_TO_ESRI.items():
        lut[wc] = esri
    return lut[arr]


# ---------------------------------------------------------------- reference grid


@dataclass(frozen=True)
class ReferenceGrid:
    """The 10 m grid every processed raster shares."""

    crs: CRS
    transform: Affine
    width: int
    height: int
    cell_size_m: float

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        left, top = self.transform.c, self.transform.f
        return (left, top - self.height * PIXEL_M, left + self.width * PIXEL_M, top)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    def profile(self, dtype: str, nodata: float) -> dict:
        return {
            "driver": "GTiff",
            "height": self.height,
            "width": self.width,
            "count": 1,
            "dtype": dtype,
            "crs": self.crs,
            "transform": self.transform,
            "nodata": nodata,
            "compress": "deflate",
            "tiled": True,
            "blockxsize": 512,
            "blockysize": 512,
        }

    def to_json(self) -> dict:
        return {
            "crs": self.crs.to_string(),
            "transform": list(self.transform)[:6],
            "width": self.width,
            "height": self.height,
            "pixel_m": PIXEL_M,
            "cell_size_m": self.cell_size_m,
            "bounds": list(self.bounds),
        }

    @classmethod
    def from_json(cls, d: dict) -> ReferenceGrid:
        return cls(
            CRS.from_string(d["crs"]),
            Affine(*d["transform"]),
            int(d["width"]),
            int(d["height"]),
            float(d["cell_size_m"]),
        )


def build_reference_grid(cfg) -> ReferenceGrid:
    """AOI + buffer in the project CRS, grown outward to whole cells."""
    cell = float(cfg.cell_size_m)
    if cell % PIXEL_M:
        raise ValueError(f"grid.cell_size_m ({cell}) must be a multiple of {PIXEL_M} m")
    left, bottom, right, top = cfg.aoi_projected.buffer(float(cfg["aoi"]["buffer_m"])).total_bounds
    left, bottom = np.floor(left / cell) * cell, np.floor(bottom / cell) * cell
    right, top = np.ceil(right / cell) * cell, np.ceil(top / cell) * cell
    return ReferenceGrid(
        crs=cfg.crs,
        transform=Affine(PIXEL_M, 0.0, float(left), 0.0, -PIXEL_M, float(top)),
        width=int(round((right - left) / PIXEL_M)),
        height=int(round((top - bottom) / PIXEL_M)),
        cell_size_m=cell,
    )


def processed_dir(cfg) -> Path:
    return Path(cfg.paths["data_processed"])


def reference_grid_path(cfg) -> Path:
    return processed_dir(cfg) / "reference_grid.json"


def load_reference_grid(cfg) -> ReferenceGrid:
    """Read the saved reference grid (for other modules, e.g. rasterising roads)."""
    path = reference_grid_path(cfg)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run `python -m src.preprocess.raster` first")
    return ReferenceGrid.from_json(json.loads(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------- alignment


def align_to_grid(
    src_path: Path,
    ref: ReferenceGrid,
    *,
    resampling: Resampling,
    dtype: str,
    dst_nodata: float,
) -> np.ndarray:
    """Read ``src_path`` onto the reference grid; cells outside the source get ``dst_nodata``."""
    out = np.full(ref.shape, dst_nodata, dtype=dtype)
    with rasterio.open(src_path) as src:
        reproject(
            rasterio.band(src, 1),
            out,
            src_nodata=src.nodata,
            dst_transform=ref.transform,
            dst_crs=ref.crs,
            dst_nodata=dst_nodata,
            resampling=resampling,
        )
    return out


def write(path: Path, arr: np.ndarray, ref: ReferenceGrid, nodata: float) -> Path:
    """Write an array as a GeoTIFF on the reference grid."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **ref.profile(str(arr.dtype), nodata)) as dst:
        dst.write(arr, 1)
    tmp.replace(path)
    return path


def dem_on_native_utm(dem_file: Path, ref: ReferenceGrid) -> tuple[np.ndarray, Affine]:
    """DEM warped to the project CRS at 30 m, on a lattice sharing the grid's origin."""
    res = 30.0
    left, bottom, right, top = ref.bounds
    pad = 2 * res  # so slope at the grid edge has neighbours
    x0, y0 = left - pad, top + pad
    w = int(np.ceil((right - left + 2 * pad) / res))
    h = int(np.ceil((top - bottom + 2 * pad) / res))
    transform = Affine(res, 0.0, x0, 0.0, -res, y0)
    z = np.full((h, w), np.nan, dtype="float32")
    with rasterio.open(dem_file) as src:
        reproject(
            rasterio.band(src, 1),
            z,
            src_nodata=src.nodata,
            dst_transform=transform,
            dst_crs=ref.crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
    return z, transform


def resample_array(
    arr: np.ndarray, transform: Affine, ref: ReferenceGrid, resampling: Resampling
) -> np.ndarray:
    """Resample an array onto the reference grid (warp)."""
    out = np.full(ref.shape, np.nan, dtype="float32")
    reproject(
        arr.astype("float32"),
        out,
        src_transform=transform,
        src_crs=ref.crs,
        src_nodata=np.nan,
        dst_transform=ref.transform,
        dst_crs=ref.crs,
        dst_nodata=np.nan,
        resampling=resampling,
    )
    return out


def preprocess_rasters(cfg, force: bool = False) -> dict[str, Path]:
    """Build the reference grid and write every aligned raster; skips existing outputs."""
    ref = build_reference_grid(cfg)
    out_dir = processed_dir(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    grid_file = reference_grid_path(cfg)
    grid_json = ref.to_json()
    if grid_file.exists() and json.loads(grid_file.read_text()) != grid_json:
        log.warning("reference grid changed (AOI or cell size?); rebuilding all outputs")
        force = True
    grid_file.write_text(json.dumps(grid_json, indent=2), encoding="utf-8")
    log.info(
        "reference grid %s: %d x %d px, bounds %s",
        ref.crs.to_string(),
        ref.width,
        ref.height,
        ref.bounds,
    )

    outputs: dict[str, Path] = {"reference_grid": grid_file}

    def todo(path: Path) -> bool:
        if path.exists() and not force:
            log.info("skip %s (exists)", path.name)
            return False
        return True

    for year in esri_years(cfg):
        p = out_dir / f"lulc_esri_{year}.tif"
        if todo(p):
            arr = align_to_grid(
                esri_path(cfg, year),
                ref,
                resampling=Resampling.nearest,
                dtype="uint8",
                dst_nodata=LULC_NODATA,
            )
            write(p, arr, ref, LULC_NODATA)
            log.info("wrote %s", p.name)
        outputs[f"lulc_esri_{year}"] = p

    wc_year = int(cfg["lulc"]["worldcover_check"])
    p = out_dir / f"worldcover_{wc_year}.tif"
    if todo(p):
        arr = align_to_grid(
            worldcover_path(cfg, wc_year),
            ref,
            resampling=Resampling.nearest,
            dtype="uint8",
            dst_nodata=LULC_NODATA,
        )
        write(p, arr, ref, LULC_NODATA)
        log.info("wrote %s", p.name)
    outputs["worldcover"] = p

    p_elev, p_slope = out_dir / "elevation.tif", out_dir / "slope.tif"
    if todo(p_elev) or todo(p_slope):
        z30, t30 = dem_on_native_utm(dem_path(cfg), ref)
        s30 = slope_degrees(z30, 30.0)
        for arr30, p in ((z30, p_elev), (s30, p_slope)):
            arr = resample_array(arr30, t30, ref, Resampling.bilinear)
            arr = np.where(np.isnan(arr), FLOAT_NODATA, arr).astype("float32")
            write(p, arr, ref, FLOAT_NODATA)
            log.info("wrote %s", p.name)
    outputs["elevation"], outputs["slope"] = p_elev, p_slope
    return outputs


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rebuild even if outputs exist")
    args = parser.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "preprocess")
    preprocess_rasters(cfg, force=args.force)


if __name__ == "__main__":
    main()
