"""Sensitivity analysis (Tasks P7.6): how do the results change with the main settings?

Three experiments, each against the project defaults (slope 15°, k = 7, 100 m cells):

- **slope threshold** (``exclusion.slope_max_deg`` and ``mcda.slope_zero_deg``): exclusion
  mask and labels rebuilt in memory; reported: excluded / candidate / grown cells and the
  temporal AUC (validation run, ``grew``) of distance-to-built, MCDA and rf_change;
- **k** (``clustering.k``): final-run clustering and labelling in memory; reported:
  silhouette, Davies-Bouldin, class shares and agreement with ESRI / WorldCover;
- **cell size** (``grid.cell_size_m``): the whole feature and label chain rebuilt in a
  separate project under ``outputs/sensitivity/cell_{m}/`` (processed rasters and raw OSM
  layers linked, or
  cropped by 10 px at the bottom edge of the buffer when the grid isn't a multiple of
  the cell); reported as for the slope threshold. The processed buildings keep their
  100 m cell ids, so building counts (leaky, used by no model) are wrong there.

rf_change is refitted out of fold with the tuned parameters from ``similarity.json``
(no re-tuning). Nothing in the main project is overwritten. Output:
``outputs/metrics/sensitivity.json``.

Run: python -m src.suitability.sensitivity [--only slope|k|cell]
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

import pandas as pd
import rasterio
import yaml
from rasterio.windows import Window
from sklearn.metrics import roc_auc_score

from src.classify import cluster as cl
from src.classify import evaluate as ev
from src.classify.label import X, rule_table
from src.config import DEFAULT_CONFIG_PATH, load_config
from src.features import labels as fl
from src.features import schema
from src.features.build import write_feature_tables
from src.features.distance import write_vector_features
from src.features.grid import write_grid
from src.features.raster_features import write_raster_features
from src.io_utils import setup_logging
from src.preprocess.raster import processed_dir, reference_grid_path
from src.similarity import rf_model as rm
from src.suitability import mcda

log = logging.getLogger(__name__)

SLOPES = (10, 15, 20)
KS = (5, 6, 7, 8)
CELLS = (50, 100, 200)


# ---------------------------------------------------------------- shared metrics


def temporal_aucs(cfg, labels: pd.DataFrame) -> dict:
    """AUC on ``grew`` (validation run) of distance-to-built, MCDA and out-of-fold rf_change."""
    lab = labels.set_index("cell_id")
    cand = lab.index[lab["candidate"]]
    keep = ~lab.loc[cand, "ambiguous"].to_numpy()
    y = lab.loc[cand, "grew"].to_numpy()[keep]
    base = cfg["years"]["baseline"]
    c4 = schema.read_contract(schema.contract_path(cfg, "C4", year=base), "C4").set_index("cell_id")
    out = {
        "n_candidates": int(len(cand)),
        "n_scored": int(keep.sum()),
        "n_grew": int(y.sum()),
        "auc_dist_to_built": float(
            roc_auc_score(y, -c4.loc[cand, "log_dist_built"].to_numpy()[keep])
        ),
        "auc_mcda": float(
            roc_auc_score(y, mcda.mcda_scores(cfg, base, cand)["score"].to_numpy()[keep])
        ),
    }
    # rf_change, out of fold, tuned parameters frozen
    params = json.loads(rm.metrics_path(load_config()).read_text())["rf_change"]["best_params"]
    seed = int(cfg["project"]["random_seed"])
    ids, yt = rm.training_set(labels, "rf_change")
    feats = rm.model_features(cfg, base)
    folds = rm.assign_folds(rm.spatial_blocks(cfg, ids), int(cfg["rf"]["n_folds"]), seed)
    cv = rm.cross_validate(cfg, feats.loc[ids].to_numpy(), yt, folds, params, seed)
    oof = pd.Series(cv["oof"], index=ids).loc[cand].to_numpy()[keep]
    out["auc_rf_change"] = float(roc_auc_score(y, oof))
    out["n_chg_train_pos"] = int(yt.sum())
    return out


# ---------------------------------------------------------------- experiments


def slope_sensitivity(slopes=SLOPES) -> list[dict]:
    """Labels and temporal AUCs for each slope threshold."""
    rows = []
    for s in slopes:
        cfg = load_config()
        cfg["exclusion"]["slope_max_deg"] = s
        cfg["mcda"]["slope_zero_deg"] = s
        labels, excl = fl.build_labels_and_mask(cfg)
        row = {
            "slope_max_deg": s,
            "n_excluded": int(excl["excluded"].sum()),
            "n_excl_slope": int(excl["excl_slope"].sum()),
        }
        row.update(temporal_aucs(cfg, labels))
        log.info("slope %s: %s", s, row)
        rows.append(row)
    return rows


def k_sensitivity(ks=KS) -> list[dict]:
    """Cluster quality, class shares and agreement for each k (final run)."""
    rows = []
    for k in ks:
        cfg = load_config()
        cfg["clustering"]["k"] = k
        res = cl.cluster_run(cfg, "final", do_scan=False)
        a = res["assignments"]
        rules = rule_table(cfg, "final", a)
        excl = fl.exclusion_table(cfg, "final")
        c7 = a.copy()
        c7["class_3"] = c7["cluster_id"].map(rules["class_3"]).astype("int64")
        c7.loc[c7["cell_id"].isin(excl.loc[excl["excluded"], "cell_id"]), "class_3"] = X
        e = ev.evaluate(cfg, c7, "final")
        shares = c7["class_3"].map(ev.NAMES).value_counts(normalize=True)
        row = {
            "k": k,
            "silhouette": res["chosen"]["silhouette"],
            "davies_bouldin": res["chosen"]["davies_bouldin"],
            **{f"share_{n}": float(shares.get(n, 0.0)) for n in ev.NAMES.values()},
            "agreement_esri_land": e[f"esri_{cl.run_year(cfg, 'final')}"]["land"]["agreement"],
            "agreement_worldcover_land": e[f"worldcover_{cfg['lulc']['worldcover_check']}"]["land"][
                "agreement"
            ],
            "cluster_rules": rules["rule"].tolist(),
        }
        log.info("k %s: %s", k, {kk: v for kk, v in row.items() if kk != "cluster_rules"})
        rows.append(row)
    return rows


def cell_project(cell: int) -> Path:
    """A separate project with ``grid.cell_size_m = cell`` under outputs/sensitivity/."""
    main = load_config()
    root = Path(main.paths["outputs"]) / "sensitivity" / f"cell_{cell}"
    proc = root / "data" / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(exist_ok=True)
    shutil.copy(main.root / main["aoi"]["path"], root / "config" / "aoi.geojson")
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    raw["grid"]["cell_size_m"] = cell
    raw["aoi"]["path"] = "config/aoi.geojson"
    (root / "config" / "config.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")

    ref = json.loads(reference_grid_path(main).read_text())
    k = int(round(cell / ref["pixel_m"]))
    h, w = ref["height"] - ref["height"] % k, ref["width"] - ref["width"] % k
    src = processed_dir(main)
    for tif in sorted(src.glob("*.tif")):
        dst = proc / tif.name
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        if (h, w) == (ref["height"], ref["width"]):
            dst.symlink_to(tif)
            continue
        with rasterio.open(tif) as ds:
            prof = ds.profile | {"height": h, "width": w}
            with rasterio.open(dst, "w", **prof) as out:
                out.write(ds.read(1, window=Window(0, 0, w, h)), 1)
    for name in ("osm", "buildings_2018.gpkg", "buildings_current.gpkg"):
        dst = proc / name
        if not (dst.exists() or dst.is_symlink()):
            dst.symlink_to(src / name)
    # the exclusion mask reads OSM lakes and protected areas from the raw downloads
    raw_osm = root / "data" / "raw" / "osm"
    if not (raw_osm.exists() or raw_osm.is_symlink()):
        raw_osm.parent.mkdir(parents=True, exist_ok=True)
        raw_osm.symlink_to(Path(main.paths["data_raw"]) / "osm")
    left, top = ref["transform"][2], ref["transform"][5]
    ref.update(
        cell_size_m=float(cell),
        height=h,
        width=w,
        bounds=[left, top - h * ref["pixel_m"], left + w * ref["pixel_m"], top],
    )
    (proc / "reference_grid.json").write_text(json.dumps(ref, indent=1))
    return root / "config" / "config.yaml"


def cell_sensitivity(cells=CELLS) -> list[dict]:
    """Temporal AUCs with features and labels rebuilt at each cell size."""
    rows = []
    for cell in cells:
        if cell == load_config().cell_size_m:
            cfg = load_config()
            labels = schema.read_contract(schema.contract_path(cfg, "C5"), "C5")
        else:
            cfg = load_config(cell_project(cell))
            cfg.ensure_dirs()
            write_grid(cfg)
            write_raster_features(cfg)
            write_vector_features(cfg)
            write_feature_tables(cfg)
            labels, _ = fl.build_labels_and_mask(cfg)
        row = {"cell_size_m": cell, "n_cells": int(len(labels))}
        row.update(temporal_aucs(cfg, labels))
        log.info("cell %s m: %s", cell, row)
        rows.append(row)
    return rows


def write_sensitivity(only: list[str] | None = None) -> dict:
    """Run the experiments (``only``: a subset) and merge them into ``sensitivity.json``."""
    p = Path(load_config().paths["metrics"]) / "sensitivity.json"
    res = json.loads(p.read_text()) if p.exists() else {}
    runs = {"slope": slope_sensitivity, "k": k_sensitivity, "cell": cell_sensitivity}
    for name, fn in runs.items():
        if only and name not in only:
            continue
        res[name] = fn()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(res, indent=1, allow_nan=False))
    return res


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", choices=("slope", "k", "cell"))
    args = parser.parse_args(argv)
    setup_logging(load_config(), "suitability")
    write_sensitivity(args.only)


if __name__ == "__main__":
    main()
