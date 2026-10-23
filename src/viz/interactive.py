"""Interactive web map (PRD FR-9.2, deliverable D12; Tasks P8.3).

``outputs/map.html``: a folium (Leaflet) map with toggleable layers:

- **Land cover 2023** (ESRI, shown at 30 m), **Three-class map** and **Suitability
  classes** as image overlays (reprojected to WGS84; colours as in the static maps; class N
  is left transparent so the basemap shows);
- **Change-RF score** and **Building similarity** (final run, usable cells);
- **Candidate sites** (all patches; popup with every attribute) and **Top sites**
  (the ``suitability.top_n_sites`` best patches of at least
  ``suitability.top_site_min_area_ha``, numbered);
- **Reference buildings** (a seeded sample of 3,000 current OSM building centroids;
  all 340k would make the page unusable);
- the study-area outline. Basemaps: Esri World Gray Canvas and World Imagery (OSM's
  tile servers refuse pages opened from a local file).

Run: python -m src.viz.interactive
"""

from __future__ import annotations

import argparse
import base64
import io
import logging
from pathlib import Path

import folium
import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402
from rasterio.warp import Resampling, calculate_default_transform, reproject  # noqa: E402

from src.config import load_config  # noqa: E402
from src.features import schema  # noqa: E402
from src.io_utils import setup_logging  # noqa: E402
from src.preprocess.raster import processed_dir  # noqa: E402
from src.similarity import aggregate as ag  # noqa: E402
from src.similarity import rf_model as rm  # noqa: E402
from src.suitability import candidates as cd  # noqa: E402
from src.suitability import score as sc  # noqa: E402
from src.viz import style  # noqa: E402

log = logging.getLogger(__name__)

N_BUILDINGS = 3000
SUIT_COLORS = {1: style.SEQ_BLUE[6], 2: style.SEQ_BLUE[4], 3: style.SEQ_BLUE[2], 4: style.NEUTRAL}
SUIT_NAMES = {1: "S1 (top 10 %)", 2: "S2", 3: "S3", 4: "N (not drawn)"}


def map_path(cfg) -> Path:
    return Path(cfg.paths["outputs"]) / "map.html"


def to_wgs84(path: Path, step: int = 1) -> tuple[np.ndarray, list[list[float]]]:
    """Read band 1 (every ``step``-th pixel), reproject to EPSG:4326 (nearest); (array, bounds)."""
    with rasterio.open(path) as ds:
        h, w = ds.height // step, ds.width // step
        src = ds.read(1, out_shape=(h, w), resampling=Resampling.nearest)
        tr = ds.transform @ ds.transform.scale(ds.width / w, ds.height / h)
        dst_tr, dw, dh = calculate_default_transform(ds.crs, "EPSG:4326", w, h, *ds.bounds)
        nodata = ds.nodata if ds.nodata is not None else 0
        dst = np.full((dh, dw), nodata, dtype=src.dtype)
        reproject(
            src,
            dst,
            src_transform=tr,
            src_crs=ds.crs,
            dst_transform=dst_tr,
            dst_crs="EPSG:4326",
            resampling=Resampling.nearest,
            src_nodata=nodata,
            dst_nodata=nodata,
        )
    west, north = dst_tr.c, dst_tr.f
    east, south = west + dw * dst_tr.a, north + dh * dst_tr.e
    return dst, [[south, west], [north, east]]


def categorical_png(arr: np.ndarray, colors: dict[int, str], alpha: float = 0.85) -> str:
    """Data-URI PNG of a class raster (unlisted codes transparent)."""
    rgba = np.zeros((*arr.shape, 4))
    for code, col in colors.items():
        rgba[arr == code] = to_rgba(col, alpha)
    return _png(rgba)


def sequential_png(arr: np.ndarray, alpha: float = 0.85) -> str:
    """Data-URI PNG of a 0-1 score raster (NaN transparent)."""
    finite = np.isfinite(arr)
    rgba = np.zeros((*arr.shape, 4))
    rgba[finite] = style.SEQUENTIAL(np.clip(arr[finite], 0, 1))
    rgba[finite, 3] = alpha
    return _png(rgba)


def _png(rgba: np.ndarray) -> str:
    buf = io.BytesIO()
    plt.imsave(buf, rgba, format="png")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _overlay(m, url: str, bounds, name: str, show: bool) -> None:
    folium.raster_layers.ImageOverlay(
        url, bounds=bounds, name=name, show=show, interactive=False
    ).add_to(m)


def legend_html(title: str, items: dict[str, str]) -> str:
    """HTML legend block: a title and colour swatches."""
    rows = "".join(
        '<div><span style="display:inline-block;width:12px;height:12px;'
        f'background:{c};margin-right:6px"></span>{n}</div>'
        for n, c in items.items()
    )
    return f'<div style="margin-bottom:6px"><b>{title}</b>{rows}</div>'


def build_map(cfg) -> folium.Map:
    """The folium map with every layer."""
    aoi = cfg.aoi.to_crs(4326)
    x0, y0, x1, y1 = aoi.total_bounds
    m = folium.Map(
        location=[(y0 + y1) / 2, (x0 + x1) / 2], zoom_start=12, tiles=None, control_scale=True
    )
    # OSM's tile servers refuse pages opened from a file (no referrer), CARTO needs a key
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
        name="Esri World Gray Canvas",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri",
        name="Esri World Imagery",
    ).add_to(m)

    latest = int(cfg["years"]["latest"])
    arr, b = to_wgs84(processed_dir(cfg) / f"lulc_esri_{latest}.tif", step=3)
    _overlay(
        m,
        categorical_png(arr, {k: c for k, (_, c) in style.ESRI_COLORS.items()}, 0.75),
        b,
        f"Land cover {latest} (ESRI)",
        False,
    )
    arr, b = to_wgs84(Path(cfg.paths["outputs"]) / "lulc_3class.tif")
    _overlay(m, categorical_png(arr, style.CLASS_COLORS), b, "Three-class map", False)
    arr, b = to_wgs84(sc.class_tif_path(cfg))
    shown = {k: c for k, c in SUIT_COLORS.items() if k != 4}  # N transparent
    _overlay(m, categorical_png(arr, shown), b, "Suitability classes", True)
    for path, name in (
        (rm.rf_probability_path(cfg), "Change-RF score"),
        (ag.similarity_tif_path(cfg), "Building similarity"),
    ):
        arr, b = to_wgs84(path)
        _overlay(m, sequential_png(arr), b, name, False)

    cand = gpd.read_file(cd.gpkg_path(cfg)).to_crs(4326)
    fields = [
        "site_id",
        "area_ha",
        "mean_score",
        "slope_deg",
        "dist_major_road_m",
        "dist_built_m",
        "dominant_cover",
        "agricultural",
    ]
    folium.GeoJson(
        cand[[*fields, "geometry"]],
        name="Candidate sites (all S1 patches)",
        style_function=lambda _f: {"color": style.INK, "weight": 0.6, "fillOpacity": 0.0},
        popup=folium.GeoJsonPopup(fields=fields),
        show=False,
    ).add_to(m)
    top = cand.loc[cand["top_site_rank"].notna()].copy()
    top["top_site_rank"] = top["top_site_rank"].astype(int)
    tfields = ["top_site_rank", *fields]
    grp = folium.FeatureGroup(name=f"Top {len(top)} sites", show=True)
    folium.GeoJson(
        top[[*tfields, "geometry"]],
        style_function=lambda _f: {
            "color": style.CLASS_COLORS[1],
            "weight": 2.5,
            "fillOpacity": 0.15,
        },
        popup=folium.GeoJsonPopup(fields=tfields),
    ).add_to(grp)
    for _, r in top.iterrows():
        folium.Marker(
            [r["lat"], r["lon"]],
            icon=folium.DivIcon(
                html=f'<div style="font-weight:bold;color:{style.INK};'
                f'text-shadow:0 0 3px #fff">{r["top_site_rank"]}</div>'
            ),
        ).add_to(grp)
    grp.add_to(m)

    b = gpd.read_file(
        schema.contract_path(cfg, "C6", snapshot="current"),
        columns=["bldg_id", "building_type", "area_m2"],
    )
    b = b.sample(min(N_BUILDINGS, len(b)), random_state=int(cfg["project"]["random_seed"]))
    pts = b.set_geometry(b.geometry.centroid).to_crs(4326)
    grp = folium.FeatureGroup(name=f"Reference buildings (sample of {len(pts)})", show=False)
    for _, r in pts.iterrows():
        folium.CircleMarker(
            [r.geometry.y, r.geometry.x],
            radius=2,
            color=style.INK_2,
            weight=0.5,
            fill=True,
            popup=f"building {r['bldg_id']}: {r['building_type']}, {r['area_m2']:.0f} m²",
        ).add_to(grp)
    grp.add_to(m)

    folium.GeoJson(
        aoi,
        name="Study area",
        style_function=lambda _f: {"color": style.INK, "weight": 2, "fill": False},
    ).add_to(m)
    legend = (
        legend_html("Suitability", {SUIT_NAMES[k]: c for k, c in SUIT_COLORS.items()})
        + legend_html(
            "Three-class map", {style.CLASS_NAMES[k]: c for k, c in style.CLASS_COLORS.items()}
        )
        + '<div style="font-size:10px;color:#52514e">'
        "Data: Impact Observatory/Esri LULC, ESA WorldCover,"
        " Copernicus DEM, &copy; OpenStreetMap contributors</div>"
    )
    m.get_root().html.add_child(
        folium.Element(
            '<div style="position:fixed;bottom:24px;left:12px;z-index:9999;'
            "background:#fcfcfbee;padding:8px 10px;"
            f'border-radius:4px;font:12px sans-serif;max-width:220px">{legend}</div>'
        )
    )
    folium.LayerControl(collapsed=False).add_to(m)
    return m


def write_map(cfg) -> Path:
    """Build and save ``outputs/map.html``."""
    p = map_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    build_map(cfg).save(str(p))
    log.info("wrote %s (%.1f MB)", p.name, p.stat().st_size / 1e6)
    return p


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "viz")
    write_map(cfg)


if __name__ == "__main__":
    main()
