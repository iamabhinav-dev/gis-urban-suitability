"""Done check for P7.1, P7.2, P7.4 (combined score, classes, candidate sites, validation).

Independent recomputation:

1. weight: AUC on the 2020/21 training label recomputed by hand (Mann-Whitney U) for
   every weight; the stored weight is the best one;
2. combined score = w x percentile(similarity) + (1 - w) x percentile(rf_change), with
   percentiles computed here from the two C8 files;
3. classes: 10 / 20 / 30 / 40 % of the scored cells; in ``suitability_class.tif`` no
   forest, built-up or excluded cell (C7) is in S1-S3;
4. candidate patches recomputed with a plain flood fill (edge neighbours) on the S1
   cells: same patches, sizes and areas >= the minimum;
5. landmarks from OSM (independent of the ESRI-based classes): no top site overlaps an
   OSM lake or Bannerghatta National Park;
6. ``validation.json``: AUC (from ranks), top-10 % precision and lift, and the S1 + S2
   hit rate recomputed for every model.

Run: python scripts/verify_suitability.py
Exits with code 1 if any check fails.
"""

from __future__ import annotations

import json
import sys
from collections import deque

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from scipy.stats import rankdata

from src.classify.label import c7_path
from src.config import load_config
from src.features import schema
from src.preprocess.vector import processed_osm_path
from src.similarity.rf_model import scores_path
from src.suitability import candidates as cd
from src.suitability import score as sc
from src.suitability import validate as va

failures: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {msg}")
    if not ok:
        failures.append(msg)


def auc(y: np.ndarray, s: np.ndarray) -> float:
    r = rankdata(s)
    n1, n0 = int(y.sum()), int((1 - y).sum())
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def pct(s: pd.Series) -> pd.Series:
    return pd.Series(rankdata(s.to_numpy()) / len(s), index=s.index)


def main() -> int:
    cfg = load_config()
    m = json.loads(sc.metrics_path(cfg).read_text())
    w = m["w_similarity"]
    lab = pd.read_parquet(schema.contract_path(cfg, "C5")).set_index("cell_id")
    grid = pd.read_parquet(schema.contract_path(cfg, "C1")).set_index("cell_id")

    print("== 1. weight")
    cand = lab.index[lab["candidate"]]
    sim = (
        pd.read_parquet(scores_path(cfg, "similarity_knn", "validation"))
        .set_index("cell_id")["score"]
        .loc[cand]
    )
    rf = (
        pd.read_parquet(scores_path(cfg, "rf_change", "validation"))
        .set_index("cell_id")["score"]
        .loc[cand]
    )
    y = lab.loc[cand, "chg_train_pos"].to_numpy().astype(int)
    table = {
        g: auc(y, (g * pct(sim) + (1 - g) * pct(rf)).to_numpy())
        for g in cfg["suitability"]["weight_grid"]
    }
    best = max(table.values())
    check(
        abs(table[w] - best) < 1e-4,
        f"w_similarity {w}: AUC on chg_train_pos {table[w]:.4f} (best {best:.4f})",
    )

    print("== 2-3. combined score and classes")
    for run in ("validation", "final"):
        ids = lab.index[lab["candidate"]] if run == "validation" else None
        s_sim = pd.read_parquet(scores_path(cfg, "similarity_knn", run)).set_index("cell_id")[
            "score"
        ]
        s_rf = pd.read_parquet(scores_path(cfg, "rf_change", run)).set_index("cell_id")["score"]
        ids = s_sim.index if ids is None else ids
        mine = w * pct(s_sim.loc[ids]) + (1 - w) * pct(s_rf.loc[ids])
        stored = pd.read_parquet(scores_path(cfg, sc.MODEL, run)).set_index("cell_id")["score"]
        check(
            bool(np.allclose(mine.sort_index(), stored.loc[mine.index].sort_index())),
            f"{run}: combined score recomputed",
        )
        cls = pd.read_parquet(sc.classes_path(cfg, run))["class"].value_counts(normalize=True)
        shares = [cls.get(k, 0) for k in (1, 2, 3, 4)]
        check(
            bool(np.allclose(shares, [0.1, 0.2, 0.3, 0.4], atol=0.01)),
            f"{run}: class shares {np.round(shares, 3).tolist()}",
        )
    c7 = pd.read_parquet(c7_path(cfg, "final")).set_index("cell_id")
    with rasterio.open(sc.class_tif_path(cfg)) as ds:
        img = ds.read(1)
    g = grid.loc[c7.index]
    vals = img[g["row"], g["col"]]
    bad = int((np.isin(vals, [1, 2, 3]) & (c7["class_3"].to_numpy() != schema.CLASS_USABLE)).sum())
    check(bad == 0, f"no forest / built-up / excluded cell in S1-S3 ({bad})")

    print("== 4. candidate patches by flood fill")
    s1 = pd.read_parquet(sc.classes_path(cfg, "final"))
    s1 = s1.loc[s1["class"] == sc.S1, "cell_id"]
    cells = {(int(grid.at[c, "row"]), int(grid.at[c, "col"])) for c in s1}
    seen, sizes = set(), []
    for start in cells:
        if start in seen:
            continue
        n, queue = 0, deque([start])
        seen.add(start)
        while queue:
            r, c = queue.popleft()
            n += 1
            for nb in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if nb in cells and nb not in seen:
                    seen.add(nb)
                    queue.append(nb)
        sizes.append(n)
    cell_ha = cfg.cell_size_m**2 / 1e4
    min_cells = cfg["suitability"]["min_patch_area_m2"] / 1e4 / cell_ha
    mine = sorted(x for x in sizes if x >= min_cells - 1e-9)
    sites = gpd.read_file(cd.gpkg_path(cfg))
    check(
        mine == sorted(sites["n_cells"].tolist()),
        f"{len(mine)} patches, sizes match ({max(mine)} cells largest)",
    )
    check(bool(np.allclose(sites.area / 1e4, sites["area_ha"])), "patch polygons' area = area_ha")

    print("== 5. top sites vs OSM lakes and the national park")
    top = sites.loc[sites["top_site_rank"].notna()]
    water = gpd.read_file(processed_osm_path(cfg, "current", "water"))
    lakes = water.loc[water["kind"] == "water_body"]
    park = gpd.read_file(processed_osm_path(cfg, "current", "protected"))
    lake_ha = float(top.geometry.intersection(lakes.union_all()).area.sum()) / 1e4
    park_ha = float(top.geometry.intersection(park.union_all()).area.sum()) / 1e4
    check(
        lake_ha < 0.5 and park_ha < 0.5,
        f"{len(top)} top sites: {lake_ha:.2f} ha in OSM lakes, {park_ha:.2f} ha in protected areas",
    )

    print("== 6. validation.json recomputed")
    v = json.loads(va.validation_path(cfg).read_text())
    ev = lab.loc[lab["candidate"] & ~lab["ambiguous"]]
    yv = ev["grew"].to_numpy().astype(int)
    for name, row in v["models"].items():
        if name == "random":
            continue
        if name == "dist_to_built":
            c4 = pd.read_parquet(
                schema.contract_path(cfg, "C4", year=cfg["years"]["baseline"])
            ).set_index("cell_id")
            s = -c4.loc[ev.index, "log_dist_built"].to_numpy()
        else:
            s = (
                pd.read_parquet(scores_path(cfg, name, "validation"))
                .set_index("cell_id")
                .loc[ev.index, "score"]
                .to_numpy()
            )
        a = auc(yv, s)
        n = int(round(0.1 * len(s)))
        # precision in the top 10 %, ties broken the same way as the harness
        order = np.lexsort((np.random.default_rng(0).random(len(s)), -s))[:n]
        p10 = yv[order].mean()
        ok = abs(a - row["auc"]) < 1e-9 and abs(p10 - row["precision_top10"]) < 1e-9
        check(ok, f"{name}: AUC {a:.3f}, precision top 10 % {p10:.3f}, lift {p10 / yv.mean():.2f}")
    cls_v = (
        pd.read_parquet(sc.classes_path(cfg, "validation"))
        .set_index("cell_id")
        .loc[ev.index, "class"]
    )
    hr = yv[cls_v.isin([1, 2]).to_numpy()].sum() / yv.sum()
    check(
        abs(hr - v["models"][sc.MODEL]["s1_s2_hit_rate"]) < 1e-9,
        f"S1 + S2 hit rate {hr:.3f} recomputed",
    )

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} CHECK(S) FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
