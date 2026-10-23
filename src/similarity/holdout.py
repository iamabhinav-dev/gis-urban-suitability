"""Held-out building check (PRD FR-8.2, §9.8; Tasks P6.6).

Do surroundings identify building locations in areas a model never saw? Grid cells are
grouped in ``validation.spatial_block_m`` blocks and dealt to ``rf.n_folds`` folds (as in
``rf_model``). For each fold, a scorer learns from the reference cells (P6.2) **outside**
the fold and scores every non-excluded cell **inside** it. Each held-out reference cell
gets the percentile rank of its score among those cells (100 = top). Reported per scorer:
median percentile, share in the top 10 % and top 30 % (chance: 50 / 10 % / 30 %), the
best median any scorer could reach (references fill the top ranks: 100 - share / 2, so
about 70 when references are 60 % of the cells) and the ROC-AUC of reference vs other
cells in the held-out blocks (scale-free; ties count half).

Scorers (all on ``schema.MODEL_INPUTS`` of the run year, never own-cell features):

- ``dist_to_built``: minus the distance to the nearest built pixel outside the cell (no
  training; the baseline);
- ``rf``: random forest, reference vs other cells (percentile features as in rf_model);
- ``knn``: minus the mean Euclidean distance to the ``similarity.knn_k`` nearest training
  reference profiles (z-scores), all inputs. A minimal stand-in for the P6.4 aggregate;
- ``knn_ring500``: the same without the 250 m rings (notebook 03: the 250 / 500 m pairs
  correlate at r 0.91-0.95, so all inputs weight ring context about twice).

Output: ``outputs/metrics/similarity.json`` → ``holdout.{run}``.

Run: python -m src.similarity.holdout [--run validation|final]
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Callable

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from src.classify.cluster import RUNS, run_year
from src.config import load_config
from src.features import schema
from src.io_utils import setup_logging
from src.similarity import reference as rs
from src.similarity import rf_model as rm
from src.similarity.aggregate import knn_mean_distance

log = logging.getLogger(__name__)

Scorer = Callable[
    [pd.DataFrame, np.ndarray, np.ndarray], np.ndarray
]  # (X, train_ref_ids, score_ids)
SCORERS = ("dist_to_built", "rf", "knn", "knn_ring500")


def _knn(cfg, cols: list[str]) -> Scorer:
    def score(X: pd.DataFrame, train_ref: np.ndarray, ids: np.ndarray) -> np.ndarray:
        Z = X[cols]
        Z = (Z - Z.mean()) / Z.std(ddof=0).replace(0, 1)
        k = int(cfg["similarity"]["knn_k"])
        d = knn_mean_distance(
            Z.loc[train_ref].to_numpy(),
            np.asarray(train_ref),
            Z.loc[ids].to_numpy(),
            np.asarray(ids),
            k,
        )
        return -d

    return score


def _rf(cfg, seed: int) -> Scorer:
    def score(X: pd.DataFrame, train_ref: np.ndarray, ids: np.ndarray) -> np.ndarray:
        Xp = X.round(rm.ROUND_DECIMALS).rank(pct=True)
        train = Xp.index.difference(pd.Index(ids))  # cells outside the fold
        y = train.isin(train_ref).astype(int)
        rf = rm.make_rf(cfg, {"min_samples_leaf": 5, "max_features": "sqrt"}, seed)
        rf.fit(Xp.loc[train].to_numpy(), y)
        return rf.predict_proba(Xp.loc[ids].to_numpy())[:, 1]

    return score


def scorers(cfg) -> dict[str, Scorer]:
    """The built-in scorers, by name (see the module docstring)."""
    seed = int(cfg["project"]["random_seed"])
    cols = list(schema.MODEL_INPUTS)
    return {
        "dist_to_built": lambda X, _train_ref, ids: -X.loc[ids, "log_dist_built"].to_numpy(),
        "rf": _rf(cfg, seed),
        "knn": _knn(cfg, cols),
        "knn_ring500": _knn(cfg, [c for c in cols if not c.startswith("ring250_")]),
    }


def holdout_ranks(cfg, run: str, scorer: Scorer) -> pd.DataFrame:
    """Percentile rank (0-100) within its fold of every held-out cell, with ``is_ref``."""
    seed = int(cfg["project"]["random_seed"])
    X = schema.read_contract(schema.contract_path(cfg, "C4", year=run_year(cfg, run)), "C4")
    X = X.set_index("cell_id")[list(schema.MODEL_INPUTS)]
    schema.check_model_inputs(list(X.columns))
    excl = pd.read_parquet(schema.contract_path(cfg, "C5").parent / f"exclusion_{run}.parquet")
    keep = X.index.isin(excl.loc[~excl["excluded"], "cell_id"])
    X = X.loc[keep]
    ref = rs.reference_cells(cfg, run)
    is_ref = X.index.isin(ref["cell_id"])
    folds = rm.assign_folds(rm.spatial_blocks(cfg, X.index), int(cfg["rf"]["n_folds"]), seed)
    out = []
    for f in np.unique(folds):
        ids = X.index[folds == f].to_numpy()
        train_ref = X.index[(folds != f) & is_ref].to_numpy()
        s = pd.Series(scorer(X, train_ref, ids), index=ids)
        pct = 100 * s.rank(pct=True)
        out.append(
            pd.DataFrame(
                {
                    "cell_id": ids,
                    "fold": f,
                    "is_ref": is_ref[folds == f],
                    "percentile": pct.to_numpy(),
                }
            )
        )
    return pd.concat(out, ignore_index=True)


def summarise(ranks: pd.DataFrame) -> dict:
    """Metrics over the held-out reference cells (``is_ref``); AUC per fold, averaged."""
    ref = ranks.loc[ranks["is_ref"]]
    p = ref["percentile"]
    aucs = []
    for _, g in ranks.groupby("fold"):
        y = g["is_ref"].to_numpy()
        if 0 < y.sum() < len(y):
            aucs.append(float(roc_auc_score(y, g["percentile"].to_numpy())))
    share = float(ranks["is_ref"].mean())
    return {
        "n_held_out": int(len(p)),
        "reference_share": share,
        "median_percentile": float(p.median()),
        "best_possible_median": 100 * (1 - share / 2),
        "share_top10": float((p > 90).mean()),
        "share_top30": float((p > 70).mean()),
        "auc": float(np.mean(aucs)) if aucs else float("nan"),
        "median_by_fold": [float(v) for v in ref.groupby("fold")["percentile"].median()],
    }


def run_holdout(cfg, run: str = "validation", names: list[str] | None = None) -> dict[str, dict]:
    """Held-out summary for each scorer (``names``: a subset)."""
    res = {}
    for name, sc in scorers(cfg).items():
        if names and name not in names:
            continue
        res[name] = summarise(holdout_ranks(cfg, run, sc))
        log.info(
            "%s %s: AUC %.3f, median percentile %.1f (best possible %.1f), top 10 %% %.1f %%",
            run, name, res[name]["auc"], res[name]["median_percentile"],
            res[name]["best_possible_median"], 100 * res[name]["share_top10"],
        )  # fmt: skip
    return res


def write_holdout(cfg, run: str = "validation") -> dict:
    """Run the check and store it in ``similarity.json`` under ``holdout.{run}``."""
    res = run_holdout(cfg, run)
    p = rm.metrics_path(cfg)
    allm = json.loads(p.read_text()) if p.exists() else {}
    allm.setdefault("holdout", {})[run] = {
        "reference_source": cfg["similarity"].get("reference_source", "osm+esri"),
        "scorers": res,
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(allm, indent=1, allow_nan=False))
    return res


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="validation", choices=RUNS)
    args = parser.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "similarity")
    write_holdout(cfg, args.run)


if __name__ == "__main__":
    main()
