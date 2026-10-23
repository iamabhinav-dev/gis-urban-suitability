"""Done check for P6.1, P6.3, P6.4 (profiles, single query, aggregate similarity).

Independent recomputation with plain numpy (no scikit-learn, no project helpers beyond
reading the contract files):

1. standardisation: mean / std of the reference + candidate cells' raw C4 values;
2. aggregate: brute-force distances from 150 random candidate cells to every reference
   profile, mean of the 10 smallest (a cell that is itself a reference left out) =
   the stored mean distance; score = the stored score (same rescaling);
3. query: brute-force ranking for 5 random buildings = the query's top 20, all usable;
4. self-query: for 200 random buildings, a cell within one cell of A (A's own cell
   left out) is in the top 1 % of all cells;
5. ``similarity_score.tif`` = the final scores, NaN elsewhere;
6. temporal AUC from ranks (Mann-Whitney U) = the stored preview.

Run: python scripts/verify_similarity.py
Exits with code 1 if any check fails.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
import rasterio
from scipy.stats import rankdata

from src.classify.label import c7_path
from src.config import load_config
from src.features import schema
from src.similarity import aggregate as ag
from src.similarity import query as q
from src.similarity import reference as rs
from src.similarity.rf_model import metrics_path, scores_path

failures: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {msg}")
    if not ok:
        failures.append(msg)


def zscores(cfg, run: str) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    year = cfg["years"]["baseline"] if run == "validation" else cfg["years"]["latest"]
    c4 = pd.read_parquet(schema.contract_path(cfg, "C4", year=year)).set_index("cell_id")
    X = c4[list(schema.MODEL_INPUTS)].astype(float)
    ref = pd.read_parquet(rs.reference_path(cfg, run))["cell_id"].to_numpy()
    if run == "validation":
        lab = pd.read_parquet(schema.contract_path(cfg, "C5"))
        cand = lab.loc[lab["candidate"], "cell_id"].to_numpy()
    else:
        c7 = pd.read_parquet(c7_path(cfg, "final"))
        cand = c7.loc[c7["class_3"] == schema.CLASS_USABLE, "cell_id"].to_numpy()
    fit = X.loc[np.union1d(ref, cand)]
    sd = fit.std(ddof=0).replace(0, 1)
    return (X - fit.mean()) / sd, ref, cand


def main() -> int:
    cfg = load_config()
    k = int(cfg["similarity"]["knn_k"])
    rng = np.random.default_rng(11)

    for run in ("validation", "final"):
        print(f"== 1-2. aggregate, {run} run")
        Z, ref, cand = zscores(cfg, run)
        R = Z.loc[ref].to_numpy()
        sample = rng.choice(cand, 150, replace=False)
        refset = set(ref.tolist())
        sample = np.concatenate(
            [sample, [c for c in cand if c in refset][:20]]
        )  # include self cases
        mine = []
        for c in sample:
            d = np.sqrt(((R - Z.loc[c].to_numpy()) ** 2).sum(axis=1))
            d = d[ref != c]  # never itself
            mine.append(np.sort(d)[:k].mean())
        stored = ag.similarity_scores(cfg, run).set_index("cell_id")
        err = float(np.abs(np.array(mine) - stored.loc[sample, "mean_distance"].to_numpy()).max())
        n_self = int(np.isin(sample, ref).sum())
        msg = f"brute-force mean distance to {k} nearest references, {len(sample)} cells"
        check(err < 1e-9, f"{msg} ({n_self} are themselves references): max diff {err:.1e}")
        file = pd.read_parquet(scores_path(cfg, ag.MODEL, run)).set_index("cell_id")
        check(
            bool(np.allclose(file.loc[stored.index, "score"], stored["score"])),
            "stored C8 scores = recomputed scores",
        )

    print("== 3. query vs brute force (final run)")
    Z, ref, cand = zscores(cfg, "final")
    b = rs.buildings(cfg, "final").sample(5, random_state=3)
    c7 = pd.read_parquet(c7_path(cfg, "final")).set_index("cell_id")
    for _, row in b.iterrows():
        a = int(row["cell_id"])
        cc = cand[cand != a]
        d = np.sqrt(((Z.loc[cc].to_numpy() - Z.loc[a].to_numpy()) ** 2).sum(axis=1))
        want = cc[np.argsort(d, kind="stable")[:20]]
        res = q.query(cfg, "final", bldg_id=int(row["bldg_id"]), n=20)
        got = res.results["cell_id"].to_numpy()
        usable = (c7.loc[got, "class_3"] == schema.CLASS_USABLE).all()
        check(
            bool((got == want).all() and usable),
            f"building {row['bldg_id']}: top 20 = brute force, all usable",
        )

    print("== 4. self-query, 200 buildings, own cell left out")
    grid = pd.read_parquet(schema.contract_path(cfg, "C1")).set_index("cell_id")
    ids = Z.index.to_numpy()
    rows, cols = grid.loc[ids, "row"].to_numpy(), grid.loc[ids, "col"].to_numpy()
    A = Z.to_numpy()
    pos = {c: i for i, c in enumerate(ids)}
    hits = 0
    for _, row in rs.buildings(cfg, "final").sample(200, random_state=4).iterrows():
        a = int(row["cell_id"])
        d = np.sqrt(((A - A[pos[a]]) ** 2).sum(axis=1))
        d[pos[a]] = np.inf
        top = np.argsort(d)[: len(d) // 100]
        hits += bool(
            (
                (np.abs(rows[top] - grid.at[a, "row"]) <= 1)
                & (np.abs(cols[top] - grid.at[a, "col"]) <= 1)
            ).any()
        )
    check(hits >= 190, f"{hits}/200 buildings have a neighbouring cell in the top 1 % of all cells")

    print("== 5. similarity_score.tif")
    fin = pd.read_parquet(scores_path(cfg, ag.MODEL, "final"))
    g = grid.loc[fin["cell_id"]]
    with rasterio.open(ag.similarity_tif_path(cfg)) as ds:
        img = ds.read(1)
    ok = np.allclose(img[g["row"], g["col"]], fin["score"]) and int(np.isfinite(img).sum()) == len(
        fin
    )
    check(bool(ok), "GeoTIFF = final scores, NaN elsewhere")

    print("== 6. temporal AUC from ranks")
    lab = pd.read_parquet(schema.contract_path(cfg, "C5")).set_index("cell_id")
    cidx = lab.index[lab["candidate"] & ~lab["ambiguous"]]
    y = lab.loc[cidx, "grew"].to_numpy().astype(int)
    s = (
        pd.read_parquet(scores_path(cfg, ag.MODEL, "validation"))
        .set_index("cell_id")
        .loc[cidx, "score"]
    )
    r = rankdata(s.to_numpy())
    auc = (r[y == 1].sum() - y.sum() * (y.sum() + 1) / 2) / (y.sum() * (1 - y).sum())
    stored = json.loads(metrics_path(cfg).read_text())[ag.MODEL]["temporal_preview"]["auc_grew"]
    check(abs(auc - stored) < 1e-9, f"AUC on grew {auc:.3f} = stored")

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} CHECK(S) FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
