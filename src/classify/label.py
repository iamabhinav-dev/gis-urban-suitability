"""Map clusters to built-up / forest / usable / excluded (contract C7) (PRD FR-5.4, FR-5.5, §9.4).

Cluster-level rules, on the cluster means of the run's own-cell fractions (C4), checked
in this order (thresholds in ``config.yaml → labeling``):

1. **water** (excluded): water + flooded >= ``water_threshold``;
2. **built-up**: built >= ``built_threshold`` **and** built is the cluster's largest land
   group (built vs trees vs crop + rangeland + bare). A share threshold alone would flip
   the mixed crop/built western valley between years (13 % built in 2018, 31 % in 2023);
3. **forest**: trees >= ``forest_threshold``;
4. **forest (steep natural vegetation)**: trees + rangeland >= ``forest_threshold`` and
   mean slope >= ``steep_natural_slope_deg``. In this AOI that is the Bannerghatta hills:
   dry deciduous forest and scrub that ESRI maps as rangeland (P5.4 caveat);
5. otherwise **usable**; a cropland-dominated usable cluster is flagged ``agricultural``
   (decision D10: usable, but flagged).

Cell-level, applied last (FR-5.5): cells in the run's exclusion mask
(``features.labels.exclusion_table``: wet, steep, nodata, protected) become 255, and grid
cells without a cluster (dropped for nodata) become 255 with ``cluster_id = -1``.

Two runs (FR-5.8, time-travel rule): ``final`` (latest-year features, today's mask) is
written to the C7 contract path; ``validation`` (baseline-year features, mask from data
<= baseline_confirm) to ``outputs/lulc_3class_validation.parquet`` with the same columns.
Also written per run: ``metrics/class_rules_{run}.csv`` (each cluster, its means and the
rule that fired) and ``exclusion_mask[_validation].tif`` (1 excluded, 0 kept, 255 outside
the AOI) on the 100 m cell lattice.

Run: python -m src.classify.label [--run validation|final]
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from src.classify import cluster as cl
from src.classify.evaluate import NAMES
from src.classify.export import lattice_transform
from src.config import load_config
from src.features import schema
from src.features.grid import lattice
from src.features.labels import exclusion_table
from src.io_utils import setup_logging

log = logging.getLogger(__name__)

B, F, U, X = schema.CLASS_BUILT, schema.CLASS_FOREST, schema.CLASS_USABLE, schema.CLASS_EXCLUDED
MASK_OUTSIDE = 255


def _frac(c: pd.Series, name: str) -> float:
    return float(c.get(f"frac_{name}", 0.0))


def classify_cluster(c: pd.Series, rules: dict) -> tuple[int, str, str]:
    """(class_3, rule, flag) for one cluster's mean fractions and slope."""
    built, tree = _frac(c, "built"), _frac(c, "tree")
    crop, rng = _frac(c, "crop"), _frac(c, "range")
    usable_land = crop + rng + _frac(c, "bare")
    wet = _frac(c, "water") + _frac(c, "flooded")
    slope = float(c.get("slope_mean", 0.0))
    if wet >= float(rules["water_threshold"]):
        return X, "water", ""
    if built >= float(rules["built_threshold"]) and built >= max(tree, usable_land):
        return B, "built", ""
    if tree >= float(rules["forest_threshold"]):
        return F, "trees", ""
    if tree + rng >= float(rules["forest_threshold"]) and slope >= float(
        rules["steep_natural_slope_deg"]
    ):
        return F, "steep natural vegetation", ""
    flag = "agricultural" if crop >= max(rng, built, tree) else ""
    if flag and not rules.get("cropland_usable", True):
        return X, "cropland excluded (labeling.cropland_usable = false)", flag
    return U, "usable", flag


def cluster_means(cfg, run: str, assignments: pd.DataFrame) -> pd.DataFrame:
    """Mean own-cell fractions and slope per cluster, from the run's feature table."""
    year = cl.run_year(cfg, run)
    c4 = schema.read_contract(schema.contract_path(cfg, "C4", year=year), "C4")
    cols = [*schema.OWN_FRACTIONS, "slope_mean", "elev_mean"]
    df = assignments.merge(c4[["cell_id", *cols]], on="cell_id", how="inner", validate="1:1")
    means = df.groupby("cluster_id")[cols].mean()
    means.insert(0, "n_cells", df.groupby("cluster_id").size())
    means.insert(1, "share", means["n_cells"] / len(df))
    return means


def rule_table(cfg, run: str, assignments: pd.DataFrame) -> pd.DataFrame:
    """Cluster means with the class, rule and flag each cluster gets."""
    means = cluster_means(cfg, run, assignments)
    rules = cfg["labeling"]
    out = [classify_cluster(row, rules) for _, row in means.iterrows()]
    means["class_3"] = [o[0] for o in out]
    means["class_name"] = means["class_3"].map(NAMES)
    means["rule"] = [o[1] for o in out]
    means["flag"] = [o[2] for o in out]
    return means


def label_run(cfg, run: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(C7 frame, rule table, exclusion table) for one run."""
    p = cl.clusters_path(cfg, run)
    if not p.exists():
        raise FileNotFoundError(f"{p} missing: run python -m src.classify.cluster first")
    assignments = pd.read_parquet(p)
    rules = rule_table(cfg, run, assignments)
    grid = schema.read_contract(schema.contract_path(cfg, "C1"), "C1")
    excl = exclusion_table(cfg, run)

    df = grid[["cell_id"]].merge(assignments, on="cell_id", how="left", validate="1:1")
    df["cluster_id"] = df["cluster_id"].fillna(-1).astype("int64")
    df["class_3"] = df["cluster_id"].map(rules["class_3"]).fillna(X).astype("int64")
    excluded = df["cell_id"].isin(excl.loc[excl["excluded"], "cell_id"])
    df.loc[excluded, "class_3"] = X
    schema.validate_frame(df, "C7")
    return df, rules, excl


def c7_path(cfg, run: str) -> Path:
    p = schema.contract_path(cfg, "C7")
    return p if run == "final" else p.with_name(f"{p.stem}_{run}{p.suffix}")


def rules_path(cfg, run: str) -> Path:
    return Path(cfg.paths["metrics"]) / f"class_rules_{run}.csv"


def mask_path(cfg, run: str) -> Path:
    suffix = "" if run == "final" else f"_{run}"
    return Path(cfg.paths["outputs"]) / f"exclusion_mask{suffix}.tif"


def write_exclusion_mask(cfg, excl: pd.DataFrame, path: Path) -> Path:
    """1 excluded, 0 kept, 255 outside the AOI, on the 100 m cell lattice (P5.5)."""
    lat = lattice(cfg)
    grid = schema.read_contract(schema.contract_path(cfg, "C1"), "C1")
    g = grid.merge(excl[["cell_id", "excluded"]], on="cell_id", how="left", validate="1:1")
    img = np.full(lat.shape, MASK_OUTSIDE, dtype="uint8")
    img[g["row"], g["col"]] = g["excluded"].fillna(True).astype("uint8")
    profile = {
        "driver": "GTiff", "height": img.shape[0], "width": img.shape[1], "count": 1,
        "dtype": "uint8", "crs": cfg.crs, "transform": lattice_transform(lat),
        "nodata": MASK_OUTSIDE, "compress": "deflate",
    }  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as ds:
        ds.write(img, 1)
        ds.update_tags(1, **{"0": "kept", "1": "excluded"})
    return path


def write_labels(cfg, runs: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Label both runs (or ``runs``); write C7, the rule tables and the exclusion masks."""
    out = {}
    for run in runs or list(cl.RUNS):
        c7, rules, excl = label_run(cfg, run)
        p = c7_path(cfg, run)
        p.parent.mkdir(parents=True, exist_ok=True)
        c7.to_parquet(p, index=False)
        rp = rules_path(cfg, run)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rules.round(4).to_csv(rp)
        write_exclusion_mask(cfg, excl, mask_path(cfg, run))
        shares = c7["class_3"].map(NAMES).value_counts(normalize=True).round(3).to_dict()
        log.info("%s: %s -> %s", run, shares, p.name)
        for cid, r in rules.iterrows():
            log.info(
                "  cluster %d (%.1f %%): %s via '%s'%s",
                cid, 100 * r["share"], r["class_name"], r["rule"],
                f" [{r['flag']}]" if r["flag"] else "",
            )  # fmt: skip
        out[run] = c7
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", choices=cl.RUNS, help="default: both")
    args = parser.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "classify")
    write_labels(cfg, args.run)


if __name__ == "__main__":
    main()
