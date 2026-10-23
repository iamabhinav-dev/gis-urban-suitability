"""Unit tests for P8.3 (website data and the in-browser query, site/js/similar-core.js)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.viz import web_data as wd

CORE = Path(__file__).resolve().parents[2] / "site" / "js" / "similar-core.js"

NODE = r"""
const fs = require("fs");
const core = require(process.argv[2]);
const dir = process.argv[3];
const buf = (f) => {
  const b = fs.readFileSync(dir + "/" + f);
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
};
const meta = JSON.parse(fs.readFileSync(dir + "/meta.json"));
const m = core.load(meta, buf("profiles.bin"), buf("cells.bin"));
const a = Number(process.argv[4]);
const r = core.query(m, a, 5);
const rk = core.query(m, a, 50, { maxKm: 0.25 });
const ex = core.explain(m, a, r.results[0].i);
process.stdout.write(JSON.stringify({
  ids: r.results.map((x) => x.i), d: r.results.map((x) => x.distance), d99: r.d99,
  near: rk.results.map((x) => x.km),
  at: core.cellAt(m, meta.lattice.left + 150, meta.lattice.top - 50),
  closest: ex.closest.map((c) => c.name), raw: Array.from(m.raw.slice(0, meta.columns.length)),
}));
"""


def test_encode_decode_roundtrip():
    rng = np.random.default_rng(0)
    raw = pd.DataFrame(
        {"ring250_built": rng.random(100), "log_dist_major": rng.random(100) * 8, "flat": 3.0}
    )
    enc, specs = wd.encode(raw)
    assert enc.dtype == np.dtype("<u2")
    step = np.array([(s["max"] - s["min"]) / wd.Q for s in specs])
    err = np.abs(wd.decode(enc, specs) - raw.to_numpy())
    assert np.all(err[:, :2] <= step[:2] / 2 + 1e-12)
    assert np.allclose(wd.decode(enc, specs)[:, 2], 3.0)  # constant column survives
    assert [s["unit"] for s in specs] == ["%", "m", "°"]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_query_matches_numpy(tmp_path):
    """3 x 4 lattice, 10 AOI cells (2 outside), 3 features: the JS query = numpy."""
    rng = np.random.default_rng(1)
    cls = np.array([[1, 3, 3, 0], [3, 3, 2, 3], [3, 0, 3, 4]], dtype="u1")
    inside = cls.ravel() > 0
    raw = pd.DataFrame(
        rng.random((inside.sum(), 3)), columns=["ring250_built", "ring500_tree", "slope_mean"]
    )
    raw.iloc[:, 1] = 0.0  # a trivial land-cover share: never among the "closest" features
    enc, specs = wd.encode(raw)
    dec = wd.decode(enc, specs)
    mean, sd = dec.mean(0), dec.std(0) + 1.0
    for s, mu, sg in zip(specs, mean, sd, strict=True):
        s["mean"], s["sd"] = float(mu), float(sg)
    meta = {"lattice": {"left": 0.0, "top": 300.0, "cell_m": 100.0, "rows": 3, "cols": 4},
            "n_cells": int(inside.sum()), "quant": wd.Q, "columns": specs,
            "trivial_share": 0.005}  # fmt: skip
    (tmp_path / "meta.json").write_text(json.dumps(meta))
    (tmp_path / "profiles.bin").write_bytes(enc.tobytes())
    (tmp_path / "cells.bin").write_bytes(cls.tobytes() + np.zeros_like(cls).tobytes())
    (tmp_path / "t.js").write_text(NODE)
    a = 0  # the built-up cell at row 0, col 0
    out = subprocess.run(["node", str(tmp_path / "t.js"), str(CORE), str(tmp_path), str(a)],
                         capture_output=True, text=True, check=True)  # fmt: skip
    js = json.loads(out.stdout)

    z = (dec - mean) / sd
    usable = np.flatnonzero(cls.ravel()[inside] == 3)
    d = np.linalg.norm(z[usable] - z[a], axis=1)
    order = np.lexsort((usable, d))
    assert js["ids"] == usable[order][:5].tolist()
    assert np.allclose(js["d"], d[order][:5])
    assert js["d99"] == pytest.approx(np.percentile(d, 99))
    # usable within 250 m of (0,0): (0,1) (1,0) at 100 m, (1,1) at 141 m, (0,2) (2,0) at 200 m
    assert sorted(js["near"]) == pytest.approx([0.1, 0.1, 0.1414214, 0.2, 0.2])
    assert js["at"] == 1  # x=150, y=250 -> row 0, col 1 -> second AOI cell
    assert "ring500_tree" not in js["closest"]
    assert np.allclose(js["raw"], dec[0])
