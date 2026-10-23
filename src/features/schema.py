"""Data contracts between the raster and vector tracks (docs/execution_plan.md §4).

Every file that passes from one track to the other is described here: its path,
its required columns, their types and their allowed values. Code on both sides
imports names from this module instead of typing column names by hand, and
``validate_frame`` / ``validate_project`` check real and stub files alike.

Changing anything in this file changes a contract: agree it with the other track.

Usage:
    from src.features import schema
    path = schema.contract_path(cfg, "C4", year=2018)
    schema.validate_frame(df, "C4")
    schema.check_model_inputs(["ring500_built", "log_dist_major"])
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- classes

# ESRI IO LULC v02 class codes (decision D2: ESRI is the LULC source everywhere).
ESRI_CLASSES = {
    1: "water",
    2: "tree",
    4: "flooded",
    5: "crop",
    7: "built",
    8: "bare",
    9: "snow",
    10: "cloud",
    11: "range",
}
ESRI_NODATA = 0

# Three-class map (C7)
CLASS_BUILT, CLASS_FOREST, CLASS_USABLE, CLASS_EXCLUDED = 1, 2, 3, 255
CLASS_3_VALUES = (CLASS_BUILT, CLASS_FOREST, CLASS_USABLE, CLASS_EXCLUDED)

# Growth type from the landscape expansion index (C5)
LEI_TYPES = ("none", "adjacent", "outlying")

# ---------------------------------------------------------------- features

OWN_FRACTION_CLASSES = ("water", "tree", "flooded", "crop", "built", "bare", "snow", "range")
RING_RADII_M = (250, 500)
RING_CLASSES = ("built", "tree", "crop", "range", "bare", "water")

# Own-cell LULC fractions: allowed for clustering only (decision D4).
OWN_FRACTIONS = tuple(f"frac_{c}" for c in OWN_FRACTION_CLASSES)
# Ring fractions: share of a class in the square window of the given radius,
# excluding the centre cell (so they never encode the cell's own status).
RING_FRACTIONS = tuple(f"ring{r}_{c}" for r in RING_RADII_M for c in RING_CLASSES)

FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "lulc_own": OWN_FRACTIONS,
    "lulc_context": tuple(f for f in RING_FRACTIONS if not f.endswith("_built")),
    "near_built": ("ring250_built", "ring500_built", "log_dist_built"),
    "roads": ("log_dist_major", "log_dist_any", "road_density"),
    "terrain": ("elev_mean", "slope_mean", "slope_max"),
    "water": ("log_dist_water",),
    "buildings": ("bldg_count", "bldg_area_frac"),
}

OWN_CELL_FEATURES = FEATURE_GROUPS["lulc_own"] + FEATURE_GROUPS["buildings"]
# Features that directly encode "this cell is built" (PRD FR-6.6).
LEAKY_FEATURES = ("frac_built", "bldg_count", "bldg_area_frac")
# Only these may feed the similarity and RF models (decision D4).
CONTEXT_FEATURES = tuple(
    f
    for g in ("lulc_context", "near_built", "roads", "terrain", "water")
    for f in FEATURE_GROUPS[g]
)
MODEL_INPUTS = tuple(f for f in CONTEXT_FEATURES if f not in LEAKY_FEATURES)
# Groups dropped one at a time in the ablation (execution_plan H5.5)
ABLATION_GROUPS = ("lulc_context", "near_built", "roads", "terrain", "water")
# Default clustering inputs (Harsh may change this in H4)
CLUSTER_INPUTS = OWN_FRACTIONS + FEATURE_GROUPS["terrain"]

RASTER_FEATURES = (
    OWN_FRACTIONS
    + RING_FRACTIONS
    + FEATURE_GROUPS["terrain"]
    + ("log_dist_built", "log_dist_water", "nodata_frac")
)
VECTOR_FEATURES = FEATURE_GROUPS["roads"] + FEATURE_GROUPS["buildings"]


class ContractError(ValueError):
    """Raised when a file or column list breaks a contract."""


def check_model_inputs(columns: list[str] | tuple[str, ...]) -> None:
    """Raise if any column is not an allowed model input (own-cell, leaky or unknown)."""
    bad = [c for c in columns if c not in MODEL_INPUTS]
    if bad:
        raise ContractError(
            f"Not allowed as model inputs (own-cell, leaky or unknown): {bad}. "
            "Use names from schema.MODEL_INPUTS."
        )


# ---------------------------------------------------------------- column specs


@dataclass(frozen=True)
class Col:
    """One required column: dtype kind and allowed values."""

    kind: str  # "int", "float", "bool", "str"
    lo: float | None = None
    hi: float | None = None
    values: tuple[Any, ...] | None = None
    nullable: bool = False


FRACTION = Col("float", 0.0, 1.0)
LOG_DIST = Col("float", 0.0, None)

_RASTER_COLS: dict[str, Col] = {
    **{f: FRACTION for f in OWN_FRACTIONS + RING_FRACTIONS},
    "elev_mean": Col("float", -500.0, 9000.0),
    "slope_mean": Col("float", 0.0, 90.0),
    "slope_max": Col("float", 0.0, 90.0),
    "log_dist_built": LOG_DIST,
    "log_dist_water": LOG_DIST,
    "nodata_frac": FRACTION,
}
_VECTOR_COLS: dict[str, Col] = {
    "log_dist_major": LOG_DIST,
    "log_dist_any": LOG_DIST,
    "road_density": Col("float", 0.0, None),  # km of road per km²
    "bldg_count": Col("int", 0, None),
    "bldg_area_frac": FRACTION,
}
CELL_ID = {"cell_id": Col("int", 0, None)}


@dataclass(frozen=True)
class Contract:
    """A file passed between the tracks."""

    id: str
    template: str  # path relative to the repo root, with {year} / {snapshot} / {model}
    producer: str
    columns: dict[str, Col] = field(default_factory=dict)
    key: str | None = "cell_id"  # must be unique; None = no key
    geo: bool = False  # GeoPackage read with geopandas


CONTRACTS: dict[str, Contract] = {
    "C1": Contract(
        "C1",
        "{data_features}/grid.parquet",
        "Abhinav (A3.1)",
        {
            **CELL_ID,
            "row": Col("int", 0, None),
            "col": Col("int", 0, None),
            "x": Col("float"),
            "y": Col("float"),
        },
    ),
    "C2": Contract(
        "C2",
        "{data_features}/raster_features_{year}.parquet",
        "Abhinav (A3.4)",
        {**CELL_ID, **_RASTER_COLS},
    ),
    "C3": Contract(
        "C3",
        "{data_features}/vector_features_{snapshot}.parquet",
        "Harsh (H3.3)",
        {**CELL_ID, **_VECTOR_COLS},
    ),
    "C4": Contract(
        "C4",
        "{data_features}/grid_features_{year}.parquet",
        "Abhinav (A3.5)",
        {**CELL_ID, **_RASTER_COLS, **_VECTOR_COLS},
    ),
    "C5": Contract(
        "C5",
        "{data_features}/labels.parquet",
        "Abhinav (A4)",
        {
            **CELL_ID,
            "excluded": Col("bool"),
            "built_baseline": Col("bool"),  # built in years.baseline
            "candidate": Col("bool"),  # non-built in baseline + baseline_confirm, not excluded
            "grew": Col("bool"),  # candidate and built in latest + latest_confirm
            # candidate that neither grew nor stayed non-built (built fraction between
            # the thresholds, or flickering, in latest_confirm/latest): left out of
            # validation (PRD §9.6)
            "ambiguous": Col("bool"),
            "chg_train_pos": Col("bool"),  # non-built baseline(+confirm), built change_train_end
            "lei_type": Col("str", values=LEI_TYPES),
        },
    ),
    "C6": Contract(
        "C6",
        "{data_processed}/buildings_{snapshot}.gpkg",
        "Harsh (H2.3b)",
        {
            "bldg_id": Col("int", 0, None),
            "area_m2": Col("float", 0.0, None),
            "building_type": Col("str"),
            "cell_id": Col("int", 0, None),
        },
        key="bldg_id",
        geo=True,
    ),
    "C7": Contract(
        "C7",
        "{outputs}/lulc_3class.parquet",
        "Harsh (H4.4)",
        {
            **CELL_ID,
            "cluster_id": Col("int", -1, None),  # -1 = not clustered (excluded / nodata)
            "class_3": Col("int", values=CLASS_3_VALUES),
        },
    ),
    "C8": Contract(
        "C8",
        "{outputs}/scores/{model}.parquet",
        "any model",
        {**CELL_ID, "score": Col("float")},  # higher = more suitable
    ),
}

# Keys every C8 metadata JSON must have
SCORE_META_KEYS = ("model", "features", "train_years", "description")


# ---------------------------------------------------------------- paths


def vector_snapshot_for(cfg, year: int) -> str:
    """OSM snapshot to pair with raster features of ``year`` (decisions D8, D9)."""
    if int(year) == int(cfg["years"]["baseline"]):
        return str(cfg["osm"]["snapshot_baseline"])[:4]
    return "current"


def contract_path(cfg, contract_id: str, **fields: Any) -> Path:
    """Absolute path of a contract file, e.g. ``contract_path(cfg, "C2", year=2018)``."""
    c = CONTRACTS[contract_id]
    names = {k: str(v) for k, v in cfg.paths.items()}
    try:
        return Path(c.template.format(**names, **fields))
    except KeyError as exc:
        raise ContractError(f"{contract_id} path needs {exc}") from exc


def score_meta_path(cfg, model: str) -> Path:
    return contract_path(cfg, "C8", model=model).with_suffix(".json")


# ---------------------------------------------------------------- validation

_KIND_CHECK = {
    "int": pd.api.types.is_integer_dtype,
    "float": pd.api.types.is_float_dtype,
    "bool": pd.api.types.is_bool_dtype,
    "str": lambda s: pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s),
}


def validate_frame(df: pd.DataFrame, contract_id: str) -> None:
    """Raise ContractError listing every problem with ``df`` for the given contract."""
    c = CONTRACTS[contract_id]
    problems: list[str] = []
    missing = [n for n in c.columns if n not in df.columns]
    if missing:
        problems.append(f"missing columns {missing}")
    for name, spec in c.columns.items():
        if name not in df.columns:
            continue
        s = df[name]
        if not _KIND_CHECK[spec.kind](s):
            problems.append(f"{name}: dtype {s.dtype} is not {spec.kind}")
            continue
        nulls = int(s.isna().sum())
        if nulls and not spec.nullable:
            problems.append(f"{name}: {nulls} missing values")
        v = s.dropna()
        if spec.kind in ("int", "float") and len(v):
            if spec.kind == "float" and not np.isfinite(v.to_numpy()).all():
                problems.append(f"{name}: infinite values")
            if spec.lo is not None and v.min() < spec.lo:
                problems.append(f"{name}: min {v.min()} < {spec.lo}")
            if spec.hi is not None and v.max() > spec.hi:
                problems.append(f"{name}: max {v.max()} > {spec.hi}")
        if spec.values is not None:
            bad = sorted(set(v.unique()) - set(spec.values), key=str)
            if bad:
                problems.append(f"{name}: unexpected values {bad[:5]}")
    if c.key and c.key in df.columns and df[c.key].duplicated().any():
        problems.append(f"{c.key}: {int(df[c.key].duplicated().sum())} duplicates")
    if problems:
        raise ContractError(f"{contract_id} ({c.template}): " + "; ".join(problems))


def read_contract(path: Path, contract_id: str) -> pd.DataFrame:
    """Read a contract file (parquet or GeoPackage) and validate it."""
    if CONTRACTS[contract_id].geo:
        import geopandas as gpd

        df = gpd.read_file(path)
    else:
        df = pd.read_parquet(path)
    validate_frame(df, contract_id)
    return df


def validate_score_meta(path: Path) -> dict:
    """Read a C8 metadata JSON; raise if keys are missing or a feature is not a model input."""
    meta = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [k for k in SCORE_META_KEYS if k not in meta]
    if missing:
        raise ContractError(f"{path}: metadata missing {missing}")
    if meta["features"]:
        check_model_inputs(meta["features"])
    return meta


def validate_project(cfg) -> dict[str, list[Path]]:
    """Validate every contract file that exists under the configured paths.

    Also checks that every ``cell_id`` in other files exists in the grid (C1).
    Returns the files checked per contract. Missing files are skipped, so this
    works at any stage of the project.
    """
    checked: dict[str, list[Path]] = {}
    grid_ids: set[int] | None = None
    patterns = {
        "C1": [contract_path(cfg, "C1")],
        "C2": sorted(Path(cfg.paths["data_features"]).glob("raster_features_*.parquet")),
        "C3": sorted(Path(cfg.paths["data_features"]).glob("vector_features_*.parquet")),
        "C4": sorted(Path(cfg.paths["data_features"]).glob("grid_features_*.parquet")),
        "C5": [contract_path(cfg, "C5")],
        "C6": sorted(Path(cfg.paths["data_processed"]).glob("buildings_*.gpkg")),
        "C7": [contract_path(cfg, "C7")],
        "C8": sorted((Path(cfg.paths["outputs"]) / "scores").glob("*.parquet")),
    }
    for cid, paths in patterns.items():
        for p in paths:
            if not p.exists():
                continue
            df = read_contract(p, cid)
            if cid == "C1":
                grid_ids = set(df["cell_id"].tolist())
            elif grid_ids is not None and "cell_id" in df.columns:
                unknown = set(df["cell_id"].tolist()) - grid_ids
                if unknown:
                    raise ContractError(f"{p}: {len(unknown)} cell_id values not in the grid")
            if cid == "C8":
                validate_score_meta(p.with_suffix(".json"))
            checked.setdefault(cid, []).append(p)
    return checked
