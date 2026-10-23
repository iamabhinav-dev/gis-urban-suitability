"""Unit tests for P7.1 (combined score, classes), P7.2 (candidates), P7.4 (validation harness),
P7.8 (pipeline plan) and P8.3 helpers - part of P7.9."""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio

from src import pipeline as pl
from src.classify.label import c7_path
from src.features import schema
from src.features.grid import lattice
from src.preprocess import raster as pr
from src.similarity import aggregate as ag
from src.similarity import reference as rs
from src.similarity import rf_model as rm
from src.suitability import candidates as cd
from src.suitability import score as sc
from src.suitability import validate as va
from src.synthetic import make_synthetic_project
from src.viz import interactive as it


@pytest.fixture(scope="module")
def cfg(tmp_path_factory):
    cfg = make_synthetic_project(tmp_path_factory.mktemp("p7") / "proj", n=30)
    ref = pr.build_reference_grid(cfg)
    pr.processed_dir(cfg).mkdir(parents=True, exist_ok=True)
    pr.reference_grid_path(cfg).write_text(json.dumps(ref.to_json()))
    cfg["validation"]["spatial_block_m"] = 500
    cfg["rf"].update(
        n_estimators=20, n_folds=3, permutation_repeats=1, param_grid={"min_samples_leaf": [5]}
    )
    rs.write_reference(cfg)
    rm.write_models(cfg, ["rf_change"])
    ag.write_similarity(cfg)
    sc.write_suitability(cfg)
    return cfg


# ---------------------------------------------------------------- classes (P7.1, P7.9)


def test_class_thresholds_give_the_expected_proportions():
    s = pd.Series(np.random.default_rng(0).random(10_000))
    cls = sc.classify(s, [0.9, 0.7, 0.4]).value_counts(normalize=True)
    assert cls[sc.S1] == pytest.approx(0.10, abs=0.002)
    assert cls[sc.S2] == pytest.approx(0.20, abs=0.002)
    assert cls[sc.S3] == pytest.approx(0.30, abs=0.002)
    assert cls[sc.N] == pytest.approx(0.40, abs=0.002)


def test_combine_is_a_weighted_mean_of_percentiles():
    r = pd.DataFrame({"similarity_knn": [0.2, 1.0], "rf_change": [1.0, 0.0]})
    assert sc.combine(r, 0.3).tolist() == pytest.approx([0.3 * 0.2 + 0.7, 0.3])


def test_weight_is_chosen_on_the_training_label_not_on_grew(cfg, monkeypatch):
    seen = []
    real = sc.roc_auc_score
    monkeypatch.setattr(sc, "roc_auc_score", lambda y, s: seen.append(y) or real(y, s))
    w, table = sc.choose_weight(cfg)
    lab = pd.read_parquet(schema.contract_path(cfg, "C5")).set_index("cell_id")
    ranks = sc.component_ranks(cfg, "validation")
    assert all((y == lab.loc[ranks.index, "chg_train_pos"].to_numpy()).all() for y in seen)
    assert w in cfg["suitability"]["weight_grid"] and len(table) == len(
        cfg["suitability"]["weight_grid"]
    )


def test_suitability_outputs(cfg):
    for run in ("validation", "final"):
        s = schema.read_contract(rm.scores_path(cfg, sc.MODEL, run), "C8")
        assert s["score"].between(0, 1).all()
    c7 = pd.read_parquet(c7_path(cfg, "final"))
    grid = pd.read_parquet(schema.contract_path(cfg, "C1")).merge(c7, on="cell_id")
    with rasterio.open(sc.class_tif_path(cfg)) as ds:
        img = ds.read(1)
    inside = img[grid["row"], grid["col"]]
    assert set(np.unique(inside)) <= {1, 2, 3, 4}
    assert (inside[grid["class_3"].to_numpy() != schema.CLASS_USABLE] == sc.N).all()  # FR-7.3
    outside = np.ones(lattice(cfg).shape, bool)
    outside[grid["row"], grid["col"]] = False
    assert (img[outside] == sc.NODATA).all()


# ---------------------------------------------------------------- candidates (P7.2)


def test_patches_use_edge_neighbours_only(cfg):
    cells = pd.DataFrame({"row": [0, 0, 1, 3, 4], "col": [0, 1, 1, 3, 4]})
    lab = cd.label_patches(cfg, cells)
    assert lab[0] == lab[1] == lab[2]  # an L of edge neighbours is one patch
    assert lab[3] != lab[4]  # diagonal only: two patches


def test_candidate_sites(cfg):
    gdf = cd.write_candidates(cfg)
    cls = pd.read_parquet(sc.classes_path(cfg, "final"))
    assert gdf["n_cells"].sum() <= (cls["class"] == sc.S1).sum()
    assert (gdf["area_ha"] * 1e4 >= cfg["suitability"]["min_patch_area_m2"] - 1e-6).all()
    assert gdf["mean_score"].is_monotonic_decreasing and gdf["site_id"].tolist() == list(
        range(1, len(gdf) + 1)
    )
    top = gdf.dropna(subset=["top_site_rank"])
    assert (top["area_ha"] >= cfg["suitability"]["top_site_min_area_ha"]).all()
    assert len(top) <= cfg["suitability"]["top_n_sites"]
    assert len(gpd.read_file(cd.gpkg_path(cfg))) == len(pd.read_csv(cd.csv_path(cfg))) == len(gdf)


# ---------------------------------------------------------------- harness (P7.4)


def test_top_n_and_toc():
    y = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
    s = np.arange(10, 0, -1).astype(float)  # perfect ranking
    t = va.top_n(y, s, 0.2)
    assert t["precision"] == 1.0 and t["recall"] == 1.0 and t["lift"] == pytest.approx(5.0)
    toc = va.toc_curve(y, s, points=11)
    assert (
        toc["flagged"][0] == 0
        and toc["hits"][0] == 0
        and toc["flagged"][-1] == 1
        and toc["hits"][-1] == 1
    )
    assert toc["hits"][2] == 1.0  # all growth found after flagging 20 % of the cells


def test_auc_by_growth_type_uses_all_non_growth():
    y = np.array([1, 1, 0, 0])
    s = np.array([0.9, 0.1, 0.5, 0.4])
    lei = np.array(["adjacent", "outlying", "none", "none"])
    m = va.evaluate_score(y, s, lei)
    assert m["auc_adjacent"] == 1.0 and m["auc_outlying"] == 0.0


def test_validate_writes_every_model_and_both_baselines(cfg):
    rep = va.validate(cfg, do_ablation=False)
    models = rep["models"]
    assert {"random", "dist_to_built", "rf_change", "similarity_knn", sc.MODEL} <= set(models)
    for m in models.values():
        assert {
            "auc",
            "precision_at_10",
            "lift_top10",
            "lift_top30",
            "auc_adjacent",
            "auc_outlying",
        } <= set(m)
    assert {"s1_s2_hit_rate", "s1_s2_lift"} <= set(models[sc.MODEL])
    assert models[sc.MODEL]["s1_s2_share_of_cells"] == pytest.approx(0.3, abs=0.05)

    def no_nan(x):
        raise ValueError(x)

    json.loads(va.validation_path(cfg).read_text(), parse_constant=no_nan)


# ---------------------------------------------------------------- pipeline (P7.8)


def test_pipeline_plan():
    steps = pl.plan()
    assert [s for s, _ in steps][0] == "download" and [s for s, _ in steps][-1] == "viz"
    part = pl.plan("features", "classify")
    assert {s for s, _ in part} == {"features", "labels", "classify"}
    # sensitivity runs by default (FR-8.7; charts and notebook 06 read it), unless skipped
    assert ("suitability", pl.SENSITIVITY) in pl.plan("suitability", "suitability")
    off = pl.plan("suitability", "suitability", sensitivity=False)
    assert ("suitability", pl.SENSITIVITY) not in off
    with pytest.raises(ValueError):
        pl.plan("nope")
    with pytest.raises(ValueError):
        pl.plan("viz", "download")
    cmds = [c[0] for _, c in steps]
    i = {m: cmds.index(m) for m in cmds}
    assert (
        i["src.similarity.aggregate"] < i["src.suitability.score"] < i["src.suitability.candidates"]
    )
    assert i["src.classify.label"] < i["src.similarity.reference"]


def test_pipeline_dry_run_runs_nothing(tmp_path):
    t = pl.run(pl.plan("labels", "labels"), tmp_path, dry_run=True)
    assert t["steps"] == []


# ---------------------------------------------------------------- interactive map helpers (P8.3)


def test_png_overlays_are_data_uris():
    url = it.categorical_png(np.array([[1, 2], [3, 255]]), {1: "#ff0000", 2: "#00ff00"})
    assert url.startswith("data:image/png;base64,")
    assert it.sequential_png(np.array([[0.0, np.nan], [0.5, 1.0]])).startswith(
        "data:image/png;base64,"
    )


def test_to_wgs84_bounds_contain_the_aoi(cfg):
    arr, b = it.to_wgs84(sc.class_tif_path(cfg))
    w, s, e, n = cfg.aoi.to_crs(4326).total_bounds
    (south, west), (north, east) = b
    assert south <= s and west <= w and north >= n and east >= e and arr.size > 0


def test_charts_skip_a_figure_whose_input_is_missing(cfg, monkeypatch):
    """Regression (P8.11): a fresh clone without sensitivity.json crashed the viz stage."""
    from src.viz import charts

    def missing(c):
        raise FileNotFoundError("sensitivity.json")

    monkeypatch.setattr(charts, "k_scan", missing)
    others = (
        "cluster_profiles",
        "class_areas",
        "rf_importance",
        "roc",
        "sensitivity",
        "holdout",
        "toc",
        "growth_type",
        "ablation_chart",
    )
    for name in others:
        monkeypatch.setattr(charts, name, lambda c: None)
    assert charts.make_all(cfg) == []  # no crash; the missing figure is skipped
