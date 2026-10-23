"""Candidate sites: patches of top-class land (PRD FR-7.4; Tasks P7.2).

S1 cells of the final run are merged into patches of edge-adjacent cells (cells that only
touch at a corner are separate patches). Patches smaller than
``suitability.min_patch_area_m2`` are dropped. Each patch gets:

- ``site_id`` (1 = best), ``n_cells``, ``area_ha``;
- ``mean_score`` / ``max_score`` (combined suitability, 0-1);
- mean ``slope_deg``, ``dist_major_road_m``, ``dist_built_m``, ``dist_water_m``,
  ``road_density_km_km2`` (latest-year features, distances from the cell centres);
- land cover now: mean ``crop_share``, ``range_share``, ``tree_share`` and the
  dominant class, and an ``agricultural`` flag (crop share > 50 %, decision D10);
- centroid ``lon`` / ``lat``.

Sites are ranked by mean score (ties: larger first). Half of the S1 patches are single
1 ha cells (infill pockets), so the **top sites** for the report and the maps are the
``suitability.top_n_sites`` best patches of at least ``suitability.top_site_min_area_ha``
(column ``top_site_rank``; empty for the others). Outputs: ``outputs/candidates.gpkg``
(patch polygons) and ``outputs/candidates.csv`` (same attributes, no geometry).

Run: python -m src.suitability.candidates
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import ndimage as ndi

from src.config import load_config
from src.features import schema
from src.features.grid import grid_geodataframe, lattice
from src.io_utils import setup_logging
from src.suitability.score import S1, classes_path

log = logging.getLogger(__name__)


def gpkg_path(cfg) -> Path:
    return Path(cfg.paths["outputs"]) / "candidates.gpkg"


def csv_path(cfg) -> Path:
    return Path(cfg.paths["outputs"]) / "candidates.csv"


def label_patches(cfg, cells: pd.DataFrame) -> pd.Series:
    """Patch label of each cell (4-connectivity on the cell lattice), indexed like ``cells``."""
    lat = lattice(cfg)
    mask = np.zeros(lat.shape, bool)
    mask[cells["row"].to_numpy(), cells["col"].to_numpy()] = True
    lab, _ = ndi.label(mask)  # default structure = edge neighbours only
    return pd.Series(lab[cells["row"].to_numpy(), cells["col"].to_numpy()], index=cells.index)


def candidate_sites(cfg) -> gpd.GeoDataFrame:
    """Candidate patches with attributes, best first."""
    cls = pd.read_parquet(classes_path(cfg, "final"))
    top = cls.loc[cls["class"] == S1]
    grid = schema.read_contract(schema.contract_path(cfg, "C1"), "C1")
    c4 = schema.read_contract(
        schema.contract_path(cfg, "C4", year=int(cfg["years"]["latest"])), "C4"
    )
    cells = top.merge(grid, on="cell_id").merge(c4, on="cell_id")
    cells["patch"] = label_patches(cfg, cells)
    for col, new in (("log_dist_major", "dist_major_road_m"), ("log_dist_built", "dist_built_m"),
                     ("log_dist_water", "dist_water_m")):  # fmt: skip
        cells[new] = np.expm1(cells[col])
    agg = cells.groupby("patch").agg(
        n_cells=("cell_id", "size"),
        mean_score=("score", "mean"),
        max_score=("score", "max"),
        slope_deg=("slope_mean", "mean"),
        dist_major_road_m=("dist_major_road_m", "mean"),
        dist_built_m=("dist_built_m", "mean"),
        dist_water_m=("dist_water_m", "mean"),
        road_density_km_km2=("road_density", "mean"),
        crop_share=("frac_crop", "mean"),
        range_share=("frac_range", "mean"),
        tree_share=("frac_tree", "mean"),
        built_share=("frac_built", "mean"),
    )
    cell_ha = (lattice(cfg).cell_m ** 2) / 1e4
    agg["area_ha"] = agg["n_cells"] * cell_ha
    shares = agg[["crop_share", "range_share", "tree_share", "built_share"]]
    agg["dominant_cover"] = shares.idxmax(axis=1).str.replace("_share", "")
    agg["agricultural"] = agg["crop_share"] > 0.5
    agg = agg.loc[agg["area_ha"] * 1e4 >= float(cfg["suitability"]["min_patch_area_m2"]) - 1e-6]

    polys = grid_geodataframe(cells[["cell_id", "x", "y", "patch"]], cfg).dissolve(by="patch")
    gdf = gpd.GeoDataFrame(agg.join(polys[["geometry"]]), geometry="geometry", crs=cfg.crs)
    cen = gdf.geometry.centroid.to_crs(4326)
    gdf["lon"], gdf["lat"] = cen.x.round(6), cen.y.round(6)
    gdf = gdf.sort_values(["mean_score", "n_cells"], ascending=False).reset_index(drop=True)
    gdf.insert(0, "site_id", np.arange(1, len(gdf) + 1))
    big = gdf.index[gdf["area_ha"] >= float(cfg["suitability"]["top_site_min_area_ha"])]
    top = big[: int(cfg["suitability"]["top_n_sites"])]
    gdf["top_site_rank"] = (
        pd.Series(np.arange(1, len(top) + 1), index=top).reindex(gdf.index).astype("Int64")
    )
    num = gdf.select_dtypes("float").columns
    gdf[num] = gdf[num].round(4)
    return gdf


def write_candidates(cfg) -> gpd.GeoDataFrame:
    gdf = candidate_sites(cfg)
    gdf.to_file(gpkg_path(cfg), driver="GPKG")
    gdf.drop(columns="geometry").to_csv(csv_path(cfg), index=False)
    log.info(
        "%d candidate sites, %.0f ha in total; largest %.0f ha; %d agricultural; %d top sites",
        len(gdf), gdf["area_ha"].sum(), gdf["area_ha"].max(), int(gdf["agricultural"].sum()),
        int(gdf["top_site_rank"].notna().sum()),
    )  # fmt: skip
    return gdf


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "suitability")
    write_candidates(cfg)


if __name__ == "__main__":
    main()
