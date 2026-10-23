"""Clean the OSM layers for each snapshot (PRD FR-3.5, FR-3.6; Tasks P3.4–P3.6).

For each snapshot (``2018`` and ``current``):

- reproject to the project CRS and clip to the reference grid (AOI + buffer);
- ``make_valid``, drop empty geometries, explode multi-part lines;
- **roads:** ``road_class`` = ``major`` (motorway, trunk, primary, secondary, incl.
  ``_link``) or ``minor`` (other drivable classes); footways, paths, steps,
  construction, proposed etc. are dropped (tracks too, unless ``vector.keep_tracks``);
- **water:** ``kind`` = ``water_body`` (``natural=water`` polygons) or ``waterway``
  (lines);
- **buildings:** drop footprints < ``vector.building_min_area_m2`` or >
  ``vector.building_max_area_m2``; add ``area_m2``, centroid ``centroid_x``/``centroid_y``,
  ``building_type`` and ``cell_id`` (``-1`` outside the grid lattice). The
  buildings whose centroid lies in an analysis grid cell form contract **C6**.

Outputs: ``data/processed/osm/<snapshot>/<layer>.gpkg`` (all cleaned features in the
reference-grid extent) and ``data/processed/buildings_<snapshot>.gpkg`` (C6).
There is one OSM source, so no deduplication with a fallback building dataset is
needed (P1.6).

Run: python -m src.preprocess.vector [--snapshot 2018|current]
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box

from src.config import load_config
from src.download.osm import layers_for, osm_path, snapshots
from src.features import schema
from src.features.grid import build_grid, lattice, xy_to_cell_id
from src.io_utils import setup_logging
from src.preprocess.raster import load_reference_grid

log = logging.getLogger(__name__)

MAJOR_ROADS = {
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link",
}  # fmt: skip
MINOR_ROADS = {
    "tertiary", "tertiary_link", "residential", "unclassified", "service",
    "living_street", "road", "busway",
}  # fmt: skip
TRACKS = {"track"}

LINE_TYPES = ("LineString", "MultiLineString")
POLY_TYPES = ("Polygon", "MultiPolygon")


def processed_osm_path(cfg, snapshot: str, layer: str) -> Path:
    return Path(cfg.paths["data_processed"]) / "osm" / snapshot / f"{layer}.gpkg"


# ---------------------------------------------------------------- geometry helpers


def _keep_types(geoms: np.ndarray, types: tuple[str, ...]) -> np.ndarray:
    """Keep only the parts of each geometry whose type is in ``types`` (None if none)."""
    out = np.empty(len(geoms), dtype=object)
    for i, g in enumerate(geoms):
        if g is None or g.is_empty:
            out[i] = None
            continue
        if g.geom_type in types:
            out[i] = g
            continue
        parts = [p for p in shapely.get_parts(g) if p.geom_type in types and not p.is_empty]
        if not parts:
            out[i] = None
        elif len(parts) == 1:
            out[i] = parts[0]
        else:
            out[i] = shapely.union_all(parts)
    return out


def clean_geometries(
    gdf: gpd.GeoDataFrame, crs, extent, types: tuple[str, ...]
) -> tuple[gpd.GeoDataFrame, dict]:
    """Reproject, make valid, clip to ``extent`` (a box), keep ``types``, drop empties."""
    stats = {"input": len(gdf)}
    g = gdf.to_crs(crs)
    geoms = g.geometry.values
    invalid = ~shapely.is_valid(geoms)
    stats["made_valid"] = int(invalid.sum())
    geoms = np.where(invalid, shapely.make_valid(geoms), geoms)
    inside = shapely.intersects(geoms, extent)
    stats["outside_extent"] = int((~inside).sum())
    g, geoms = g.loc[inside].copy(), geoms[inside]
    crosses = ~shapely.within(geoms, extent)
    geoms = np.where(crosses, shapely.intersection(geoms, extent), geoms)
    geoms = _keep_types(geoms, types)
    empty = np.array([x is None or x.is_empty for x in geoms], dtype=bool)
    stats["empty_after_clip"] = int(empty.sum())
    g = g.loc[~empty].copy()
    g = g.set_geometry(gpd.GeoSeries(geoms[~empty], index=g.index, crs=crs))
    stats["kept"] = len(g)
    return g, stats


# ---------------------------------------------------------------- layers


def classify_roads(highway: pd.Series, keep_tracks: bool) -> pd.Series:
    """'major' / 'minor' / None (not a drivable road)."""
    tag = highway.astype(str).str.split(";").str[0].str.strip()
    minor = MINOR_ROADS | (TRACKS if keep_tracks else set())
    return pd.Series(
        np.where(tag.isin(MAJOR_ROADS), "major", np.where(tag.isin(minor), "minor", None)),
        index=highway.index,
        dtype=object,
    )


def clean_roads(cfg, raw: gpd.GeoDataFrame, extent) -> tuple[gpd.GeoDataFrame, dict]:
    """Drivable roads with a major / minor class, clipped and single-part."""
    g, stats = clean_geometries(raw, cfg.crs, extent, LINE_TYPES)
    g["road_class"] = classify_roads(g["highway"], bool(cfg["vector"]["keep_tracks"]))
    stats["not_drivable"] = int(g["road_class"].isna().sum())
    stats["dropped_tags"] = (
        g.loc[g["road_class"].isna(), "highway"].value_counts().head(10).to_dict()
    )
    g = g.loc[g["road_class"].notna()]
    g = g.explode(index_parts=False).reset_index(drop=True)
    g = g[~g.geometry.is_empty]
    stats["segments"] = len(g)
    stats["km_major"] = round(float(g.loc[g["road_class"] == "major"].length.sum()) / 1000, 1)
    stats["km_minor"] = round(float(g.loc[g["road_class"] == "minor"].length.sum()) / 1000, 1)
    cols = ["osm_type", "osm_id", "highway", "road_class", "name", "ref"]
    return g[[c for c in cols if c in g.columns] + ["geometry"]], stats


def clean_water(cfg, raw: gpd.GeoDataFrame, extent) -> tuple[gpd.GeoDataFrame, dict]:
    """OSM lakes (polygons) and waterways (single-part lines), clipped."""
    raw = raw.copy()
    poly = raw.geom_type.isin(POLY_TYPES)
    natural = raw["natural"] if "natural" in raw.columns else pd.Series(None, index=raw.index)
    waterway = raw["waterway"] if "waterway" in raw.columns else pd.Series(None, index=raw.index)
    bodies, s1 = clean_geometries(raw.loc[poly & (natural == "water")], cfg.crs, extent, POLY_TYPES)
    ways, s2 = clean_geometries(raw.loc[~poly & waterway.notna()], cfg.crs, extent, LINE_TYPES)
    # multi-part lines (from OSM or from clipping a line that leaves and re-enters the
    # extent) -> one LineString per part, as for roads
    ways = ways.explode(index_parts=False).reset_index(drop=True)
    bodies["kind"] = "water_body"
    ways["kind"] = "waterway"
    g = pd.concat([bodies, ways], ignore_index=True)
    stats = {
        "water_bodies": s1,
        "waterways": s2,
        "km2_water_bodies": round(float(bodies.area.sum()) / 1e6, 2),
    }
    cols = ["osm_type", "osm_id", "kind", "natural", "water", "waterway", "name"]
    return (
        gpd.GeoDataFrame(g[[c for c in cols if c in g.columns] + ["geometry"]], crs=cfg.crs),
        stats,
    )


def clean_buildings(cfg, raw: gpd.GeoDataFrame, extent) -> tuple[gpd.GeoDataFrame, dict]:
    """Building footprints with area and centroid, size-filtered, with their grid cell."""
    g, stats = clean_geometries(raw, cfg.crs, extent, POLY_TYPES)
    # single-part MultiPolygons (osmnx returns every building as one) -> Polygon
    geoms = g.geometry.values
    n_parts = shapely.get_num_geometries(geoms)
    single = (n_parts == 1) & (shapely.get_type_id(geoms) == 6)
    geoms = np.where(single, shapely.get_geometry(geoms, 0), geoms)
    g = g.set_geometry(gpd.GeoSeries(geoms, index=g.index, crs=cfg.crs))
    area = g.area
    lo, hi = float(cfg["vector"]["building_min_area_m2"]), float(
        cfg["vector"]["building_max_area_m2"]
    )
    stats["too_small"] = int((area < lo).sum())
    stats["too_large"] = int((area > hi).sum())
    g = g.loc[(area >= lo) & (area <= hi)].copy()
    g = g.sort_values(["osm_type", "osm_id"]).reset_index(drop=True)
    c = g.geometry.centroid
    g["bldg_id"] = np.arange(len(g), dtype="int64")
    g["area_m2"] = g.area.astype("float64")
    g["centroid_x"], g["centroid_y"] = c.x.to_numpy(), c.y.to_numpy()
    g["building_type"] = (
        g["building"].fillna("yes").astype(str) if "building" in g.columns else "yes"
    )
    g["cell_id"] = xy_to_cell_id(cfg, g["centroid_x"], g["centroid_y"], lattice(cfg))
    stats["kept"] = len(g)
    cols = [
        "bldg_id",
        "osm_type",
        "osm_id",
        "building_type",
        "area_m2",
        "centroid_x",
        "centroid_y",
        "cell_id",
        "name",
        "amenity",
    ]
    return g[[c for c in cols if c in g.columns] + ["geometry"]], stats


def clean_protected(cfg, raw: gpd.GeoDataFrame, extent) -> tuple[gpd.GeoDataFrame, dict]:
    """Protected-area polygons (e.g. Bannerghatta NP), clipped."""
    g, stats = clean_geometries(raw, cfg.crs, extent, POLY_TYPES)
    stats["km2"] = round(float(g.area.sum()) / 1e6, 2)
    return g, stats


CLEANERS = {
    "roads": clean_roads,
    "water": clean_water,
    "buildings": clean_buildings,
    "protected": clean_protected,
}


# ---------------------------------------------------------------- run


def reference_extent(cfg) -> shapely.Polygon:
    """The reference grid's bounding box (the clipping extent)."""
    return box(*load_reference_grid(cfg).bounds)


def write_c6(
    cfg, buildings: gpd.GeoDataFrame, snapshot: str, grid_ids: set[int]
) -> gpd.GeoDataFrame:
    """C6: cleaned buildings whose centroid lies in an analysis grid cell."""
    c6 = buildings.loc[buildings["cell_id"].isin(grid_ids)].reset_index(drop=True)
    schema.validate_frame(c6, "C6")
    path = schema.contract_path(cfg, "C6", snapshot=snapshot)
    path.parent.mkdir(parents=True, exist_ok=True)
    c6.to_file(path, driver="GPKG")
    log.info(
        "wrote %s (%d buildings in %d grid cells)", path.name, len(c6), c6["cell_id"].nunique()
    )
    return c6


def preprocess_snapshot(cfg, snapshot: str) -> dict:
    """Clean every layer of one OSM snapshot and write it (plus C6 for the buildings)."""
    extent = reference_extent(cfg)
    grid_ids = set(build_grid(cfg)["cell_id"].tolist())
    report = {}
    for layer in layers_for(snapshot):
        src = osm_path(cfg, snapshot, layer)
        if not src.exists():
            raise FileNotFoundError(f"{src} missing: run `python -m src.download.osm` first")
        cleaned, stats = CLEANERS[layer](cfg, gpd.read_file(src), extent)
        out = processed_osm_path(cfg, snapshot, layer)
        out.parent.mkdir(parents=True, exist_ok=True)
        cleaned.to_file(out, driver="GPKG")
        log.info("%s/%s: %s", snapshot, layer, stats)
        report[layer] = stats
        if layer == "buildings":
            write_c6(cfg, cleaned, snapshot, grid_ids)
    return report


def preprocess_vectors(cfg, only: list[str] | None = None) -> dict:
    """Clean every OSM snapshot; write the layers and C6."""
    return {snap: preprocess_snapshot(cfg, snap) for snap in (only or list(snapshots(cfg)))}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", action="append", help="2018 or current (default: both)")
    args = parser.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "preprocess")
    preprocess_vectors(cfg, args.snapshot)


if __name__ == "__main__":
    main()
