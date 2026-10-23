"""Aggregate building similarity: how much does each cell look like where buildings are?

PRD FR-6.4, §9.5; Tasks P6.4. For every candidate cell of a run:

1. standardised profile (``profiles.run_profiles``);
2. mean Euclidean distance to its ``similarity.knn_k`` nearest **reference** profiles
   (P6.2). A cell that is itself a reference cell is never matched with itself;
3. similarity = 1 - rescaled distance, with the rescaling between the 1st and 99th
   percentile of the candidates' distances and clipped to [0, 1] (robust to a few
   extreme cells; higher = more similar).

Outputs, like the other models: C8 ``outputs/scores/similarity_knn.parquet``
(validation run: candidate cells, 2018 profiles, 2018 references),
``outputs/final/scores/similarity_knn.parquet`` (usable cells, latest year),
``outputs/similarity_score.tif`` (final, NaN outside usable land) and
``outputs/metrics/similarity.json`` → ``similarity_knn`` (with a temporal preview).

Run: python -m src.similarity.aggregate
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.neighbors import NearestNeighbors

from src.config import load_config
from src.features import schema
from src.io_utils import setup_logging
from src.similarity import profiles as pf
from src.similarity.rf_model import metrics_path, scores_path, write_probability_raster

log = logging.getLogger(__name__)

MODEL = "similarity_knn"
RESCALE_PCT = (1.0, 99.0)


def knn_mean_distance(
    ref_z: np.ndarray, ref_ids: np.ndarray, q_z: np.ndarray, q_ids: np.ndarray, k: int
) -> np.ndarray:  # noqa: E501
    """Mean distance of each query to its k nearest references, never counting itself."""
    k = min(k, len(ref_ids) - 1) if len(ref_ids) > 1 else 1
    nn = NearestNeighbors(n_neighbors=min(k + 1, len(ref_ids))).fit(ref_z)
    d, idx = nn.kneighbors(q_z)
    not_self = ref_ids[idx] != np.asarray(q_ids)[:, None]
    # keep the first k neighbours that aren't the query cell itself
    keep = not_self & (np.cumsum(not_self, axis=1) <= k)
    return (d * keep).sum(axis=1) / keep.sum(axis=1)


def rescale(dist: np.ndarray) -> np.ndarray:
    """Distance -> similarity in [0, 1] (1 = closest), robust percentile min-max."""
    lo, hi = np.percentile(dist, RESCALE_PCT)
    if hi <= lo:
        return np.ones_like(dist)
    return np.clip(1.0 - (dist - lo) / (hi - lo), 0.0, 1.0)


def similarity_scores(cfg, run: str, columns=None, k: int | None = None) -> pd.DataFrame:
    """Aggregate similarity of every candidate cell of a run (cell_id, score, mean_distance)."""
    rp = pf.run_profiles(cfg, run, columns)
    k = int(k or cfg["similarity"]["knn_k"])
    d = knn_mean_distance(
        rp.z.loc[rp.reference].to_numpy(), rp.reference,
        rp.z.loc[rp.candidates].to_numpy(), rp.candidates, k,
    )  # fmt: skip
    return pd.DataFrame({"cell_id": rp.candidates, "score": rescale(d), "mean_distance": d})


def similarity_tif_path(cfg) -> Path:
    return Path(cfg.paths["outputs"]) / "similarity_score.tif"


def write_similarity(cfg) -> dict:
    """Score both runs; write the C8 files, the GeoTIFF and the metrics entry."""
    k = int(cfg["similarity"]["knn_k"])
    base = int(cfg["years"]["baseline"])
    meta = {
        "model": MODEL,
        "features": pf.profile_columns(),
        "train_years": [base],
        "description": f"Mean Euclidean distance to the {k} nearest reference (building) profiles",
        "k": k,
        "reference_source": cfg["similarity"].get("reference_source", "osm+esri"),
    }
    out = {}
    for run in ("validation", "final"):
        sc = similarity_scores(cfg, run)
        c8 = sc[["cell_id", "score"]]
        schema.validate_frame(c8, "C8")
        p = scores_path(cfg, MODEL, run)
        p.parent.mkdir(parents=True, exist_ok=True)
        c8.to_parquet(p, index=False)
        p.with_suffix(".json").write_text(json.dumps({**meta, "run": run}, indent=1))
        if run == "validation":
            schema.validate_score_meta(p.with_suffix(".json"))
        else:
            write_probability_raster(cfg, c8, similarity_tif_path(cfg))
        out[run] = sc
    # preview of the temporal validation (Phase 7 does it properly)
    lab = schema.read_contract(schema.contract_path(cfg, "C5"), "C5").set_index("cell_id")
    v = out["validation"].set_index("cell_id")
    ev = lab.loc[v.index]
    keep = (~ev["ambiguous"]).to_numpy()
    auc = float(roc_auc_score(ev["grew"].to_numpy()[keep], v["score"].to_numpy()[keep]))
    mp = metrics_path(cfg)
    allm = json.loads(mp.read_text()) if mp.exists() else {}
    allm[MODEL] = {
        **{k_: v_ for k_, v_ in meta.items() if k_ != "features"},
        "n_reference": {r: int(len(pf.reference_ids(cfg, r))) for r in ("validation", "final")},
        "temporal_preview": {"auc_grew": auc},
    }
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(allm, indent=1, allow_nan=False))
    log.info(
        "%s: AUC on grew (validation run) %.3f; final run %d usable cells",
        MODEL,
        auc,
        len(out["final"]),
    )
    return out


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "similarity")
    write_similarity(cfg)


if __name__ == "__main__":
    main()
