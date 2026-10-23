"""Unit tests for P6.1, P6.3, P6.4 (profiles, single query, aggregate similarity) - P6.9."""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from src.classify.label import c7_path
from src.features import schema
from src.preprocess import raster as pr
from src.similarity import aggregate as ag
from src.similarity import profiles as pf
from src.similarity import query as q
from src.similarity.rf_model import metrics_path, scores_path
from src.synthetic import make_synthetic_project
from src.viz import static_maps as sm


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    cfg = make_synthetic_project(tmp_path / "proj", n=30)
    ref = pr.build_reference_grid(cfg)
    pr.processed_dir(cfg).mkdir(parents=True, exist_ok=True)
    pr.reference_grid_path(cfg).write_text(json.dumps(ref.to_json()))
    monkeypatch.setattr(sm, "BASEMAP", False)
    return cfg


# ---------------------------------------------------------------- profiles (P6.1)


@pytest.mark.parametrize("bad", ["frac_built", "bldg_count", "bldg_area_frac", "frac_crop"])
def test_profile_refuses_own_cell_and_leaky_features(bad):
    with pytest.raises(schema.ContractError):
        pf.profile_columns([*schema.MODEL_INPUTS[:3], bad])


def test_standardiser():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [5.0, 5.0, 5.0]})
    z = pf.Standardiser.fit(df).transform(df)
    assert z["a"].mean() == pytest.approx(0) and z["a"].std(ddof=0) == pytest.approx(1)
    assert (z["b"] == 0).all()  # a constant column doesn't divide by zero


def test_run_profiles_follow_the_time_travel_rule(cfg):
    for run, year in (("validation", cfg["years"]["baseline"]), ("final", cfg["years"]["latest"])):
        rp = pf.run_profiles(cfg, run)
        c4 = pd.read_parquet(schema.contract_path(cfg, "C4", year=year)).set_index("cell_id")
        raw = pf.profile_table(cfg, run)
        assert raw.equals(c4[list(schema.MODEL_INPUTS)].astype("float64"))
        fit = raw.loc[np.union1d(rp.reference, rp.candidates)]
        assert np.allclose(rp.scaler.mean, fit.mean())
    lab = pd.read_parquet(schema.contract_path(cfg, "C5"))
    assert set(pf.candidate_cells(cfg, "validation")) == set(lab.loc[lab["candidate"], "cell_id"])
    c7 = pd.read_parquet(c7_path(cfg, "final"))
    assert set(pf.candidate_cells(cfg, "final")) == set(c7.loc[c7["class_3"] == 3, "cell_id"])


# ---------------------------------------------------------------- kNN + rescaling (P6.4)


def test_identical_profiles_give_distance_zero_and_similarity_one():
    ref = np.array([[0.0, 0.0], [1.0, 1.0], [5.0, 5.0]])
    q_z = np.array([[0.0, 0.0], [9.0, 9.0]])
    d = ag.knn_mean_distance(ref, np.array([10, 11, 12]), q_z, np.array([20, 21]), k=1)
    assert d[0] == 0.0
    s = ag.rescale(np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]))
    assert s[0] == 1.0 and s[-1] == 0.0 and (np.diff(s) <= 0).all()


def test_a_reference_cell_is_never_matched_with_itself():
    ref = np.array([[0.0], [3.0], [10.0]])
    d = ag.knn_mean_distance(ref, np.array([1, 2, 3]), np.array([[0.0]]), np.array([1]), k=1)
    assert d[0] == 3.0  # nearest *other* reference, not itself at 0


def test_write_similarity(cfg):
    ag.write_similarity(cfg)
    for run in ("validation", "final"):
        s = schema.read_contract(scores_path(cfg, ag.MODEL, run), "C8")
        assert set(s["cell_id"]) == set(pf.candidate_cells(cfg, run))  # FR-6.7
        assert s["score"].between(0, 1).all()
    meta = schema.validate_score_meta(scores_path(cfg, ag.MODEL, "validation").with_suffix(".json"))
    assert meta["features"] == list(schema.MODEL_INPUTS)
    assert ag.similarity_tif_path(cfg).exists()
    m = json.loads(metrics_path(cfg).read_text())[ag.MODEL]
    assert 0 <= m["temporal_preview"]["auc_grew"] <= 1


# ---------------------------------------------------------------- single query (P6.3)


def _a_building(cfg):
    from src.similarity import reference as rs

    return int(rs.buildings(cfg, "final").iloc[0]["bldg_id"])


def test_query_returns_only_usable_cells_and_not_a(cfg):
    b = _a_building(cfg)
    res = q.query(cfg, "final", bldg_id=b, n=15)
    usable = set(pf.candidate_cells(cfg, "final"))
    assert set(res.results["cell_id"]) <= usable
    c7 = pd.read_parquet(c7_path(cfg, "final")).set_index("cell_id")
    assert (c7.loc[res.results["cell_id"], "class_3"] == schema.CLASS_USABLE).all()
    assert res.query_cell not in set(res.results["cell_id"])
    assert res.results["distance"].is_monotonic_increasing
    assert list(res.results["rank"]) == list(range(1, len(res.results) + 1))


def test_self_query_ranks_own_cell_first(cfg):
    b = _a_building(cfg)
    res = q.query(cfg, "final", bldg_id=b, n=5, candidates="all")
    assert res.results.iloc[0]["cell_id"] == res.query_cell and res.results.iloc[0]["distance"] == 0


def test_lonlat_to_cell_round_trip(cfg):
    """Cell centres -> WGS84 -> cell id, on a grid built the real way (lattice numbering)."""
    from pyproj import Transformer

    from src.features.grid import build_grid

    grid = build_grid(cfg).sample(20, random_state=0)
    lon, lat = Transformer.from_crs(cfg.crs, 4326, always_xy=True).transform(grid["x"], grid["y"])
    got = [pf.lonlat_to_cell(cfg, a, b) for a, b in zip(lon, lat, strict=True)]
    assert got == grid["cell_id"].tolist()
    assert pf.lonlat_to_cell(cfg, 0.0, 0.0) == -1  # far outside the grid


def test_query_by_cell_matches_query_by_building(cfg):
    b = _a_building(cfg)
    by_b = q.query(cfg, "final", bldg_id=b, n=5)
    by_c = q.query(cfg, "final", cell_id=by_b.query_cell, n=5)
    assert by_c.results.equals(by_b.results)


def test_metrics():
    za = np.array([1.0, 0.0])
    zc = np.array([[2.0, 0.0], [0.0, 1.0]])
    assert np.allclose(q.distances(zc, za, "euclidean"), [1.0, np.sqrt(2)])
    assert np.allclose(q.distances(zc, za, "cosine"), [0.0, 1.0])  # cosine ignores magnitude
    with pytest.raises(ValueError):
        q.distances(zc, za, "manhattan")


def test_trivial_matches_rank_last():
    cols = np.array(["ring250_crop", "elev_mean", "ring500_built"])
    t = q.trivial_match(cols, np.array([0.0, 0.0, 0.6]), np.array([0.001, 0.0, 0.5]))
    assert t.tolist() == [True, False, False]  # elevation 0 is a real value, not a share


def test_write_query(cfg):
    res = q.query(cfg, "final", bldg_id=_a_building(cfg), n=10)
    gpkg, png = q.write_query(cfg, res, "unit")
    assert png.exists()
    cells = gpd.read_file(gpkg, layer="similar_cells")
    a = gpd.read_file(gpkg, layer="query")
    assert len(cells) == 10 and list(a["cell_id"]) == [res.query_cell]
    assert {"closest_features", "most_different", "similarity"} <= set(cells.columns)
