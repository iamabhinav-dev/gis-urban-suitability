"""Combined suitability score and classes S1-S3 / N (PRD FR-7.2, FR-7.3; Tasks P7.1).

Score = weighted mean of the building similarity (``similarity_knn``) and the change
random forest (``rf_change``). The two are on very different scales (RF probabilities
sit mostly near 0), so each is first turned into its percentile among the run's scored
cells; the weight then means what it says.

**Weight.** Chosen on the validation run and frozen for the final run (FR-7.2), but on
the change RF's *training* label (cells built in 2020/21, ``chg_train_pos``) with the
RF's out-of-fold scores, never on the 2022/23 ``grew`` label used to validate. The grid
is ``suitability.weight_grid`` (weight of the similarity); ties go to the weight
closest to 0.5.

**Classes** among the run's scored cells (candidates in the validation run, usable cells
in the final run): S1 >= q90, S2 >= q70, S3 >= q40, else N (``suitability.class_quantiles``).
Forest, built-up and excluded cells are always N.

Outputs: C8 ``outputs/scores/suitability.parquet`` (validation) and
``outputs/final/scores/suitability.parquet``; ``outputs/suitability_classes_{run}.parquet``
(cell_id, score, class); ``outputs/suitability_score.tif`` (final, NaN outside usable land)
and ``outputs/suitability_class.tif`` (1 S1, 2 S2, 3 S3, 4 N on every AOI cell, 0 outside);
``outputs/metrics/suitability.json`` (weight table, frozen weight, class counts).

Run: python -m src.suitability.score
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from sklearn.metrics import roc_auc_score

from src.classify.export import lattice_transform
from src.config import load_config
from src.features import schema
from src.features.grid import lattice
from src.io_utils import setup_logging
from src.similarity import profiles as pf
from src.similarity.rf_model import scores_path, write_probability_raster

log = logging.getLogger(__name__)

MODEL = "suitability"
COMPONENTS = ("similarity_knn", "rf_change")
S1, S2, S3, N = 1, 2, 3, 4
CLASS_NAMES = {S1: "S1", S2: "S2", S3: "S3", N: "N"}
NODATA = 0


def component_ranks(cfg, run: str) -> pd.DataFrame:
    """Within-run percentile of each component score, on the run's scored cells."""
    ids = pf.candidate_cells(cfg, run)
    out = pd.DataFrame(index=pd.Index(np.sort(ids), name="cell_id"))
    for model in COMPONENTS:
        s = pd.read_parquet(scores_path(cfg, model, run)).set_index("cell_id")["score"]
        missing = out.index.difference(s.index)
        if len(missing):
            raise ValueError(f"{model} ({run}) has no score for {len(missing)} cells: rerun it")
        out[model] = s.loc[out.index].rank(pct=True)
    return out


def combine(ranks: pd.DataFrame, w_similarity: float) -> pd.Series:
    """Weighted mean of the percentile ranks (weight of the similarity)."""
    return w_similarity * ranks["similarity_knn"] + (1 - w_similarity) * ranks["rf_change"]


def choose_weight(cfg) -> tuple[float, list[dict]]:
    """Similarity weight with the best AUC on the 2020/21 training label (validation run)."""
    ranks = component_ranks(cfg, "validation")
    lab = schema.read_contract(schema.contract_path(cfg, "C5"), "C5").set_index("cell_id")
    y = lab.loc[ranks.index, "chg_train_pos"].to_numpy()
    table = []
    for w in cfg["suitability"]["weight_grid"]:
        table.append(
            {
                "w_similarity": float(w),
                "auc_chg_train_pos": float(roc_auc_score(y, combine(ranks, float(w)))),
            }
        )
    best = max(
        table, key=lambda r: (round(r["auc_chg_train_pos"], 4), -abs(r["w_similarity"] - 0.5))
    )
    return best["w_similarity"], table


def classify(score: pd.Series, quantiles) -> pd.Series:
    """S1-S3 / N by quantiles of the scored cells (``quantiles``: q90, q70, q40)."""
    q1, q2, q3 = (score.quantile(q) for q in quantiles)
    cls = np.select([score >= q1, score >= q2, score >= q3], [S1, S2, S3], default=N)
    return pd.Series(cls.astype("int64"), index=score.index, name="class")


def classes_path(cfg, run: str) -> Path:
    return Path(cfg.paths["outputs"]) / f"suitability_classes_{run}.parquet"


def score_tif_path(cfg) -> Path:
    return Path(cfg.paths["outputs"]) / "suitability_score.tif"


def class_tif_path(cfg) -> Path:
    return Path(cfg.paths["outputs"]) / "suitability_class.tif"


def metrics_path(cfg) -> Path:
    return Path(cfg.paths["metrics"]) / "suitability.json"


def write_class_raster(cfg, classes: pd.Series, path: Path) -> Path:
    """Classes of the scored cells; every other AOI cell is N; 0 outside the AOI."""
    lat = lattice(cfg)
    grid = schema.read_contract(schema.contract_path(cfg, "C1"), "C1").set_index("cell_id")
    img = np.full(lat.shape, NODATA, dtype="uint8")
    img[grid["row"].to_numpy(), grid["col"].to_numpy()] = N
    g = grid.loc[classes.index]
    img[g["row"].to_numpy(), g["col"].to_numpy()] = classes.to_numpy().astype("uint8")
    profile = {
        "driver": "GTiff",
        "height": img.shape[0],
        "width": img.shape[1],
        "count": 1,
        "dtype": "uint8",
        "crs": cfg.crs,
        "transform": lattice_transform(lat),
        "nodata": NODATA,
        "compress": "deflate",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as ds:
        ds.write(img, 1)
        ds.update_tags(1, **{str(k): v for k, v in CLASS_NAMES.items()})
    return path


def write_suitability(cfg) -> dict:
    """Choose and freeze the weight, score and classify both runs, write all outputs."""
    w, table = choose_weight(cfg)
    quantiles = cfg["suitability"]["class_quantiles"]
    report = {
        "components": list(COMPONENTS),
        "scale": "within-run percentile",
        "weight_label": "chg_train_pos (validation run, out-of-fold rf_change)",
        "weight_table": table,
        "w_similarity": w,
        "w_rf_change": round(1 - w, 6),
        "class_quantiles": quantiles,
    }
    for run in ("validation", "final"):
        score = combine(component_ranks(cfg, run), w)
        cls = classify(score, quantiles)
        c8 = pd.DataFrame({"cell_id": score.index.to_numpy(), "score": score.to_numpy()})
        schema.validate_frame(c8, "C8")
        p = scores_path(cfg, MODEL, run)
        p.parent.mkdir(parents=True, exist_ok=True)
        c8.to_parquet(p, index=False)
        meta = {
            "model": MODEL,
            "features": list(schema.MODEL_INPUTS),
            "train_years": [int(cfg["years"]["baseline"]), *cfg["years"]["change_train_end"]],
            "description": f"{w:.2f} x similarity_knn + {1 - w:.2f} x rf_change"
            " (within-run percentiles)",
            "run": run,
            "w_similarity": w,
        }
        p.with_suffix(".json").write_text(json.dumps(meta, indent=1))
        if run == "validation":
            schema.validate_score_meta(p.with_suffix(".json"))
        pd.DataFrame(
            {"cell_id": score.index, "score": score.to_numpy(), "class": cls.to_numpy()}
        ).to_parquet(classes_path(cfg, run), index=False)
        report[f"class_counts_{run}"] = {
            CLASS_NAMES[k]: int(v) for k, v in cls.value_counts().sort_index().items()
        }
        if run == "final":
            write_probability_raster(cfg, c8, score_tif_path(cfg))
            write_class_raster(cfg, cls, class_tif_path(cfg))
    mp = metrics_path(cfg)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(report, indent=1, allow_nan=False))
    log.info(
        "weight: similarity %.2f / rf_change %.2f; final classes %s",
        w,
        1 - w,
        report["class_counts_final"],
    )
    return report


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "suitability")
    write_suitability(cfg)


if __name__ == "__main__":
    main()
