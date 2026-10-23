"""Validation harness: every score, tested the same way against real growth (PRD FR-8; Tasks P7.4).

Evaluation set (validation run, PRD §9.6): candidate cells (non-built in 2018 and 2019,
not excluded) that are not ``ambiguous``; positive = ``grew`` (built in 2022 and 2023).

For every C8 file in ``outputs/scores/`` (all computed as of 2018; trained models out of
fold) plus two baselines added automatically (FR-8.4): ``random`` (seeded uniform) and
``dist_to_built`` (minus the 2018 distance to built-up land):

- **AUC** (ROC);
- **top-N**: in the top 10 % and 30 % of scores, precision (hit rate), recall and
  **lift** = precision / prevalence (target: lift >= 2 in the top 10 %);
- **TOC** curve (Pontius & Si 2014): hits vs cells flagged, 101 points;
- **AUC by growth type** (LEI): adjacent growth vs all non-growth, outlying growth vs
  all non-growth.

For the combined ``suitability`` score also the **S1 + S2 hit rate**: the share of grown
cells that the validation-run classes put in S1 or S2 (30 % of the cells by
construction), with its precision and lift.

**Group ablation** (FR-8.5): each ``schema.ABLATION_GROUPS`` group is dropped in turn
from the inputs of ``rf_change`` (refitted out of fold with the frozen parameters) and of
``similarity_knn``; the AUC change shows which surroundings carry the signal.

Output: ``outputs/metrics/validation.json``.

Run: python -m src.suitability.validate [--no-ablation]
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from src.config import load_config
from src.features import schema
from src.io_utils import setup_logging
from src.similarity import aggregate as ag
from src.similarity import rf_model as rm
from src.suitability.score import S1, S2, classes_path

log = logging.getLogger(__name__)

TOP_FRACTIONS = (0.10, 0.30)
TOC_POINTS = 101
BASELINES = ("random", "dist_to_built")


def eval_set(cfg) -> pd.DataFrame:
    """Candidate, non-ambiguous cells with ``grew`` and ``lei_type``, indexed by cell_id."""
    lab = schema.read_contract(schema.contract_path(cfg, "C5"), "C5").set_index("cell_id")
    keep = lab["candidate"] & ~lab["ambiguous"]
    return lab.loc[keep, ["grew", "lei_type"]]


def model_scores(cfg, cells: pd.Index) -> dict[str, pd.Series]:
    """Every validation-run C8 score on ``cells``, plus the two baselines."""
    out = {}
    for p in sorted((Path(cfg.paths["outputs"]) / "scores").glob("*.parquet")):
        s = schema.read_contract(p, "C8").set_index("cell_id")["score"]
        missing = cells.difference(s.index)
        if len(missing):
            raise ValueError(f"{p.name} has no score for {len(missing)} evaluation cells")
        out[p.stem] = s.loc[cells]
    rng = np.random.default_rng(int(cfg["project"]["random_seed"]))
    out["random"] = pd.Series(rng.random(len(cells)), index=cells)
    c4 = schema.read_contract(
        schema.contract_path(cfg, "C4", year=int(cfg["years"]["baseline"])), "C4"
    )
    out["dist_to_built"] = -c4.set_index("cell_id").loc[cells, "log_dist_built"]
    return out


def top_n(y: np.ndarray, s: np.ndarray, frac: float) -> dict[str, float]:
    """Precision, recall and lift among the top ``frac`` of scores (ties broken at random)."""
    n = max(1, int(round(frac * len(s))))  # at least one cell
    order = np.lexsort((np.random.default_rng(0).random(len(s)), -s))[:n]
    hits = int(y[order].sum())
    prec = hits / n
    return {"precision": prec, "recall": hits / int(y.sum()), "lift": prec / y.mean()}


def toc_curve(y: np.ndarray, s: np.ndarray, points: int = TOC_POINTS) -> dict[str, list[float]]:
    """TOC: share of cells flagged (x) vs hits (y, as a share of all growth), by threshold."""
    order = np.argsort(-s, kind="stable")
    cum = np.concatenate([[0], np.cumsum(y[order])])
    idx = np.linspace(0, len(s), points).round().astype(int)
    return {
        "flagged": (idx / len(s)).round(4).tolist(),
        "hits": (cum[idx] / y.sum()).round(4).tolist(),
    }


def evaluate_score(y: np.ndarray, s: np.ndarray, lei: np.ndarray) -> dict:
    """Every metric of one score (AUC, top-N, growth-type AUC)."""
    out = {"auc": float(roc_auc_score(y, s)), "n_scored": int(len(s))}
    for frac in TOP_FRACTIONS:
        pct = int(round(frac * 100))
        for k, v in top_n(y, s, frac).items():
            out[f"{k}_top{pct}"] = float(v)
    out["precision_at_10"] = out["precision_top10"]
    for t in ("adjacent", "outlying"):
        m = (lei == t) | (y == 0)
        out[f"auc_{t}"] = float(roc_auc_score(y[m], s[m]))
    return out


def s1s2_metrics(cfg, ev: pd.DataFrame) -> dict:
    """Share of the growth in classes S1 + S2, with precision and lift."""
    cls = (
        pd.read_parquet(classes_path(cfg, "validation")).set_index("cell_id").loc[ev.index, "class"]
    )
    in_top = cls.isin([S1, S2]).to_numpy()
    y = ev["grew"].to_numpy()
    prec = y[in_top].mean()
    return {
        "s1_s2_hit_rate": float(y[in_top].sum() / y.sum()),
        "s1_s2_precision": float(prec),
        "s1_s2_lift": float(prec / y.mean()),
        "s1_s2_share_of_cells": float(in_top.mean()),
    }


def ablation(cfg, ev: pd.DataFrame) -> dict:
    """AUC change on grew when each feature group is dropped (rf_change and similarity_knn)."""
    labels = schema.read_contract(schema.contract_path(cfg, "C5"), "C5")
    seed = int(cfg["project"]["random_seed"])
    params = json.loads(rm.metrics_path(cfg).read_text())["rf_change"]["best_params"]
    feats = rm.model_features(cfg, int(cfg["years"]["baseline"]))
    ids, y_train = rm.training_set(labels, "rf_change")
    folds = rm.assign_folds(rm.spatial_blocks(cfg, ids), int(cfg["rf"]["n_folds"]), seed)
    y = ev["grew"].to_numpy()

    def rf_auc(cols: list[str]) -> float:
        cv = rm.cross_validate(cfg, feats.loc[ids, cols].to_numpy(), y_train, folds, params, seed)
        return float(roc_auc_score(y, pd.Series(cv["oof"], index=ids).loc[ev.index].to_numpy()))

    def sim_auc(cols: list[str]) -> float:
        s = ag.similarity_scores(cfg, "validation", columns=cols).set_index("cell_id")["score"]
        return float(roc_auc_score(y, s.loc[ev.index].to_numpy()))

    all_cols = list(schema.MODEL_INPUTS)
    out = {"full": {"rf_change": rf_auc(all_cols), "similarity_knn": sim_auc(all_cols)}, "drop": {}}
    for g in schema.ABLATION_GROUPS:
        drop = set(schema.FEATURE_GROUPS[g])
        cols = [c for c in all_cols if c not in drop]
        row = {"dropped": sorted(drop & set(all_cols))}
        for name, fn in (("rf_change", rf_auc), ("similarity_knn", sim_auc)):
            a = fn(cols)
            row[name] = {"auc": a, "delta": a - out["full"][name]}
        out["drop"][g] = row
        log.info(
            "ablation -%s: rf_change %+.3f, similarity %+.3f",
            g,
            row["rf_change"]["delta"],
            row["similarity_knn"]["delta"],
        )
    return out


def validation_path(cfg) -> Path:
    return Path(cfg.paths["metrics"]) / "validation.json"


def validate(cfg, do_ablation: bool = True) -> dict:
    """Run the harness on every score; write ``validation.json``."""
    ev = eval_set(cfg)
    y, lei = ev["grew"].to_numpy(), ev["lei_type"].to_numpy()
    scores = model_scores(cfg, ev.index)
    report = {
        "eval_set": {
            "n_cells": int(len(ev)),
            "n_grew": int(y.sum()),
            "prevalence": float(y.mean()),
            "n_adjacent": int((lei == "adjacent").sum()),
            "n_outlying": int((lei == "outlying").sum()),
        },
        "models": {},
        "toc": {},
    }
    for name, s in scores.items():
        m = evaluate_score(y, s.to_numpy(), lei)
        m["kind"] = "baseline" if name in BASELINES else "model"
        if name == "suitability" and classes_path(cfg, "validation").exists():
            m.update(s1s2_metrics(cfg, ev))
        report["models"][name] = m
        report["toc"][name] = toc_curve(y, s.to_numpy())
        log.info(
            "%-15s AUC %.3f, lift top 10 %% %.2f, adjacent %.3f / outlying %.3f",
            name,
            m["auc"],
            m["lift_top10"],
            m["auc_adjacent"],
            m["auc_outlying"],
        )
    if do_ablation:
        report["ablation"] = ablation(cfg, ev)
    p = validation_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=1, allow_nan=False))
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-ablation", action="store_true")
    args = parser.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "suitability")
    validate(cfg, do_ablation=not args.no_ablation)


if __name__ == "__main__":
    main()
