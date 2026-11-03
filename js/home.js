/* Landing page: the suitability map in the hero sheet and the table of the top 20 sites. */
(function () {
  "use strict";
  const map = L.map("hero-map", { scrollWheelZoom: false, zoomSnap: 0.25 }).setView([12.83, 77.63], 11);
  const bases = Sheet.basemaps();
  bases["Light gray"].addTo(map);
  L.control.scale({ imperial: false, position: "bottomright" }).addTo(map);
  Sheet.legend("Suitability, 2023", [...Sheet.SUIT_LEGEND, ['class="o"', "Top 20 site"]]).addTo(map);
  Sheet.ticks(map, document.getElementById("ticks"));
  map.on("focus click", () => map.scrollWheelZoom.enable());
  map.on("mouseout", () => map.scrollWheelZoom.disable());

  const fmtM = (m) => (m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m / 10) * 10} m`);
  const COVER = { crop: "cropland", range: "rangeland", tree: "trees", bare: "bare ground" };
  const sites = [];

  function popup(p) {
    return `<div class="pop"><h4>Site ${p.rank}</h4><dl>
      <dt>Area</dt><dd>${p.area_ha.toFixed(0)} ha</dd>
      <dt>Mean score</dt><dd>${p.mean_score.toFixed(3)}</dd>
      <dt>Slope</dt><dd>${p.slope_deg.toFixed(1)}°</dd>
      <dt>To major road</dt><dd>${fmtM(p.dist_major_road_m)}</dd>
      <dt>To built-up</dt><dd>${fmtM(p.dist_built_m)}</dd>
      <dt>Cover now</dt><dd>${COVER[p.dominant_cover] || p.dominant_cover}</dd>
      <dt>Centre</dt><dd>${p.lat.toFixed(4)}° N, ${p.lon.toFixed(4)}° E</dd></dl></div>`;
  }

  function select(k) {
    const s = sites[k];
    document.querySelectorAll("#sites-body tr").forEach((tr, j) => tr.setAttribute("aria-selected", String(j === k)));
    document.querySelector(".sheet").scrollIntoView({ behavior: "smooth", block: "center" });
    map.flyToBounds(s.shape.getBounds(), { maxZoom: 15, duration: 0.8, padding: [40, 40] });
    map.once("moveend", () => s.pin.openPopup());
  }

  function renderTable() {
    const body = document.getElementById("sites-body");
    body.innerHTML = sites.map(({ p }) => `<tr tabindex="0">
      <td><span class="rank">${p.rank}</span></td>
      <td class="n">${p.area_ha.toFixed(0)}</td>
      <td class="n">${p.mean_score.toFixed(3)}</td>
      <td class="n">${p.slope_deg.toFixed(1)}°</td>
      <td class="n">${fmtM(p.dist_major_road_m)}</td>
      <td class="n">${fmtM(p.dist_built_m)}</td>
      <td><span class="cover">${COVER[p.dominant_cover] || p.dominant_cover}</span></td>
      <td class="m">${p.lat.toFixed(4)}° N, ${p.lon.toFixed(4)}° E</td></tr>`).join("");
    body.querySelectorAll("tr").forEach((tr, k) => {
      tr.addEventListener("click", () => select(k));
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(k); } });
    });
  }

  Promise.all([
    fetch("data/meta.json").then((r) => r.json()),
    fetch("data/aoi.geojson").then((r) => r.json()),
    fetch("data/sites.geojson").then((r) => r.json()),
  ]).then(([meta, aoi, geo]) => {
    const built = L.imageOverlay("data/built.png", meta.built_overlay, { interactive: false }).addTo(map);
    const suit = L.imageOverlay("data/suitability.png", meta.suitability_overlay, { interactive: false }).addTo(map);
    const outline = L.geoJSON(aoi, { style: { color: "#14212c", weight: 1.5, fill: false, dashArray: "5 4" }, interactive: false }).addTo(map);
    const siteLayer = L.layerGroup().addTo(map);
    geo.features.forEach((f) => {
      const p = f.properties;
      const shape = L.geoJSON(f, { style: { color: "#0d366b", weight: 2, fillOpacity: 0.15 } }).addTo(siteLayer);
      const pin = L.marker([p.lat, p.lon], {
        icon: L.divIcon({ className: "pin pin-sm", html: `<b>${p.rank}</b>`, iconSize: [20, 20] }),
        title: `Site ${p.rank}`, riseOnHover: true,
      }).bindPopup(popup(p)).addTo(siteLayer);
      shape.on("click", () => pin.openPopup());
      sites.push({ p, shape, pin });
    });
    L.control.layers(bases, {
      "Suitability classes": suit, "Built-up land": built, "Top 20 sites": siteLayer, "Study area": outline,
    }, { collapsed: true, position: "topright" }).addTo(map);
    map.fitBounds(outline.getBounds(), { padding: [6, 6] });
    renderTable();
  }).catch((err) => {
    document.getElementById("sites-body").innerHTML =
      `<tr><td colspan="8">Could not load the map data (${err.message}). Reload the page to try again.</td></tr>`;
  });
})();
