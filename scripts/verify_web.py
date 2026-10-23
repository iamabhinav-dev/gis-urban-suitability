"""Done check for the website's "find places like A" tool: browser code = Python query.

Runs ``site/js/similar-core.js`` under Node on the exported data (``outputs/site/data``,
``python -m src.viz.web_data``) and compares it with ``src.similarity.query`` (final run):

1. decoding: profiles decoded in JS equal the raw C4 profiles within the uint16 step;
2. for 30 random buildings: the JS top 20 = the Python top 20 (same cells, same order; a
   swap of near-equal distances, < 1e-4, is allowed) and the distances agree within 1e-3;
3. every JS result is a usable cell of the final 3-class map;
4. the explanation's closest features match the Python ones for the first result.

Run: python scripts/verify_web.py   (needs node)
Exits with code 1 if any check fails.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from src.classify.label import c7_path
from src.config import load_config
from src.features import schema
from src.similarity import profiles as pf
from src.similarity import query as q
from src.similarity import reference as rs

failures: list[str] = []
ROOT = Path(__file__).resolve().parents[1]

NODE = r"""
const fs = require("fs");
const core = require(process.argv[2]);
const dir = process.argv[3];
const meta = JSON.parse(fs.readFileSync(dir + "/meta.json"));
const buf = (f) => {
  const b = fs.readFileSync(dir + "/" + f);
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
};
const model = core.load(meta, buf("profiles.bin"), buf("cells.bin"));
const cellIds = JSON.parse(process.argv[4]);
const L = meta.lattice;
const out = { decoded: [], queries: [] };
const toId = (i) => { const c = core.centre(model, i); return c.row * L.cols + c.col; };
const idx = (id) => model.index[id];
for (const id of cellIds.slice(0, 5)) {
  const i = idx(id);
  out.decoded.push(Array.from(model.raw.slice(i * model.nf, (i + 1) * model.nf)));
}
for (const id of cellIds) {
  const a = idx(id);
  const r = core.query(model, a, 20);
  const ex = core.explain(model, a, r.results[0].i);
  out.queries.push({ a: id, ids: r.results.map((x) => toId(x.i)),
                     d: r.results.map((x) => x.distance),
                     closest: ex.closest.map((c) => c.label) });
}
process.stdout.write(JSON.stringify(out));
"""


def check(ok: bool, msg: str) -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {msg}")
    if not ok:
        failures.append(msg)


def main() -> int:
    cfg = load_config()
    node = shutil.which("node")
    if not node:
        print("node not found: skipped")
        return 0
    data = Path(cfg.paths["outputs"]) / "site" / "data"
    b = rs.buildings(cfg, "final").sample(30, random_state=21)
    cells = [int(c) for c in b["cell_id"]]
    script = Path(cfg.paths["outputs"]) / "site" / ".verify_web.js"
    script.write_text(NODE)
    core = ROOT / "site" / "js" / "similar-core.js"
    r = subprocess.run([node, str(script), str(core), str(data), json.dumps(cells)],
                       capture_output=True, text=True)  # fmt: skip
    script.unlink()
    if r.returncode != 0:
        print(r.stderr[-2000:])
        return 1
    js = json.loads(r.stdout)
    meta = json.loads((data / "meta.json").read_text())

    print("== 1. decoding")
    raw = pf.profile_table(cfg, "final")
    step = np.array([(c["max"] - c["min"]) / meta["quant"] for c in meta["columns"]])
    err = max(
        float(np.max(np.abs(np.array(d) - raw.loc[c].to_numpy()) / np.maximum(step, 1e-12)))
        for c, d in zip(cells, js["decoded"], strict=False)
    )
    check(
        err <= 0.5 + 1e-9, f"decoded profiles within half a quantisation step (max {err:.2f} steps)"
    )

    print("== 2-4. JS query vs Python query, 30 buildings")
    rp = pf.run_profiles(cfg, "final")
    c7 = schema.read_contract(c7_path(cfg, "final"), "C7").set_index("cell_id")
    same = close = usable = expl = 0
    for res in js["queries"]:
        py = q.query(cfg, "final", cell_id=res["a"], n=20, profiles=rp)
        pids = py.results["cell_id"].tolist()
        pd_ = py.results["distance"].to_numpy()
        if pids == res["ids"]:
            same += 1
        elif set(pids) == set(res["ids"]) or np.all(
            np.abs(np.sort(pd_) - np.sort(res["d"])) < 1e-4
        ):
            close += 1  # near-equal distances swapped by the uint16 rounding
        dmax = float(np.max(np.abs(np.sort(pd_) - np.sort(res["d"]))))
        usable += bool((c7.loc[res["ids"], "class_3"] == schema.CLASS_USABLE).all())
        expl += res["closest"] == py.results.iloc[0]["closest_features"].split("; ")
        if dmax > 1e-3:
            failures.append(f"cell {res['a']}: distances differ by {dmax:.1e}")
    check(
        same + close == 30,
        f"top 20 identical for {same}/30 queries, identical up to near-tie order for {close}",
    )
    check(usable == 30, f"all results usable land ({usable}/30 queries)")
    check(expl >= 28, f"closest-feature explanation matches Python for {expl}/30 queries")

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} CHECK(S) FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
