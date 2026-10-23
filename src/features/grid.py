"""The analysis grid (contract C1): square cells on the reference-grid lattice (PRD FR-4.1).

Cells are ``grid.cell_size_m`` squares whose edges fall on the 10 m reference grid,
so each cell is exactly a block of reference pixels. The lattice covers the whole
reference grid (AOI + buffer). The analysis grid keeps the cells whose **centre**
lies inside the AOI.

``cell_id = row * n_cols + col`` on the lattice, so an id never changes as long as
the AOI and cell size stay the same, and any point maps to a cell id with
``xy_to_cell_id``.

Usage:
    from src.features.grid import build_grid, xy_to_cell_id
    grid = build_grid(cfg)                      # DataFrame: cell_id, row, col, x, y
    ids = xy_to_cell_id(cfg, xs, ys)            # e.g. building centroids -> cell_id
"""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from src.features import schema
from src.preprocess.raster import PIXEL_M, ReferenceGrid, load_reference_grid


@dataclass(frozen=True)
class Lattice:
    """Cell lattice over the reference grid."""

    ref: ReferenceGrid
    cell_m: float

    @property
    def px_per_cell(self) -> int:
        return int(round(self.cell_m / PIXEL_M))

    @property
    def shape(self) -> tuple[int, int]:
        k = self.px_per_cell
        return (self.ref.height // k, self.ref.width // k)

    @property
    def left(self) -> float:
        return self.ref.transform.c

    @property
    def top(self) -> float:
        return self.ref.transform.f

    def centres(self) -> tuple[np.ndarray, np.ndarray]:
        """x, y of every cell centre, shape = lattice shape."""
        rows, cols = np.indices(self.shape)
        return (self.left + (cols + 0.5) * self.cell_m, self.top - (rows + 0.5) * self.cell_m)

    def xy_to_rowcol(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        col = np.floor((np.asarray(x, float) - self.left) / self.cell_m).astype(int)
        row = np.floor((self.top - np.asarray(y, float)) / self.cell_m).astype(int)
        return row, col


def lattice(cfg) -> Lattice:
    """The 100 m cell lattice of the project's reference grid."""
    return Lattice(load_reference_grid(cfg), float(cfg.cell_size_m))


def cell_ids(lat: Lattice) -> np.ndarray:
    """cell_id for every lattice position, shape = lattice shape."""
    return np.arange(lat.shape[0] * lat.shape[1], dtype="int64").reshape(lat.shape)


def aoi_cell_mask(cfg, lat: Lattice) -> np.ndarray:
    """True where the cell centre lies inside the AOI."""
    x, y = lat.centres()
    aoi = cfg.aoi_projected.geometry.iloc[0]
    return shapely.contains_xy(aoi, x.ravel(), y.ravel()).reshape(lat.shape)


def build_grid(cfg) -> pd.DataFrame:
    """C1: one row per cell whose centre is inside the AOI."""
    lat = lattice(cfg)
    keep = aoi_cell_mask(cfg, lat)
    rows, cols = np.nonzero(keep)
    x, y = lat.centres()
    df = pd.DataFrame(
        {
            "cell_id": cell_ids(lat)[rows, cols],
            "row": rows.astype("int64"),
            "col": cols.astype("int64"),
            "x": x[rows, cols],
            "y": y[rows, cols],
        }
    )
    schema.validate_frame(df, "C1")
    return df


def grid_geodataframe(grid: pd.DataFrame, cfg) -> gpd.GeoDataFrame:
    """Cell squares as polygons, in the project CRS."""
    h = float(cfg.cell_size_m) / 2
    x, y = grid["x"].to_numpy(), grid["y"].to_numpy()  # arrays: no index alignment
    geom = shapely.box(x - h, y - h, x + h, y + h)
    return gpd.GeoDataFrame(grid.copy(), geometry=geom, crs=cfg.crs)


def xy_to_cell_id(cfg, x, y, lat: Lattice | None = None) -> np.ndarray:
    """cell_id of the cell containing each point (project CRS); -1 outside the lattice."""
    lat = lat or lattice(cfg)
    row, col = lat.xy_to_rowcol(x, y)
    inside = (row >= 0) & (row < lat.shape[0]) & (col >= 0) & (col < lat.shape[1])
    return np.where(inside, row * lat.shape[1] + col, -1).astype("int64")


def write_grid(cfg) -> pd.DataFrame:
    """Build the analysis grid and write C1 (parquet + GeoPackage)."""
    grid = build_grid(cfg)
    path = schema.contract_path(cfg, "C1")
    path.parent.mkdir(parents=True, exist_ok=True)
    grid.to_parquet(path, index=False)
    gpkg = path.with_suffix(".gpkg")
    grid_geodataframe(grid, cfg).to_file(gpkg, driver="GPKG")
    return grid
