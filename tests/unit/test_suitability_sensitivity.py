"""Unit tests for P7.6: the separate cell-size project used by the sensitivity analysis."""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio

from src.config import load_config
from src.features.grid import build_grid
from src.preprocess import raster as pr
from src.suitability import sensitivity as se
from src.synthetic import make_synthetic_project


@pytest.fixture
def main_cfg(tmp_path, monkeypatch):
    cfg = make_synthetic_project(tmp_path / "proj", n=30)
    ref = pr.build_reference_grid(cfg)
    out = pr.processed_dir(cfg)
    out.mkdir(parents=True, exist_ok=True)
    pr.reference_grid_path(cfg).write_text(json.dumps(ref.to_json()))
    pr.write(
        out / "slope.tif",
        np.arange(ref.shape[0] * ref.shape[1], dtype="float32").reshape(ref.shape),
        ref,
        -9999.0,
    )
    for name in ("osm", "buildings_2018.gpkg", "buildings_current.gpkg"):
        (out / name).mkdir() if name == "osm" else (out / name).write_text("")
    raw = cfg.paths["data_raw"] / "osm" / "current"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "protected.gpkg").write_text("")
    path = cfg.root / "config" / "config.yaml"
    monkeypatch.setattr(se, "load_config", lambda p=None: load_config(p or path))
    monkeypatch.setattr(se, "DEFAULT_CONFIG_PATH", path)
    return cfg, ref


@pytest.mark.parametrize("cell", [50, 70])  # 70 m: the grid isn't a multiple -> cropped
def test_cell_project(main_cfg, cell):
    cfg, ref = main_cfg
    sub = load_config(se.cell_project(cell))
    assert sub.cell_size_m == cell
    sref = pr.load_reference_grid(sub)
    k = cell // 10
    assert sref.height % k == 0 and sref.width % k == 0
    assert sref.transform == ref.transform  # same origin and pixel
    assert sref.height <= ref.height and ref.height - sref.height < k
    with (
        rasterio.open(pr.processed_dir(sub) / "slope.tif") as ds,
        rasterio.open(pr.processed_dir(cfg) / "slope.tif") as orig,
    ):
        assert (ds.height, ds.width) == sref.shape
        assert (
            ds.read(1) == orig.read(1)[: sref.height, : sref.width]
        ).all()  # cropped at the bottom/right
    g = build_grid(sub)
    assert len(g) > 0 and np.allclose(((g["x"] - ref.transform.c) / (cell / 2)) % 2, 1)
    assert sub.paths["data_features"] != cfg.paths["data_features"]  # never the main project's data
    # regression: the exclusion mask reads OSM lakes / protected areas from the raw downloads
    from src.download.osm import osm_path

    assert osm_path(sub, "current", "protected").exists()
