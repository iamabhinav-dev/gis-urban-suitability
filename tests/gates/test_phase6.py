"""Phase 6 gate: building similarity and learned models (see docs/Tasks.md). Runs on real data.

Run: pytest tests/gates/test_phase6.py
Build first: python -m src.similarity.reference; python -m src.similarity.aggregate;
             python -m src.similarity.rf_model
Set GIS_SUIT_CONFIG to run the gate on another project (e.g. a synthetic one).
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import pytest
import rasterio

from src.classify.label import c7_path
from src.config import load_config
from src.features import schema
from src.features.grid import lattice
from src.preprocess.raster import load_reference_grid
from src.similarity import aggregate as ag
from src.similarity import profiles as pf
from src.similarity import query as q
from src.similarity import reference as rs
from src.similarity import rf_model as rm

cfg = load_config(os.environ.get("GIS_SUIT_CONFIG"))
N_QUERIES = 30


@pytest.fixture(scope="module")
def final_profiles() -> pf.RunProfiles:
    return pf.run_profiles(cfg, "final")


@pytest.fixture(scope="module")
def sample_buildings() -> pd.DataFrame:
    b = rs.buildings(cfg, "final")
    return b.sample(min(N_QUERIES, len(b)), random_state=int(cfg["project"]["random_seed"]))


def test_self_query_finds_its_own_location(final_profiles, sample_buildings):
    """A building's own cell (allowed as a candidate) or a neighbour is in the top 1 %."""
    grid = schema.read_contract(schema.contract_path(cfg, "C1"), "C1").set_index("cell_id")
    misses = []
    for _, b in sample_buildings.iterrows():
        a = int(b["cell_id"])
        res = q.query(cfg, "final", cell_id=a, n=1, include_cells=[a], profiles=final_profiles)
        cand = res.extra["candidate_ids"]
        top = cand[res.extra["rank_percentile"] <= 0.01]
        dr = np.abs(grid.loc[top, "row"].to_numpy() - grid.at[a, "row"])
        dc = np.abs(grid.loc[top, "col"].to_numpy() - grid.at[a, "col"])
        if not ((dr <= 1) & (dc <= 1)).any():
            misses.append(int(b["bldg_id"]))
    assert (
        not misses
    ), f"{len(misses)} buildings not found near themselves in the top 1 %: {misses[:5]}"


def test_query_results_are_usable_and_not_excluded(final_profiles, sample_buildings):
    c7 = schema.read_contract(c7_path(cfg, "final"), "C7").set_index("cell_id")
    excl = pd.read_parquet(schema.contract_path(cfg, "C5").parent / "exclusion_final.parquet")
    excluded = set(excl.loc[excl["excluded"], "cell_id"])
    for _, b in sample_buildings.head(10).iterrows():
        res = q.query(cfg, "final", bldg_id=int(b["bldg_id"]), profiles=final_profiles)
        ids = res.results["cell_id"]
        assert (
            c7.loc[ids, "class_3"] == schema.CLASS_USABLE
        ).all(), f"building {b['bldg_id']}: non-usable result"
        assert not set(ids) & excluded, f"building {b['bldg_id']}: excluded cell in the results"


@pytest.mark.parametrize("name", ["similarity_score.tif", "rf_probability.tif"])
def test_score_rasters_aligned_in_unit_range_nan_outside_usable(name):
    path = (
        ag.similarity_tif_path(cfg)
        if name.startswith("similarity")
        else rm.rf_probability_path(cfg)
    )
    assert path.exists(), f"{path} missing"
    lat, ref = lattice(cfg), load_reference_grid(cfg)
    with rasterio.open(path) as ds:
        img = ds.read(1)
        assert ds.crs == cfg.crs and img.shape == lat.shape, f"{name}: grid differs"
        assert (ds.transform.c, ds.transform.f) == (
            ref.transform.c,
            ref.transform.f,
        ), f"{name}: origin"
        assert ds.res == (cfg.cell_size_m, cfg.cell_size_m), f"{name}: resolution {ds.res}"
    vals = img[np.isfinite(img)]
    assert ((vals >= 0) & (vals <= 1)).all(), f"{name}: values outside [0, 1]"
    grid = schema.read_contract(schema.contract_path(cfg, "C1"), "C1").set_index("cell_id")
    use = pf.candidate_cells(cfg, "final")
    usable = np.zeros(lat.shape, bool)
    usable[grid.loc[use, "row"], grid.loc[use, "col"]] = True
    assert (np.isfinite(img) == usable).all(), f"{name}: NaN pattern differs from the usable cells"


def test_no_leaky_feature_in_profiles_or_models():
    pf.profile_columns()  # raises on leaky / own-cell columns
    for model in ("similarity_knn", *rm.MODELS):
        meta = schema.validate_score_meta(
            rm.scores_path(cfg, model, "validation").with_suffix(".json")
        )
        bad = set(meta["features"]) & (set(schema.LEAKY_FEATURES) | set(schema.OWN_FRACTIONS))
        assert not bad, f"{model}: leaky inputs {sorted(bad)}"


@pytest.mark.parametrize("model", rm.MODELS)
def test_spatial_folds_never_share_a_block(model):
    labels = schema.read_contract(schema.contract_path(cfg, "C5"), "C5")
    ids, _ = rm.training_set(labels, model)
    blocks = rm.spatial_blocks(cfg, ids)
    folds = rm.assign_folds(blocks, int(cfg["rf"]["n_folds"]), int(cfg["project"]["random_seed"]))
    assert pd.Series(folds).groupby(blocks).nunique().max() == 1, "a block is in two folds"
    assert len(np.unique(folds)) == int(cfg["rf"]["n_folds"])


def test_rf_spatial_cv_auc_saved():
    m = json.loads(rm.metrics_path(cfg).read_text())
    for model in rm.MODELS:
        auc = m[model]["spatial_cv_auc"]["mean"]
        assert 0.5 <= auc <= 1, f"{model}: spatial-CV AUC {auc}"
        assert len(m[model]["spatial_cv_auc"]["folds"]) == int(cfg["rf"]["n_folds"])
    assert (
        "similarity_knn" in m
    ), "aggregate similarity metrics missing (python -m src.similarity.aggregate)"
