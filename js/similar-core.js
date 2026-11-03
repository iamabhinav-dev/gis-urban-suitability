/*
 * "Find places like A": the single-building similarity query (src/similarity/query.py),
 * reimplemented for the browser. Pure functions, no DOM: also runs under Node for tests.
 *
 * Data (src/viz/web_data.py): meta.json, profiles.bin (uint16 per value, row-major AOI
 * cells), cells.bin (class per lattice position, then suitability class per position).
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.SimilarCore = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /** Build the model from the three files (ArrayBuffers + parsed meta). */
  function load(meta, profilesBuf, cellsBuf) {
    const L = meta.lattice;
    const nPos = L.rows * L.cols;
    const cells = new Uint8Array(cellsBuf);
    const cls = cells.subarray(0, nPos);
    const suit = cells.subarray(nPos, 2 * nPos);
    const index = new Int32Array(nPos).fill(-1);
    const pos = new Int32Array(meta.n_cells);
    let k = 0;
    for (let p = 0; p < nPos; p++) {
      if (cls[p] > 0) { index[p] = k; pos[k] = p; k++; }
    }
    if (k !== meta.n_cells) throw new Error(`cells.bin has ${k} AOI cells, meta says ${meta.n_cells}`);
    const nf = meta.columns.length;
    const q = new Uint16Array(profilesBuf);
    if (q.length !== meta.n_cells * nf) throw new Error("profiles.bin has the wrong size");
    const raw = new Float64Array(q.length);
    const z = new Float64Array(q.length);
    for (let j = 0; j < nf; j++) {
      const c = meta.columns[j];
      const span = c.max > c.min ? c.max - c.min : 1;
      for (let i = 0; i < meta.n_cells; i++) {
        const v = c.min + (q[i * nf + j] / meta.quant) * span;
        raw[i * nf + j] = v;
        z[i * nf + j] = (v - c.mean) / c.sd;
      }
    }
    const usable = [];
    for (let i = 0; i < meta.n_cells; i++) if (cls[pos[i]] === 3) usable.push(i);
    return { meta, nf, cls, suit, index, pos, raw, z, usable: Int32Array.from(usable) };
  }

  /** Lattice row / col of a projected point (null outside the lattice). */
  function rowCol(model, x, y) {
    const L = model.meta.lattice;
    const row = Math.floor((L.top - y) / L.cell_m);
    const col = Math.floor((x - L.left) / L.cell_m);
    if (row < 0 || col < 0 || row >= L.rows || col >= L.cols) return null;
    return { row, col };
  }

  /** AOI cell index of a projected point, or -1. */
  function cellAt(model, x, y) {
    const rc = rowCol(model, x, y);
    if (!rc) return -1;
    return model.index[rc.row * model.meta.lattice.cols + rc.col];
  }

  /** Projected centre (x, y) of AOI cell i. */
  function centre(model, i) {
    const L = model.meta.lattice;
    const p = model.pos[i];
    const row = Math.floor(p / L.cols), col = p % L.cols;
    return { x: L.left + (col + 0.5) * L.cell_m, y: L.top - (row + 0.5) * L.cell_m, row, col };
  }

  function dist(model, i, a) {
    const nf = model.nf, z = model.z;
    let s = 0;
    for (let j = 0; j < nf; j++) { const d = z[i * nf + j] - z[a * nf + j]; s += d * d; }
    return Math.sqrt(s);
  }

  /**
   * Top-n usable cells most similar to cell a (Euclidean distance between standardised
   * profiles, D5). Options: maxKm (only cells within this distance of A).
   * Returns {results: [{rank, i, distance, similarity, km}], d99, nCandidates}.
   */
  function query(model, a, n = 20, opts = {}) {
    const ca = centre(model, a);
    const cand = [];
    for (const i of model.usable) {
      if (i === a) continue;
      let km = null;
      if (opts.maxKm) {
        const c = centre(model, i);
        km = Math.hypot(c.x - ca.x, c.y - ca.y) / 1000;
        if (km > opts.maxKm) continue;
      }
      cand.push({ i, distance: dist(model, i, a), km });
    }
    // similarity scale as in Python: 1 - distance / 99th percentile of all candidate distances
    const sorted = cand.map((c) => c.distance).sort((x, y) => x - y);
    const d99 = sorted.length ? percentile(sorted, 99) || 1 : 1;
    cand.sort((p, q) => p.distance - q.distance || p.i - q.i);
    const results = cand.slice(0, n).map((c, r) => {
      const cc = centre(model, c.i);
      return {
        rank: r + 1, i: c.i, distance: c.distance,
        similarity: Math.max(0, Math.min(1, 1 - c.distance / d99)),
        km: Math.hypot(cc.x - ca.x, cc.y - ca.y) / 1000,
      };
    });
    return { results, d99, nCandidates: cand.length };
  }

  /** numpy-style linear-interpolation percentile of a sorted array. */
  function percentile(sorted, p) {
    if (!sorted.length) return NaN;
    const h = (sorted.length - 1) * (p / 100);
    const lo = Math.floor(h), hi = Math.ceil(h);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (h - lo);
  }

  /** Value as shown to people (metres, %, degrees ...). */
  function shown(col, v) {
    if (col.show === "expm1") return Math.expm1(v);
    if (col.show === "percent") return 100 * v;
    return v;
  }

  /**
   * Feature-by-feature comparison of A and B: gap in standard deviations, shown values,
   * and whether the match is trivial (a land-cover share ~0 at both cells).
   */
  function explain(model, a, b) {
    const nf = model.nf, meta = model.meta;
    const rows = [];
    for (let j = 0; j < nf; j++) {
      const col = meta.columns[j];
      const va = model.raw[a * nf + j], vb = model.raw[b * nf + j];
      const gap = Math.abs(model.z[a * nf + j] - model.z[b * nf + j]);
      const trivial = col.name.startsWith("ring") && Math.abs(va) < meta.trivial_share && Math.abs(vb) < meta.trivial_share;
      rows.push({ name: col.name, label: col.label, unit: col.unit, a: shown(col, va), b: shown(col, vb), gap, trivial });
    }
    const byGap = rows.slice().sort((p, q) => (p.trivial - q.trivial) || (p.gap - q.gap));
    return {
      rows: byGap,
      closest: byGap.filter((r) => !r.trivial).slice(0, 3),
      different: rows.slice().sort((p, q) => q.gap - p.gap).slice(0, 3),
    };
  }

  return { load, rowCol, cellAt, centre, query, explain, percentile, shown };
});
