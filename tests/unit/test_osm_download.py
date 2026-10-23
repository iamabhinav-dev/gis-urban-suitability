"""Unit tests for the OSM downloader (no network: Overpass queries are mocked)."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon

from src.download import osm
from src.io_utils import DownloadError, Manifest, manifest_key, sha256
from src.synthetic import make_synthetic_project


@pytest.fixture
def project(tmp_path):
    return make_synthetic_project(tmp_path / "proj", n=10)


def _features(n_ways: int = 3) -> gpd.GeoDataFrame:
    """An osmnx-like result: (element, id) index, a point, ways and a list column."""
    geoms = [Point(77.6, 12.8)] + [
        LineString([(77.6 + k * 0.001, 12.8), (77.6 + k * 0.001, 12.801)]) for k in range(n_ways)
    ]
    idx = pd.MultiIndex.from_tuples(
        [("node", 1)] + [("way", 100 + k) for k in range(n_ways)], names=["element", "id"]
    )
    return gpd.GeoDataFrame(
        {
            "highway": ["crossing"] + ["residential"] * n_ways,
            "name": [None] + [f"Road {k}" for k in range(n_ways)],
            "nodes": [None] + [[1, 2]] * n_ways,  # list column, must be dropped
            "fixme": ["x"] * (n_ways + 1),  # tag not in the kept list
        },
        geometry=geoms,
        index=idx,
        crs="EPSG:4326",
    )


def test_snapshots_and_layers(project):
    snaps = osm.snapshots(project)
    pinned = f"{project['osm']['snapshot_current']}T00:00:00Z"
    assert snaps == {"2018": "2018-01-01T00:00:00Z", "current": pinned}
    project.raw["osm"]["snapshot_current"] = None  # unpinned: the day of the download
    assert osm.snapshots(project)["current"] is None
    assert "protected" not in osm.layers_for("2018")
    assert osm.layers_for("current") == ("roads", "water", "buildings", "protected")
    assert (
        osm.osm_path(project, "2018", "roads").as_posix().endswith("data/raw/osm/2018/roads.gpkg")
    )


def test_overpass_settings_date_only_for_history():
    assert osm.overpass_settings("2018-01-01T00:00:00Z").endswith('[date:"2018-01-01T00:00:00Z"]')
    assert "date" not in osm.overpass_settings(None)
    assert osm.overpass_settings(None).startswith("[out:json][timeout:{timeout}]")


def test_tidy_keeps_types_and_columns():
    out = osm.tidy(_features(), *osm.LAYERS["roads"][1:])
    assert len(out) == 3  # the point is dropped
    assert list(out.columns) == ["osm_type", "osm_id", "highway", "name", "geometry"]
    assert set(out.osm_type) == {"way"} and out.osm_id.tolist() == [100, 101, 102]
    assert out.crs.to_epsg() == 4326


def test_download_falls_back_to_next_mirror_and_skips_rerun(project, monkeypatch):
    calls = []

    def fake_query(bbox, tags, date, mirror):
        calls.append((mirror, date))
        if "overpass-api.de" in mirror:
            raise ConnectionError("timed out")
        if tags == {"highway": True}:
            return _features()
        return gpd.GeoDataFrame(
            {"building": ["yes"]},
            geometry=[Polygon([(77.6, 12.8), (77.601, 12.8), (77.601, 12.801)])],
            index=pd.MultiIndex.from_tuples([("way", 7)], names=["element", "id"]),
            crs="EPSG:4326",
        )

    monkeypatch.setattr(osm, "_query", fake_query)
    monkeypatch.setattr(osm.time, "sleep", lambda s: None)

    path = osm.download_layer(project, "2018", "roads")
    assert [m for m, _ in calls] == [
        "https://overpass-api.de/api/interpreter",  # 2 attempts on the first mirror
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    assert calls[-1][1] == "2018-01-01T00:00:00Z"  # historical snapshot
    gdf = gpd.read_file(path)
    assert len(gdf) == 3 and "highway" in gdf.columns
    entry = Manifest.for_config(project).get(manifest_key(path, project.root))
    assert entry["dataset"] == "osm-roads" and entry["snapshot"] == "2018"
    assert entry["source"]["mirror"].endswith("kumi.systems/api/interpreter")
    assert entry["n_features"] == 3 and entry["sha256"] == sha256(path)

    n_calls = len(calls)
    osm.download_layer(project, "2018", "roads")  # rerun: skipped, no query
    assert len(calls) == n_calls


def test_redownloads_when_the_area_changes(project, monkeypatch):
    calls = []
    monkeypatch.setattr(osm, "_query", lambda *a: calls.append(a[0]) or _features())
    osm.download_layer(project, "current", "roads")
    osm.download_layer(project, "current", "roads")  # same area: skipped
    assert len(calls) == 1
    project.raw["aoi"]["buffer_m"] = float(project.raw["aoi"]["buffer_m"]) + 2000
    osm.download_layer(project, "current", "roads")  # larger buffer: fetched again
    assert len(calls) == 2
    assert calls[1][0] < calls[0][0] and calls[1][3] > calls[0][3]  # wider bbox


def test_all_mirrors_failing_is_a_clear_error(project, monkeypatch):
    def fail(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(osm, "_query", fail)
    monkeypatch.setattr(osm.time, "sleep", lambda s: None)
    with pytest.raises(DownloadError, match="All Overpass mirrors failed"):
        osm.download_layer(project, "current", "water")
    assert not osm.osm_path(project, "current", "water").exists()


def test_one_tag_empty_on_all_mirrors_is_skipped_and_counted(project, monkeypatch):
    class InsufficientResponseError(Exception):  # name matches osmnx's exception
        pass

    def fake_query(bbox, tags, date, mirror):
        if "leisure" in tags:
            raise InsufficientResponseError("No matching features")
        return gpd.GeoDataFrame(
            {"boundary": ["protected_area"], "name": ["Bannerghatta National Park"]},
            geometry=[Polygon([(77.55, 12.75), (77.6, 12.75), (77.6, 12.8)])],
            index=pd.MultiIndex.from_tuples([("relation", 9)], names=["element", "id"]),
            crs="EPSG:4326",
        )

    monkeypatch.setattr(osm, "_query", fake_query)
    monkeypatch.setattr(osm.time, "sleep", lambda s: None)
    path = osm.download_layer(project, "current", "protected")
    assert gpd.read_file(path).name.tolist() == ["Bannerghatta National Park"]
    entry = Manifest.for_config(project).get(manifest_key(path, project.root))
    assert entry["n_features_by_tag"] == {
        "boundary=protected_area,national_park": 1,
        "leisure=nature_reserve": 0,
    }


def test_water_queries_key_only_and_keeps_natural_water(project, monkeypatch):
    queried = []
    lake = Polygon([(77.6, 12.8), (77.601, 12.8), (77.601, 12.801)])

    def fake_query(bbox, tags, date, mirror):
        queried.append(tags)
        idx = pd.MultiIndex.from_tuples([("way", 1), ("way", 2)], names=["element", "id"])
        if "natural" in tags:
            return gpd.GeoDataFrame(
                {"natural": ["water", "wood"]}, geometry=[lake, lake], index=idx, crs="EPSG:4326"
            )
        river = LineString([(77.6, 12.8), (77.61, 12.81)])
        return gpd.GeoDataFrame(
            {"waterway": ["river", "stream"]}, geometry=[river, river], index=idx, crs="EPSG:4326"
        )

    monkeypatch.setattr(osm, "_query", fake_query)
    path = osm.download_layer(project, "2018", "water")
    assert queried == [{"natural": True}, {"waterway": True}]  # key-only queries
    gdf = gpd.read_file(path)
    assert gdf.natural.dropna().tolist() == ["water"]  # the wood polygon is dropped
    entry = Manifest.for_config(project).get(manifest_key(path, project.root))
    assert entry["n_features_by_tag"] == {"natural=water": 1, "waterway=True": 2}


def test_empty_result_is_an_error(project, monkeypatch):
    monkeypatch.setattr(osm, "_query", lambda *a: _features().iloc[:1])  # only a point
    with pytest.raises(DownloadError, match="no features"):
        osm.download_layer(project, "current", "roads")


def test_download_osm_runs_every_snapshot_layer(project, monkeypatch):
    done = []
    monkeypatch.setattr(
        osm, "download_layer", lambda cfg, s, layer, force, manifest: done.append((s, layer))
    )
    osm.download_osm(project)
    assert done == [
        ("2018", "roads"),
        ("2018", "water"),
        ("2018", "buildings"),
        ("current", "roads"),
        ("current", "water"),
        ("current", "buildings"),
        ("current", "protected"),
    ]


def test_empty_tag_costs_two_queries_without_retries(project, monkeypatch):
    """Regression (P8.11): an empty tag was retried on every mirror (~7 min each)."""

    class InsufficientResponseError(Exception):
        pass

    calls, sleeps = [], []

    def fake_query(bbox, tags, date, mirror):
        calls.append(mirror)
        raise InsufficientResponseError("No matching features")

    monkeypatch.setattr(osm, "_query", fake_query)
    monkeypatch.setattr(osm.time, "sleep", lambda s: sleeps.append(s))
    with pytest.raises(osm.NoFeatures):
        osm.fetch_features(project, (0, 0, 1, 1), {"leisure": "nature_reserve"}, None)
    mirrors = project["osm"]["overpass_mirrors"]
    assert calls == mirrors[:2] and not sleeps


def test_empty_answer_on_one_mirror_then_data_on_the_next(project, monkeypatch):
    """A timeout that osmnx reports as 'no features' must not hide real data."""

    class InsufficientResponseError(Exception):
        pass

    def fake_query(bbox, tags, date, mirror):
        if mirror == project["osm"]["overpass_mirrors"][0]:
            raise InsufficientResponseError("No matching features")
        return _features()

    monkeypatch.setattr(osm, "_query", fake_query)
    gdf, mirror = osm.fetch_features(project, (0, 0, 1, 1), {"highway": True}, None)
    assert len(gdf) == len(_features()) and mirror == project["osm"]["overpass_mirrors"][1]


def test_redownloads_when_the_pinned_date_changes(project, monkeypatch):
    dates = []
    monkeypatch.setattr(osm, "_query", lambda *a: dates.append(a[2]) or _features())
    osm.download_layer(project, "current", "roads")
    osm.download_layer(project, "current", "roads")  # same date: skipped
    project.raw["osm"]["snapshot_current"] = "2026-11-01"
    osm.download_layer(project, "current", "roads")
    assert dates == ["2026-10-01T00:00:00Z", "2026-11-01T00:00:00Z"]
