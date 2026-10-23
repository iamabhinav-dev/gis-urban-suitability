"""Context profiles for the building similarity (PRD FR-6.2, §9.5; Tasks P6.1).

The profile of a location is the ``schema.MODEL_INPUTS`` vector of the 100 m cell it
lies in: built-up, tree, crop, rangeland, bare and water shares in the 250 m and 500 m
rings around the cell (never the cell itself), distances to built-up, water, a major
road and any road, road density within 500 m, and terrain. Own-cell land cover and
building counts are refused (``schema.check_model_inputs``, decision D4).

Profiles are standardised (z-scores) with means and standard deviations fitted on the
reference and candidate cells of the run together, so a distance of 1 means one
standard deviation of the cells being compared. Runs follow the time-travel rule:
``validation`` uses the baseline-year features, ``final`` the latest year.

Candidate cells: ``validation``: C5 ``candidate``; ``final``: usable cells of the final
3-class map (C7 ``class_3 = 3``, which already excludes masked cells).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pyproj import Transformer

from src.classify.cluster import RUNS, run_year
from src.classify.label import c7_path
from src.features import schema
from src.features.grid import xy_to_cell_id
from src.similarity import reference as rs


def profile_columns(columns=None) -> list[str]:
    """Profile columns (default ``schema.MODEL_INPUTS``); raises on own-cell or leaky ones."""
    cols = list(columns) if columns is not None else list(schema.MODEL_INPUTS)
    schema.check_model_inputs(cols)
    return cols


def profile_table(cfg, run: str, columns=None) -> pd.DataFrame:
    """Raw profiles of every grid cell for the run's feature year, indexed by cell_id."""
    if run not in RUNS:
        raise ValueError(f"run must be one of {RUNS}, got {run!r}")
    cols = profile_columns(columns)
    c4 = schema.read_contract(schema.contract_path(cfg, "C4", year=run_year(cfg, run)), "C4")
    return c4.set_index("cell_id")[cols].astype("float64")


def candidate_cells(cfg, run: str) -> np.ndarray:
    """Cells a similarity score may rank (FR-6.7): candidates (validation) or usable (final)."""
    if run == "validation":
        lab = schema.read_contract(schema.contract_path(cfg, "C5"), "C5")
        return lab.loc[lab["candidate"], "cell_id"].to_numpy()
    c7 = schema.read_contract(c7_path(cfg, "final"), "C7")
    return c7.loc[c7["class_3"] == schema.CLASS_USABLE, "cell_id"].to_numpy()


def reference_ids(cfg, run: str) -> np.ndarray:
    """Reference cells of the run (P6.2), read from disk if built, else computed."""
    p = rs.reference_path(cfg, run)
    ref = pd.read_parquet(p) if p.exists() else rs.reference_cells(cfg, run)
    return ref["cell_id"].to_numpy()


@dataclass
class Standardiser:
    """Z-scores with statistics fitted on a set of cells."""

    mean: pd.Series
    std: pd.Series

    @classmethod
    def fit(cls, profiles: pd.DataFrame) -> Standardiser:
        std = profiles.std(ddof=0).replace(0.0, 1.0)  # a constant column stays 0
        return cls(profiles.mean(), std)

    def transform(self, profiles: pd.DataFrame) -> pd.DataFrame:
        return (profiles[self.mean.index] - self.mean) / self.std


@dataclass
class RunProfiles:
    """Standardised profiles of one run: every grid cell, plus the reference and candidate sets."""

    run: str
    z: pd.DataFrame  # every grid cell, standardised
    reference: np.ndarray
    candidates: np.ndarray
    scaler: Standardiser


def run_profiles(cfg, run: str, columns=None) -> RunProfiles:
    """Profiles of a run, standardised on its reference + candidate cells."""
    raw = profile_table(cfg, run, columns)
    ref = np.intersect1d(reference_ids(cfg, run), raw.index.to_numpy())
    cand = np.intersect1d(candidate_cells(cfg, run), raw.index.to_numpy())
    scaler = Standardiser.fit(raw.loc[np.union1d(ref, cand)])
    return RunProfiles(run, scaler.transform(raw), ref, cand, scaler)


def lonlat_to_cell(cfg, lon: float, lat: float) -> int:
    """Grid cell id of a WGS84 point (-1 outside the grid)."""
    x, y = Transformer.from_crs(4326, cfg.crs, always_xy=True).transform(lon, lat)
    return int(xy_to_cell_id(cfg, np.array([x]), np.array([y]))[0])


def building_cell(cfg, run: str, bldg_id: int) -> tuple[int, pd.Series]:
    """Cell id and attributes of a reference building (C6 of the run's OSM snapshot)."""
    b = rs.buildings(cfg, run).set_index("bldg_id")
    if bldg_id not in b.index:
        raise KeyError(f"building {bldg_id} is not in the {rs.run_snapshot(cfg, run)} buildings")
    row = b.loc[bldg_id]
    return int(row["cell_id"]), row
