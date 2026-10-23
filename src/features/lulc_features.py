"""Per-cell land-cover fractions by block aggregation of the 10 m LULC (PRD FR-4.2).

Each cell is a k × k block of reference pixels (k = cell size / 10 m), so fractions
are exact pixel counts, not polygon zonal statistics.

Fractions are shares of the **valid** pixels (not nodata, not cloud), so they sum to 1
whenever a cell has any valid pixel. ``nodata_frac`` is the share of invalid pixels.
"""

from __future__ import annotations

import numpy as np

from src.features import schema

ESRI_CODE = {name: code for code, name in schema.ESRI_CLASSES.items()}
INVALID_CODES = (schema.ESRI_NODATA, ESRI_CODE["cloud"])


def block_view(arr: np.ndarray, k: int) -> np.ndarray:
    """(rows, k, cols, k) view of a raster whose shape is a multiple of k."""
    h, w = arr.shape
    if h % k or w % k:
        raise ValueError(f"raster shape {arr.shape} is not a multiple of {k}")
    return arr.reshape(h // k, k, w // k, k)


def block_mean(arr: np.ndarray, k: int) -> np.ndarray:
    """Mean of each k x k block (one value per cell)."""
    return block_view(arr, k).mean(axis=(1, 3))


def block_max(arr: np.ndarray, k: int) -> np.ndarray:
    """Maximum of each k x k block (one value per cell)."""
    return block_view(arr, k).max(axis=(1, 3))


def class_fractions(lulc: np.ndarray, k: int) -> dict[str, np.ndarray]:
    """``frac_<class>`` for every class in schema.OWN_FRACTION_CLASSES, plus ``nodata_frac``."""
    invalid = np.isin(lulc, INVALID_CODES)
    n_valid = block_view(~invalid, k).sum(axis=(1, 3)).astype("float64")
    safe = np.where(n_valid > 0, n_valid, 1.0)
    out = {}
    for name in schema.OWN_FRACTION_CLASSES:
        count = block_view(lulc == ESRI_CODE[name], k).sum(axis=(1, 3))
        out[f"frac_{name}"] = np.where(n_valid > 0, count / safe, 0.0)
    out["nodata_frac"] = 1.0 - n_valid / (k * k)
    return out
