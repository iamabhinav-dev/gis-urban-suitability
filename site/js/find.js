/*
 * "Find places like A" page: map, controls and result list around SimilarCore.
 * State is kept in the URL hash (#a=lat,lon&n=20&r=0) so a query can be shared.
 */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const SUIT = { 1: ["S1", "var(--s1)"], 2: ["S2", "var(--s2)"], 3: ["S3", "var(--s3)", "light"], 4: ["N", "var(--excluded)", "light"] };
  const CLASS = { 1: "built-up land", 2: "forest", 3: "usable land", 4: "excluded land (water, protected or steep)" };
  const COLOR = { a: "#eb6834", result: "#2a78d6", selected: "#0d366b" };
  const state = { model: null, a: -1, query: null, sel: -1 };

  // ---------------------------------------------------------------- map
  const map = L.map("map", { zoomSnap: 0.5 }).setView([12.83, 77.63], 11);
  const bases = Sheet.basemaps();
  bases["Light gray"].addTo(map);
  const resultLayer = L.layerGroup().addTo(map);
  const aLayer = L.layerGroup().addTo(map);
  const layers = L.control.layers(bases, {}, { collapsed: true }).addTo(map);
  L.control.scale({ imperial: false, position: "bottomright" }).addTo(map);
  Sheet.legend("Legend", [
    ['class="o" style="background:#eb6834;box-shadow:0 0 0 1px #eb6834"', "A, your chosen place"],
    ['class="o" style="background:#256abf;box-shadow:0 0 0 1px #256abf"', "Match, numbered by rank"],
    ['style="background:rgba(109,167,236,.55)"', "Usable land (searched)"],
  ]).addTo(map);
  map.attributionControl.addAttribution("&copy; OpenStreetMap contributors; land cover &copy; Impact Observatory, Microsoft, Esri");

  let toUtm, toLatLng;

  // ---------------------------------------------------------------- data
  async function fetchBuf(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return r.arrayBuffer();
  }

  async function init() {
    try {
      const [meta, prof, cells, aoi] = await Promise.all([
        fetch("data/meta.json").then((r) => r.json()),
        fetchBuf("data/profiles.bin"), fetchBuf("data/cells.bin"),
        fetch("data/aoi.geojson").then((r) => r.json()),
      ]);
      state.model = SimilarCore.load(meta, prof, cells);
      proj4.defs("AOI", meta.proj4);
      toUtm = (lat, lon) => proj4("WGS84", "AOI", [lon, lat]);
      toLatLng = (x, y) => { const p = proj4("AOI", "WGS84", [x, y]); return [p[1], p[0]]; };

      const usable = L.imageOverlay("data/usable.png", meta.usable_overlay, { opacity: 1, interactive: false }).addTo(map);
      const outline = L.geoJSON(aoi, { style: { color: "#14212c", weight: 1.5, fill: false, dashArray: "5 4" }, interactive: false }).addTo(map);
      const suit = L.imageOverlay("data/suitability.png", meta.suitability_overlay, { interactive: false });
      layers.addOverlay(usable, "Usable land (searched)");
      layers.addOverlay(suit, "Suitability classes S1–S3");
      layers.addOverlay(outline, "Study area");
      map.fitBounds(outline.getBounds(), { padding: [10, 10] });
      renderExamples(meta.examples);
      status(`Ready. ${meta.n_usable.toLocaleString()} usable cells can be matched. Click the map to choose A.`);
      fromHash();
    } catch (err) {
      status(`Could not load the data: ${err.message}`, true);
    }
  }

  // ---------------------------------------------------------------- helpers
  function status(msg, error) {
    const el = $("#status");
    el.textContent = msg;
    el.classList.toggle("error", !!error);
    el.hidden = !msg;
  }

  function cellCorners(i) {
    const c = SimilarCore.centre(state.model, i), h = state.model.meta.lattice.cell_m / 2;
    return [toLatLng(c.x - h, c.y - h), toLatLng(c.x + h, c.y - h), toLatLng(c.x + h, c.y + h), toLatLng(c.x - h, c.y + h)];
  }

  function cellLatLng(i) {
    const c = SimilarCore.centre(state.model, i);
    return toLatLng(c.x, c.y);
  }

  function badge(i) {
    const s = SUIT[state.model.suit[state.model.pos[i]]];
    if (!s) return "";
    return `<span class="badge${s[2] ? " light" : ""}" style="--c:${s[1]}" title="Suitability class ${s[0]}">${s[0]}</span>`;
  }

  function fmt(row, v) {
    if (row.unit === "%") return `${v.toFixed(v < 9.95 && v > 0.05 ? 1 : 0)} %`;
    if (row.name.startsWith("log_dist")) return v >= 1000 ? `${(v / 1000).toFixed(1)} km` : `${Math.round(v / 10) * 10} m`;
    if (row.unit === "m") return `${Math.round(v)} m`;
    if (row.unit === "°") return `${v.toFixed(1)}°`;
    return `${v.toFixed(1)} ${row.unit}`;
  }

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  // ---------------------------------------------------------------- choose A
  function renderExamples(examples) {
    const box = $("#examples");
    box.innerHTML = "";
    for (const ex of examples) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = ex.label;
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", () => chooseLatLng(ex.lat, ex.lon, ex.label, true));
      box.appendChild(b);
    }
  }

  map.on("click", (e) => { if (state.model) chooseLatLng(e.latlng.lat, e.latlng.lng, null, false); });
  $("#opt-n").addEventListener("change", () => run(false));
  $("#opt-r").addEventListener("change", () => run(true));
  $("#fit").addEventListener("click", fitAll);

  function chooseLatLng(lat, lon, label, fly) {
    const [x, y] = toUtm(lat, lon);
    const i = SimilarCore.cellAt(state.model, x, y);
    if (i < 0) { status("That point is outside the study area. Click inside the dashed outline."); return; }
    state.a = i;
    state.aLabel = label;
    state.aLatLng = [lat, lon];
    document.querySelectorAll("#examples .chip").forEach((c) => c.setAttribute("aria-pressed", String(c.textContent === label)));
    run(true, fly);
  }

  // ---------------------------------------------------------------- query
  function run(refit, fly) {
    if (state.a < 0) return;
    const n = +$("#opt-n").value, r = +$("#opt-r").value;
    const t0 = performance.now();
    state.query = SimilarCore.query(state.model, state.a, n, { maxKm: r || undefined });
    state.sel = -1;
    const ms = performance.now() - t0;
    const [lat, lon] = state.aLatLng;
    history.replaceState(null, "", `#a=${lat.toFixed(5)},${lon.toFixed(5)}&n=${n}&r=${r}`);
    status(state.query.results.length
      ? `Compared A with ${state.query.nCandidates.toLocaleString()} usable cells in ${ms.toFixed(0)} ms.`
      : "No usable land within this distance of A. Widen the search.");
    renderA();
    renderResults();
    renderCompare();
    if (refit) fitAll(fly);
  }

  function renderA() {
    const m = state.model, a = state.a, cls = m.cls[m.pos[a]];
    aLayer.clearLayers();
    L.polygon(cellCorners(a), { color: COLOR.a, weight: 2, fillOpacity: 0.35 }).addTo(aLayer);
    L.marker(state.aLatLng, {
      icon: L.divIcon({ className: "pin pin-a", html: "<b>A</b>", iconSize: [30, 30] }),
      keyboard: false, title: "A",
    }).addTo(aLayer);
    const ex = SimilarCore.explain(m, a, a).rows;
    const pick = (name) => ex.find((r) => r.name === name);
    const facts = ["ring500_built", "log_dist_major", "road_density", "slope_mean"].map((k) => {
      const r = pick(k);
      return `<div><dt>${esc(r.label)}</dt><dd>${fmt(r, r.a)}</dd></div>`;
    }).join("");
    const card = $("#a-card");
    card.innerHTML = `
      <div class="a-head"><span class="pin pin-a static">A</span>
        <div><b>${state.aLabel ? esc(state.aLabel) : "Your chosen place"}</b> <span class="muted small">· ${CLASS[cls]}</span>
        <div class="coords">${state.aLatLng[0].toFixed(5)}° N, ${state.aLatLng[1].toFixed(5)}° E</div></div></div>
      <dl class="facts small">${facts}</dl>`;
    card.hidden = false;
  }

  function renderResults() {
    const res = state.query.results;
    resultLayer.clearLayers();
    const list = $("#results");
    list.innerHTML = "";
    $("#results-wrap").hidden = !res.length;
    res.forEach((r, k) => {
      const sq = L.polygon(cellCorners(r.i), { color: COLOR.result, weight: 1.5, fillOpacity: 0.5 }).addTo(resultLayer);
      const pin = L.marker(cellLatLng(r.i), {
        icon: L.divIcon({ className: "pin pin-r", html: `<b>${r.rank}</b>`, iconSize: [24, 24] }),
        title: `Match ${r.rank}`, riseOnHover: true,
      }).addTo(resultLayer);
      sq.on("click", (e) => { L.DomEvent.stopPropagation(e); select(k, false); });
      pin.on("click", (e) => { L.DomEvent.stopPropagation(e); select(k, false); });
      r.layers = [sq, pin];

      const ex = SimilarCore.explain(state.model, state.a, r.i);
      const li = document.createElement("li");
      li.innerHTML = `
        <button type="button" class="result">
          <span class="rk">${r.rank}</span>
          <span class="body">
            <span class="top"><span class="pct">${Math.round(r.similarity * 100)} %</span>${badge(r.i)}
              <span class="km">${r.km.toFixed(1)} km from A</span></span>
            <span class="bar"><span style="width:${(r.similarity * 100).toFixed(1)}%"></span></span>
            <span class="why">Closest on ${ex.closest.map((c) => esc(c.label)).join(", ")}</span>
          </span>
        </button>`;
      li.querySelector("button").addEventListener("click", () => select(k, true));
      list.appendChild(li);
    });
  }

  function select(k, pan) {
    state.sel = k;
    const res = state.query.results;
    res.forEach((r, j) => {
      const on = j === k;
      r.layers[0].setStyle({ color: on ? COLOR.selected : COLOR.result, weight: on ? 3 : 1.5, fillOpacity: on ? 0.8 : 0.5 });
      if (on) r.layers[1].setZIndexOffset(1000); else r.layers[1].setZIndexOffset(0);
      r.layers[1].getElement()?.classList.toggle("pin-selected", on);
    });
    document.querySelectorAll("#results .result").forEach((b, j) => b.setAttribute("aria-pressed", String(j === k)));
    renderCompare();
    if (k < 0) return;
    const r = res[k];
    if (pan) map.flyTo(cellLatLng(r.i), Math.max(map.getZoom(), 15), { duration: 0.6 });
    else document.querySelectorAll("#results li")[k]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function renderCompare() {
    const box = $("#compare");
    if (state.sel < 0) { box.hidden = true; return; }
    const r = state.query.results[state.sel];
    const ex = SimilarCore.explain(state.model, state.a, r.i);
    const [lat, lon] = cellLatLng(r.i);
    const rows = ex.rows.map((row) => {
      const w = Math.min(row.gap / 2, 1) * 100;
      return `<tr${row.trivial ? ' class="trivial"' : ""}><th scope="row">${esc(row.label)}</th>
        <td class="n">${fmt(row, row.a)}</td><td class="n">${fmt(row, row.b)}</td>
        <td><span class="gap" title="${row.gap.toFixed(2)} standard deviations apart"><span style="width:${w.toFixed(0)}%"></span></span></td></tr>`;
    }).join("");
    box.innerHTML = `
      <div class="compare-head">
        <h2>A compared with match ${r.rank}</h2>
        <button type="button" class="linkish small" id="close-compare">Close</button>
      </div>
      <p class="small muted" style="margin:0 0 8px"><span class="mono">${lat.toFixed(5)}° N, ${lon.toFixed(5)}° E</span> ·
        ${Math.round(r.similarity * 100)} % similar ${badge(r.i)} ·
        <a href="https://www.google.com/maps/@${lat.toFixed(5)},${lon.toFixed(5)},17z" target="_blank" rel="noopener">open in Google Maps</a></p>
      <p class="small" style="margin:0 0 8px"><b>Most different:</b> ${ex.different.map((d) => esc(d.label)).join(", ")}</p>
      <div class="table-wrap"><table class="small">
        <thead><tr><th scope="col">Surroundings</th><th class="n" scope="col">A</th><th class="n" scope="col">Match</th><th scope="col">Gap</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      <p class="small muted">Sorted from most to least alike. Greyed rows are land-cover types absent
        at both places; agreeing on them says little.</p>`;
    box.hidden = false;
    $("#close-compare").addEventListener("click", () => select(-1, false));
  }

  function fitAll(fly) {
    if (!state.query) return;
    const pts = [state.aLatLng, ...state.query.results.map((r) => cellLatLng(r.i))];
    const b = L.latLngBounds(pts);
    const opts = { padding: [40, 40], maxZoom: 15 };
    if (fly === true) map.flyToBounds(b, { ...opts, duration: 0.8 });
    else map.fitBounds(b, opts);
  }

  // ---------------------------------------------------------------- shareable URL
  function fromHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    if (p.get("n")) $("#opt-n").value = p.get("n");
    if (p.get("r")) $("#opt-r").value = p.get("r");
    const a = (p.get("a") || "").split(",").map(Number);
    if (a.length === 2 && a.every(Number.isFinite)) chooseLatLng(a[0], a[1], null, false);
  }

  init();
})();
