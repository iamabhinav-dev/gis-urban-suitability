"""Merge raster (C2) and vector (C3) features into the feature table (C4) (PRD FR-4.4, FR-4.5).

For each feature year, C2 of that year is joined on ``cell_id`` with the OSM snapshot
that belongs to it (``schema.vector_snapshot_for``: baseline year -> 2018 snapshot,
otherwise current). Cells with ``nodata_frac`` above ``features.max_nodata_fraction``
are dropped and logged. Each table is also written as a GeoPackage of cell squares
(``grid_features_{year}.gpkg``) for viewing in a GIS.

Run: python -m src.features.build
"""

from __future__ import annotations

import logging

import pandas as pd

from src.config import load_config
from src.features import schema
from src.features.grid import grid_geodataframe
from src.features.raster_features import features_years
from src.io_utils import setup_logging

log = logging.getLogger(__name__)


def build_feature_table(cfg, year: int) -> pd.DataFrame:
    """C4 for one year (reads C2 and C3 from disk)."""
    raster = schema.read_contract(schema.contract_path(cfg, "C2", year=year), "C2")
    snapshot = schema.vector_snapshot_for(cfg, year)
    c3 = schema.contract_path(cfg, "C3", snapshot=snapshot)
    if not c3.exists():
        raise FileNotFoundError(
            f"{c3} missing: vector features for snapshot {snapshot} "
            "come from src.features.distance (H3.3)"
        )
    vector = schema.read_contract(c3, "C3")
    missing = set(raster["cell_id"]) - set(vector["cell_id"])
    if missing:
        raise ValueError(f"{len(missing)} grid cells have no vector features in {c3.name}")
    df = raster.merge(vector[["cell_id", *schema.VECTOR_FEATURES]], on="cell_id", how="left")

    max_nodata = float(cfg["features"]["max_nodata_fraction"])
    drop = df["nodata_frac"] > max_nodata
    if drop.any():
        log.warning(
            "%d: dropping %d cells with nodata_frac > %.2f", year, int(drop.sum()), max_nodata
        )
        log.info("dropped cell_ids: %s", df.loc[drop, "cell_id"].tolist()[:50])
    df = df.loc[~drop].reset_index(drop=True)
    schema.validate_frame(df, "C4")
    return df


def write_feature_gpkg(cfg, df: pd.DataFrame, path) -> None:
    """C4 with the cell squares as geometry (x, y from the grid C1)."""
    grid = schema.read_contract(schema.contract_path(cfg, "C1"), "C1")
    g = df.merge(grid[["cell_id", "x", "y"]], on="cell_id", how="left", validate="1:1")
    grid_geodataframe(g, cfg).to_file(path, driver="GPKG")


def write_feature_tables(cfg) -> dict[int, pd.DataFrame]:
    """Build and write C4 (parquet + GeoPackage) for every feature year."""
    out = {}
    for year in features_years(cfg):
        df = build_feature_table(cfg, year)
        path = schema.contract_path(cfg, "C4", year=year)
        df.to_parquet(path, index=False)
        write_feature_gpkg(cfg, df, path.with_suffix(".gpkg"))
        log.info("wrote %s (%d cells, %d columns)", path.name, len(df), df.shape[1])
        out[year] = df
    return out


def main() -> None:
    cfg = load_config()
    setup_logging(cfg, "features")
    write_feature_tables(cfg)


if __name__ == "__main__":
    main()
