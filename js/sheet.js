/*
 * Map furniture shared by the pages: Esri basemaps, a legend block and survey-sheet
 * coordinate ticks (degrees and minutes) drawn in the margin around a Leaflet map.
 */
(function (root) {
  "use strict";

  function basemaps() {
    const gray = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      { maxNativeZoom: 16, maxZoom: 19, attribution: "Tiles &copy; Esri" });
    const imagery = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { maxNativeZoom: 18, maxZoom: 19, attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics" });
    return { "Light gray": gray, "Satellite imagery": imagery };
  }

  /** A legend block: title plus rows of [swatch style, label]. */
  function legend(title, rows, position) {
    const c = L.control({ position: position || "bottomleft" });
    c.onAdd = () => {
      const d = L.DomUtil.create("div", "legend");
      d.innerHTML = `<div class="t">${title}</div>` +
        rows.map(([sw, label]) => `<div><i ${sw}></i>${label}</div>`).join("");
      L.DomEvent.disableClickPropagation(d);
      return d;
    };
    return c;
  }

  const STEPS = [1, 2, 3, 5, 10, 15, 30, 60].map((m) => m / 60);

  function dm(v, pos, neg) {
    const a = Math.abs(v);
    let d = Math.floor(a), m = Math.round((a - d) * 60);
    if (m === 60) { d += 1; m = 0; }
    return `${d}°${String(m).padStart(2, "0")}′${v >= 0 ? pos : neg}`;
  }

  /** Draw degree-minute ticks for `map` into `box` (positioned over the map's frame). */
  function ticks(map, box) {
    const mapEl = map.getContainer();
    function draw() {
      const b = map.getBounds(), size = map.getSize();
      const ox = mapEl.offsetLeft, oy = mapEl.offsetTop;
      const pick = (span, px) => STEPS.find((s) => span / s <= Math.max(2, px / 120)) || 1;
      const sx = pick(b.getEast() - b.getWest(), size.x);
      const sy = pick(b.getNorth() - b.getSouth(), size.y);
      const out = [];
      for (let lon = Math.ceil(b.getWest() / sx) * sx; lon <= b.getEast(); lon += sx) {
        const x = map.latLngToContainerPoint([b.getCenter().lat, lon]).x;
        if (x > 24 && x < size.x - 24) out.push(`<span class="x" style="left:${ox + x}px">${dm(lon, "E", "W")}</span>`);
      }
      for (let lat = Math.ceil(b.getSouth() / sy) * sy; lat <= b.getNorth(); lat += sy) {
        const y = map.latLngToContainerPoint([lat, b.getCenter().lng]).y;
        if (y > 12 && y < size.y - 12) out.push(`<span class="y" style="top:${oy + y}px">${dm(lat, "N", "S")}</span>`);
      }
      box.innerHTML = out.join("");
    }
    map.on("move zoom resize", draw);
    draw();
  }

  const SUIT_LEGEND = [
    ['style="background:#0d366b"', "S1, top 10 %"],
    ['style="background:#256abf"', "S2"],
    ['style="background:#6da7ec"', "S3"],
    ['style="background:rgba(235,104,52,.2)"', "Built-up, 2023"],
  ];

  root.Sheet = { basemaps, legend, ticks, SUIT_LEGEND };
})(window);
