"""Exclusion mask and growth labels (contract C5) (PRD FR-4.5, FR-5.5, FR-8.1, FR-8.2, §9.6).

**Exclusion mask** (``exclusion_table``), one per run:

- ``validation`` uses only data dated <= ``years.baseline_confirm`` (time-travel rule,
  FR-8.2): ESRI water / flooded / snow in the baseline **or** confirm year, plus OSM
  water polygons from the baseline snapshot;
- ``final`` uses the two latest years and today's OSM water.

Both add the static layers: slope > ``exclusion.slope_max_deg``, nodata, and protected
areas (OSM, current; a static layer, so allowed in validation). A cell is excluded if
any rule holds; wet / protected / nodata use ``exclusion.max_excluded_fraction``.
OSM layers are optional: if a file is missing, the rule is skipped and logged.

**Labels** (C5, validation run), on cells whose centre is in the AOI:

- ``built_baseline``: built fraction >= ``growth.built_min`` in the baseline year;
- ``candidate``: built < ``growth.nonbuilt_max`` in baseline **and** confirm year, not excluded;
- ``grew``: candidate and built >= ``built_min`` in latest_confirm **and** latest;
- ``ambiguous``: candidate, did not grow, but not non-built in both end years either;
  left out of validation (PRD §9.6);
- ``chg_train_pos``: candidate and built in both ``years.change_train_end`` years;
- ``lei_type``: for grown cells, the landscape expansion index type of the 10 m growth
  patches in the cell (``adjacent`` if the patch's ring touches baseline built-up,
  ``outlying`` if not); ``none`` otherwise.

Run: python -m src.features.labels
"""

from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from scipy import ndimage as ndi

from src.config import load_config
from src.download.osm import osm_path
from src.features import schema
from src.features.grid import aoi_cell_mask, cell_ids, lattice
from src.features.lulc_features import ESRI_CODE, block_mean, class_fractions
from src.io_utils import setup_logging
from src.preprocess.raster import PIXEL_M, ReferenceGrid, load_reference_grid, processed_dir

log = logging.getLogger(__name__)

RUNS = ("validation", "final")
WET_CODES = (ESRI_CODE["water"], ESRI_CODE["flooded"], ESRI_CODE["snow"])
BUILT = ESRI_CODE["built"]


# ---------------------------------------------------------------- inputs


def read_lulc(cfg, year: int) -> np.ndarray:
    """Processed ESRI LULC of ``year`` on the reference grid."""
    with rasterio.open(processed_dir(cfg) / f"lulc_esri_{year}.tif") as ds:
        return ds.read(1)


def read_slope(cfg) -> np.ndarray:
    """Processed slope (degrees) on the reference grid."""
    with rasterio.open(processed_dir(cfg) / "slope.tif") as ds:
        return ds.read(1).astype("float64")


def run_years(cfg, run: str) -> tuple[int, int]:
    """The two LULC years that define a run's mask (validation: baseline years; final: latest)."""
    y = cfg["years"]
    if run == "validation":
        return int(y["baseline"]), int(y["baseline_confirm"])
    if run == "final":
        return int(y["latest_confirm"]), int(y["latest"])
    raise ValueError(f"run must be one of {RUNS}, got {run!r}")


def run_snapshot(cfg, run: str) -> str:
    """OSM snapshot whose water feeds a run's mask (time-travel rule)."""
    return schema.vector_snapshot_for(
        cfg, cfg["years"]["baseline"] if run == "validation" else cfg["years"]["latest"]
    )


def rasterize_polygons(gdf: gpd.GeoDataFrame, ref: ReferenceGrid) -> np.ndarray:
    """True where a pixel centre falls inside any polygon."""
    polys = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].to_crs(ref.crs)
    if polys.empty:
        return np.zeros(ref.shape, bool)
    return rasterize(
        ((g, 1) for g in polys.geometry),
        out_shape=ref.shape,
        transform=ref.transform,
        fill=0,
        dtype="uint8",
    ).astype(bool)


def osm_water_mask(cfg, snapshot: str, ref: ReferenceGrid) -> np.ndarray | None:
    """OSM ``natural=water`` polygons of a snapshot, or None if the layer is missing."""
    path = osm_path(cfg, snapshot, "water")
    if not path.exists():
        log.warning("OSM water (%s) missing: %s; wet rule uses ESRI only", snapshot, path)
        return None
    gdf = gpd.read_file(path)
    if "natural" in gdf.columns:
        gdf = gdf[gdf["natural"] == "water"]
    return rasterize_polygons(gdf, ref)


def protected_mask(cfg, ref: ReferenceGrid) -> np.ndarray | None:
    """Protected-area polygons (current snapshot, static layer), or None if missing."""
    path = osm_path(cfg, "current", "protected")
    if not path.exists():
        log.warning("OSM protected areas missing: %s; protected rule skipped", path)
        return None
    return rasterize_polygons(gpd.read_file(path), ref)


# ---------------------------------------------------------------- exclusion


def exclusion_table(cfg, run: str) -> pd.DataFrame:
    """Per-cell exclusion for one run, with the fraction behind every rule."""
    ref = load_reference_grid(cfg)
    lat = lattice(cfg)
    k = lat.px_per_cell
    years = run_years(cfg, run)
    lulc = {y: read_lulc(cfg, y) for y in years}
    wet = np.zeros(ref.shape, bool)
    for arr in lulc.values():
        wet |= np.isin(arr, WET_CODES)
    osm_wet = osm_water_mask(cfg, run_snapshot(cfg, run), ref)
    if osm_wet is not None:
        wet |= osm_wet
    prot = protected_mask(cfg, ref)
    nodata = np.maximum.reduce([class_fractions(a, k)["nodata_frac"] for a in lulc.values()])

    max_frac = float(cfg["exclusion"]["max_excluded_fraction"])
    cells = {
        "wet_frac": block_mean(wet.astype("float64"), k),
        "slope_mean": block_mean(read_slope(cfg), k),
        "nodata_frac": nodata,
        "protected_frac": (
            block_mean(prot.astype("float64"), k) if prot is not None else np.zeros(lat.shape)
        ),
    }
    rows, cols = np.nonzero(aoi_cell_mask(cfg, lat))
    df = pd.DataFrame({"cell_id": cell_ids(lat)[rows, cols]})
    for name, arr in cells.items():
        df[name] = arr[rows, cols]
    df["excl_wet"] = df["wet_frac"] > max_frac
    df["excl_slope"] = df["slope_mean"] > float(cfg["exclusion"]["slope_max_deg"])
    df["excl_nodata"] = df["nodata_frac"] > float(cfg["features"]["max_nodata_fraction"])
    df["excl_protected"] = df["protected_frac"] > max_frac
    df["excluded"] = df[["excl_wet", "excl_slope", "excl_nodata", "excl_protected"]].any(axis=1)
    df.attrs["sources"] = {
        "lulc_years": list(years),
        "osm_water": run_snapshot(cfg, run) if osm_wet is not None else None,
        "protected": "current" if prot is not None else None,
    }
    return df


# ---------------------------------------------------------------- growth type (LEI)


def lei_cell_types(cfg, built: dict[int, np.ndarray]) -> np.ndarray:
    """Growth type per lattice cell from 10 m persistent growth patches.

    New built = built in latest_confirm and latest, non-built in baseline and confirm.
    Each 8-connected patch gets LEI = share of its ring (``growth.lei_buffer_m`` wide)
    that was built at baseline: > 0 -> ``adjacent``, 0 -> ``outlying``. A cell takes the
    type that covers most of its new-built pixels, counting only patches of at least
    ``growth.lei_min_patch_m2`` (all patches if the cell has none that large).
    """
    y = cfg["years"]
    k = lattice(cfg).px_per_cell
    old = built[y["baseline"]]
    new = ~old & ~built[y["baseline_confirm"]] & built[y["latest_confirm"]] & built[y["latest"]]
    lab, n = ndi.label(new, structure=np.ones((3, 3), bool))
    shape = (new.shape[0] // k, new.shape[1] // k)
    if n == 0:
        return np.full(shape, "none", dtype=object)
    idx = np.arange(1, n + 1)
    size = ndi.sum(new, lab, idx)
    r = max(1, int(round(float(cfg["growth"]["lei_buffer_m"]) / PIXEL_M)))
    dil = ndi.grey_dilation(lab, size=(2 * r + 1, 2 * r + 1))
    ring = (dil > 0) & (lab == 0)
    ring_n = ndi.sum(ring, dil, idx)
    ring_old = ndi.sum(ring & old, dil, idx)
    outlying = np.r_[False, (ring_old == 0) & (ring_n > 0)]
    big = np.r_[False, size * PIXEL_M**2 >= float(cfg["growth"]["lei_min_patch_m2"])]

    def counts(mask: np.ndarray) -> np.ndarray:
        return mask.reshape(shape[0], k, shape[1], k).sum(axis=(1, 3))

    out_big, adj_big = counts(big[lab] & outlying[lab]), counts(
        big[lab] & ~outlying[lab] & (lab > 0)
    )
    out_all, adj_all = counts(outlying[lab]), counts(~outlying[lab] & (lab > 0))
    use_big = (out_big + adj_big) > 0
    out_n = np.where(use_big, out_big, out_all)
    adj_n = np.where(use_big, adj_big, adj_all)
    types = np.full(shape, "none", dtype=object)
    has = (out_n + adj_n) > 0
    types[has] = np.where(out_n[has] > adj_n[has], "outlying", "adjacent")
    return types


# ---------------------------------------------------------------- labels


def build_labels(cfg) -> pd.DataFrame:
    """C5 for the validation run."""
    return build_labels_and_mask(cfg)[0]


def build_labels_and_mask(cfg) -> tuple[pd.DataFrame, pd.DataFrame]:
    """C5 for the validation run, plus the validation exclusion table it used."""
    y = cfg["years"]
    lat = lattice(cfg)
    k = lat.px_per_cell
    years = sorted(
        {
            int(y["baseline"]),
            int(y["baseline_confirm"]),
            *map(int, y["change_train_end"]),
            int(y["latest_confirm"]),
            int(y["latest"]),
        }
    )
    lulc = {yr: read_lulc(cfg, yr) for yr in years}
    built = {yr: arr == BUILT for yr, arr in lulc.items()}
    frac = {yr: class_fractions(arr, k)["frac_built"] for yr, arr in lulc.items()}
    lo, hi = float(cfg["growth"]["nonbuilt_max"]), float(cfg["growth"]["built_min"])

    excl = exclusion_table(cfg, "validation")
    rows, cols = np.nonzero(aoi_cell_mask(cfg, lat))

    def at(arr: np.ndarray) -> np.ndarray:
        return arr[rows, cols]

    excluded = excl["excluded"].to_numpy()
    nonbuilt_start = at(frac[y["baseline"]] < lo) & at(frac[y["baseline_confirm"]] < lo)
    candidate = nonbuilt_start & ~excluded
    t0, t1 = map(int, y["change_train_end"])
    grew = candidate & at(frac[y["latest_confirm"]] >= hi) & at(frac[y["latest"]] >= hi)
    stayed = candidate & at(frac[y["latest_confirm"]] < lo) & at(frac[y["latest"]] < lo)
    lei = at(lei_cell_types(cfg, built))
    df = pd.DataFrame(
        {
            "cell_id": cell_ids(lat)[rows, cols],
            "excluded": excluded,
            "built_baseline": at(frac[y["baseline"]] >= hi),
            "candidate": candidate,
            "grew": grew,
            "ambiguous": candidate & ~grew & ~stayed,
            "chg_train_pos": candidate & at(frac[t0] >= hi) & at(frac[t1] >= hi),
            "lei_type": np.where(grew, lei, "none").astype(object),
        }
    )
    # a grown cell always has new-built pixels, so it always has a type
    df.loc[df["grew"] & (df["lei_type"] == "none"), "lei_type"] = "adjacent"
    schema.validate_frame(df, "C5")
    return df, excl


def log_label_counts(df: pd.DataFrame, excl: pd.DataFrame | None = None) -> dict[str, int]:
    """Log and return how many cells carry each label."""
    counts = {
        "cells": len(df),
        "excluded": int(df["excluded"].sum()),
        "built_baseline": int(df["built_baseline"].sum()),
        "candidate": int(df["candidate"].sum()),
        "grew": int(df["grew"].sum()),
        "ambiguous": int(df["ambiguous"].sum()),
        "stayed_nonbuilt": int((df["candidate"] & ~df["grew"] & ~df["ambiguous"]).sum()),
        "chg_train_pos": int(df["chg_train_pos"].sum()),
        "lei_adjacent": int((df["lei_type"] == "adjacent").sum()),
        "lei_outlying": int((df["lei_type"] == "outlying").sum()),
        "mid_threshold_start": int(
            (~df["excluded"] & ~df["candidate"] & ~df["built_baseline"]).sum()
        ),
    }
    if excl is not None:
        for rule in ("excl_wet", "excl_slope", "excl_nodata", "excl_protected"):
            counts[rule] = int(excl[rule].sum())
    for name, n in counts.items():
        log.info("labels: %-20s %7d", name, n)
    return counts


def write_labels(cfg) -> pd.DataFrame:
    """Build C5 and both runs' exclusion tables; write them."""
    df, val_excl = build_labels_and_mask(cfg)
    counts = log_label_counts(df, val_excl)
    path = schema.contract_path(cfg, "C5")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    for run in RUNS:
        excl = val_excl if run == "validation" else exclusion_table(cfg, run)
        out = path.parent / f"exclusion_{run}.parquet"
        excl.to_parquet(out, index=False)
        log.info(
            "wrote %s (%d excluded; sources %s)",
            out.name,
            int(excl["excluded"].sum()),
            excl.attrs["sources"],
        )
    log.info("wrote %s", path.name)
    df.attrs["counts"] = counts
    return df


def main() -> None:
    cfg = load_config()
    setup_logging(cfg, "features")
    write_labels(cfg)


if __name__ == "__main__":
    main()
