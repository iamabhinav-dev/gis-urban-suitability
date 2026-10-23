"""Data for the website's "find places like A" tool (Tasks P8.3; PRD FR-6.3).

The single-building query (``src/similarity/query.py``) is pure arithmetic on cell profiles,
so the website runs it in the browser. This module exports what it needs, for the
**final run** (latest data):

- ``profiles.bin``: the raw profile (``schema.MODEL_INPUTS``, 20 values) of every AOI cell,
  in row-major lattice order, as little-endian uint16 linearly scaled to each column's
  [min, max] (precision ~1/65,535 of the range; 2.3 MB);
- ``cells.bin``: one uint8 per lattice position: 0 outside the AOI, else the class of the
  final 3-class map (1 built-up, 2 forest, 3 usable, 4 excluded), followed by one uint8 per
  lattice position with the suitability class (0 none, 1 S1, 2 S2, 3 S3, 4 N);
- ``meta.json``: lattice (origin, cell size, shape, proj4 string), columns with their
  scaling, the standardisation (mean / sd fitted on reference + usable cells, exactly as the
  Python query), readable labels and display units, the example buildings of notebook 05;
- ``aoi.geojson`` (study-area outline), ``sites.geojson`` (the top candidate sites) and the
  overlays ``usable.png``, ``built.png``, ``suitability.png`` (classes S1-S3), with their WGS84
  bounds in ``meta.json``.

Run: python -m src.viz.web_data [--out outputs/site/data]
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

from src.classify.label import c7_path
from src.config import load_config
from src.features import schema
from src.features.grid import lattice
from src.io_utils import setup_logging
from src.similarity import profiles as pf
from src.similarity.query import feature_label
from src.suitability.score import classes_path
from src.viz import style

log = logging.getLogger(__name__)

CLASS_CODE = {
    schema.CLASS_BUILT: 1,
    schema.CLASS_FOREST: 2,
    schema.CLASS_USABLE: 3,
    schema.CLASS_EXCLUDED: 4,
}
Q = 65535


def display(col: str) -> dict:
    """How the website shows a column: unit and transform from the stored value."""
    if col.startswith("log_dist"):
        return {"unit": "m", "show": "expm1"}
    if col.startswith("ring"):
        return {"unit": "%", "show": "percent"}
    if col == "road_density":
        return {"unit": "km/km²", "show": "value"}
    if col == "elev_mean":
        return {"unit": "m", "show": "value"}
    return {"unit": "°", "show": "value"}  # slopes


def encode(raw: pd.DataFrame) -> tuple[np.ndarray, list[dict]]:
    """uint16 per value, scaled per column to [min, max]; returns (array, column specs)."""
    specs, out = [], np.zeros(raw.shape, dtype="<u2")
    for j, col in enumerate(raw.columns):
        v = raw[col].to_numpy(dtype="float64")
        lo, hi = float(v.min()), float(v.max())
        span = hi - lo if hi > lo else 1.0
        out[:, j] = np.round((v - lo) / span * Q).astype("<u2")
        specs.append(
            {"name": col, "label": feature_label(col), "min": lo, "max": hi, **display(col)}
        )
    return out, specs


def decode(arr: np.ndarray, specs: list[dict]) -> np.ndarray:
    """Inverse of ``encode`` (float64), as the website does it."""
    lo = np.array([s["min"] for s in specs])
    hi = np.array([s["max"] for s in specs])
    span = np.where(hi > lo, hi - lo, 1.0)
    return lo + arr.astype("float64") / Q * span


EXAMPLE_TYPES = {"industrial": "Industrial building", "apartments": "Apartment block",
                 "school": "School", "house": "House"}  # fmt: skip


def examples(cfg) -> list[dict]:
    """The example buildings of notebook 05 (same seeded choice), as WGS84 points."""
    from src.similarity import reference as rs

    b = rs.buildings(cfg, "final")
    out = []
    for t, label in EXAMPLE_TYPES.items():
        pick = b.loc[b["building_type"] == t].sample(
            1, random_state=int(cfg["project"]["random_seed"])
        )
        cid = int(pick["cell_id"].iloc[0])
        lat = lattice(cfg)
        row, col = divmod(cid, lat.shape[1])
        x, y = lat.left + (col + 0.5) * lat.cell_m, lat.top - (row + 0.5) * lat.cell_m
        lon, la = Transformer.from_crs(cfg.crs, 4326, always_xy=True).transform(x, y)
        out.append(
            {
                "label": label,
                "bldg_id": int(pick["bldg_id"].iloc[0]),
                "lon": round(lon, 6),
                "lat": round(la, 6),
            }
        )
    return out


def overlay(path: Path, out: Path, colors: dict[int, str], alpha: float) -> list[list[float]]:
    """PNG of a class raster (listed codes coloured, others transparent) in WGS84; its bounds."""
    from src.viz.interactive import categorical_png, to_wgs84

    arr, bounds = to_wgs84(path)
    url = categorical_png(arr, colors, alpha=alpha)
    out.write_bytes(base64.b64decode(url.split(",", 1)[1]))
    return bounds


SITE_COLUMNS = ["top_site_rank", "area_ha", "mean_score", "slope_deg", "dist_major_road_m",
                "dist_built_m", "dominant_cover", "lon", "lat"]  # fmt: skip


def top_sites(cfg, path: Path) -> int:
    """The top candidate sites (``candidates.gpkg``) as WGS84 GeoJSON, ranked; returns how many."""
    import geopandas as gpd

    g = gpd.read_file(Path(cfg.paths["outputs"]) / "candidates.gpkg")
    g = g.loc[g["top_site_rank"].notna(), [*SITE_COLUMNS, "geometry"]].sort_values("top_site_rank")
    g = g.rename(columns={"top_site_rank": "rank"}).astype({"rank": int}).round(4)
    g.to_crs(4326).to_file(path, driver="GeoJSON")
    return len(g)


def export(cfg, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    lat = lattice(cfg)
    grid = schema.read_contract(schema.contract_path(cfg, "C1"), "C1").sort_values(["row", "col"])
    raw = pf.profile_table(cfg, "final").loc[grid["cell_id"]]
    rp = pf.run_profiles(cfg, "final")
    enc, specs = encode(raw)
    for s in specs:
        s["mean"] = float(rp.scaler.mean[s["name"]])
        s["sd"] = float(rp.scaler.std[s["name"]])
    (out / "profiles.bin").write_bytes(enc.tobytes())

    c7 = schema.read_contract(c7_path(cfg, "final"), "C7").set_index("cell_id")
    cls = np.zeros(lat.shape, dtype="u1")
    cls[grid["row"], grid["col"]] = c7.loc[grid["cell_id"], "class_3"].map(CLASS_CODE).to_numpy()
    suit = np.zeros(lat.shape, dtype="u1")
    sc = pd.read_parquet(classes_path(cfg, "final")).set_index("cell_id")
    g = grid.set_index("cell_id").loc[sc.index]
    suit[g["row"], g["col"]] = sc["class"].to_numpy()
    (out / "cells.bin").write_bytes(cls.tobytes() + suit.tobytes())

    meta = {
        "run": "final",
        "years": {
            "lulc": int(cfg["years"]["latest"]),
            "osm": str(cfg["osm"].get("snapshot_current")),
        },
        "lattice": {
            "left": lat.left,
            "top": lat.top,
            "cell_m": lat.cell_m,
            "rows": lat.shape[0],
            "cols": lat.shape[1],
        },
        "proj4": cfg.crs.to_proj4().replace(" +type=crs", ""),
        "n_cells": int(len(grid)),
        "n_usable": int((cls == 3).sum()),
        "classes": {"1": "built-up", "2": "forest", "3": "usable", "4": "excluded"},
        "suitability": {"1": "S1", "2": "S2", "3": "S3", "4": "N"},
        "quant": Q,
        "columns": specs,
        "trivial_share": 0.005,
    }
    meta["examples"] = examples(cfg)
    outputs = Path(cfg.paths["outputs"])
    meta["usable_overlay"] = overlay(
        outputs / "lulc_3class.tif", out / "usable.png", {schema.CLASS_USABLE: "#6da7ec"}, 0.45
    )
    meta["built_overlay"] = overlay(
        outputs / "lulc_3class.tif", out / "built.png", {schema.CLASS_BUILT: "#eb6834"}, 0.16
    )
    suit = {1: style.SEQ_BLUE[6], 2: style.SEQ_BLUE[4], 3: style.SEQ_BLUE[2]}
    meta["suitability_overlay"] = overlay(
        outputs / "suitability_class.tif", out / "suitability.png", suit, 0.9
    )
    meta["n_sites"] = top_sites(cfg, out / "sites.geojson")
    cfg.aoi.to_crs(4326).to_file(out / "aoi.geojson", driver="GeoJSON")
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    log.info(
        "wrote %s: %d cells x %d features (%.1f MB)", out, len(grid), len(specs), enc.nbytes / 1e6
    )
    return meta


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    cfg = load_config()
    parser.add_argument("--out", default=str(Path(cfg.paths["outputs"]) / "site" / "data"))
    args = parser.parse_args(argv)
    setup_logging(cfg, "viz")
    export(cfg, Path(args.out))


if __name__ == "__main__":
    main()
