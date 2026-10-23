"""Planetary Computer STAC helpers shared by the raster downloaders (LULC, DEM).

``fetch_raster`` searches a collection over the AOI + buffer, reads only the needed
window from each Cloud-Optimised GeoTIFF, mosaics the tiles and writes one
compressed GeoTIFF, recording it in the manifest. Tiles in different CRSs (e.g. two
UTM zones) are warped to the project CRS.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, transform_bounds

from src.io_utils import (
    DownloadError,
    Manifest,
    manifest_key,
    needs_download,
    raster_info,
    record_download,
    retry,
)

log = logging.getLogger(__name__)

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


def aoi_bounds_4326(cfg) -> tuple[float, float, float, float]:
    """(west, south, east, north) in EPSG:4326 that fully cover the reference grid.

    The reference grid (src/preprocess/raster.py) is the *rectangle* around the AOI
    + ``aoi.buffer_m``, grown to whole cells. The rectangle's corners reach beyond the
    rounded corners of the buffered AOI, so we transform the rectangle itself (densified,
    so edges that curve in lat/lon are covered) and add two cells of margin.
    """
    cell = float(cfg.cell_size_m)
    left, bottom, right, top = cfg.aoi_projected.buffer(
        float(cfg["aoi"].get("buffer_m", 0))
    ).total_bounds
    left, bottom = (
        np.floor(left / cell) * cell - 2 * cell,
        np.floor(bottom / cell) * cell - 2 * cell,
    )
    right, top = np.ceil(right / cell) * cell + 2 * cell, np.ceil(top / cell) * cell + 2 * cell
    return tuple(
        float(v) for v in transform_bounds(cfg.crs, 4326, left, bottom, right, top, densify_pts=51)
    )


def search_items(
    collection: str, bbox, datetime: str | None = None, query: dict | None = None
) -> list:
    """STAC items (signed hrefs) intersecting ``bbox``, sorted by id; retried on failure."""
    import planetary_computer as pc
    import pystac_client

    def _search():
        catalog = pystac_client.Client.open(STAC_URL, modifier=pc.sign_inplace)
        search = catalog.search(collections=[collection], bbox=bbox, datetime=datetime, query=query)
        return sorted(search.items(), key=lambda i: i.id)

    items = retry(_search, what=f"STAC search {collection} {datetime or ''}")
    if not items:
        raise DownloadError(f"No {collection} items for bbox {bbox} ({datetime}).")
    return items


def snap_bounds(
    src, bounds: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    """Grow ``bounds`` (in the source CRS) outward to whole pixels of the source grid.

    Without this, ``rasterio.merge`` starts the output grid at the raw bounds, which
    shifts every pixel by a fraction of a cell and resamples the data.
    """
    rx, ry = abs(src.transform.a), abs(src.transform.e)
    x0, y0 = src.transform.c, src.transform.f
    eps = 1e-6
    left = x0 + np.floor((bounds[0] - x0) / rx + eps) * rx
    right = x0 + np.ceil((bounds[2] - x0) / rx - eps) * rx
    top = y0 - np.floor((y0 - bounds[3]) / ry + eps) * ry
    bottom = y0 - np.ceil((y0 - bounds[1]) / ry - eps) * ry
    return (float(left), float(bottom), float(right), float(top))


def mosaic_to_file(
    hrefs: list[str],
    bounds_4326: tuple[float, float, float, float],
    out: Path,
    *,
    dst_crs,
    resampling: Resampling,
    nodata: float | None = None,
) -> None:
    """Mosaic the COGs over ``bounds_4326`` and write a tiled, compressed GeoTIFF.

    If all sources share one CRS the data keep their native pixel grid: the bounds are
    snapped to it, so values are copied, never resampled.
    Otherwise every source is warped to ``dst_crs`` at the finest source resolution.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    sources = [retry(lambda h=h: rasterio.open(h), what=f"open {h.split('?')[0]}") for h in hrefs]
    try:
        crss = {s.crs.to_string() for s in sources}
        nd = nodata if nodata is not None else sources[0].nodata
        if len(crss) == 1:
            src_crs = sources[0].crs
            b = snap_bounds(
                sources[0], transform_bounds(4326, src_crs, *bounds_4326, densify_pts=21)
            )
            res = (abs(sources[0].transform.a), abs(sources[0].transform.e))
            arr, transform = retry(
                lambda: merge(sources, bounds=b, res=res, nodata=nd, resampling=resampling),
                what="read tiles",
            )
            crs = src_crs
        else:
            log.info("tiles in %d CRSs; warping to %s", len(crss), dst_crs)
            b = transform_bounds(4326, dst_crs, *bounds_4326, densify_pts=21)
            # finest source resolution, expressed in the destination CRS's units
            res = min(
                abs(calculate_default_transform(s.crs, dst_crs, s.width, s.height, *s.bounds)[0].a)
                for s in sources
            )
            width = int(np.ceil((b[2] - b[0]) / res))
            height = int(np.ceil((b[3] - b[1]) / res))
            transform = rasterio.transform.from_origin(b[0], b[3], res, res)
            arr = np.full(
                (1, height, width), nd if nd is not None else 0, dtype=sources[0].dtypes[0]
            )
            for s in sources:
                tmp = np.full_like(arr, arr.flat[0])
                reproject(
                    rasterio.band(s, 1),
                    tmp[0],
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    dst_nodata=nd,
                    resampling=resampling,
                )
                fill = tmp != nd if nd is not None else tmp != 0
                arr[fill] = tmp[fill]
            crs = dst_crs
        profile = {
            "driver": "GTiff",
            "height": arr.shape[1],
            "width": arr.shape[2],
            "count": 1,
            "dtype": arr.dtype,
            "crs": crs,
            "transform": transform,
            "nodata": nd,
            "compress": "deflate",
            "tiled": True,
            "blockxsize": 512,
            "blockysize": 512,
        }
        tmp_out = out.with_suffix(".tmp.tif")
        with rasterio.open(tmp_out, "w", **profile) as dst:
            dst.write(arr)
        tmp_out.replace(out)  # only a complete file ever appears at ``out``
    finally:
        for s in sources:
            s.close()


def fetch_raster(
    cfg,
    *,
    collection: str,
    asset: str,
    out: Path,
    dataset: str,
    resampling: Resampling,
    datetime: str | None = None,
    query: dict | None = None,
    item_filter=None,
    year: int | None = None,
    nodata: float | None = None,
    force: bool = False,
    manifest: Manifest | None = None,
) -> Path:
    """Download one mosaicked raster for the AOI + buffer, unless it is already there."""
    manifest = manifest or Manifest.for_config(cfg)
    bbox = aoi_bounds_4326(cfg)
    if not force and not needs_download(out, manifest, cfg.root):
        entry = manifest.get(manifest_key(out, cfg.root)) or {}
        old = entry.get("source", {}).get("bbox_4326")
        if old is not None and np.allclose(old, bbox, atol=1e-9):
            log.info("skip %s (exists, checksum matches)", out.name)
            return out
        log.info(
            "%s covers a different area than requested (AOI or buffer changed); re-downloading",
            out.name,
        )
    items = search_items(collection, bbox, datetime, query)
    if item_filter is not None:
        items = [i for i in items if item_filter(i)]
        if not items:
            raise DownloadError(f"No {collection} items left after filtering ({datetime}).")
    log.info("%s: %d item(s): %s", out.name, len(items), [i.id for i in items])
    mosaic_to_file(
        [i.assets[asset].href for i in items],
        bbox,
        out,
        dst_crs=cfg.crs,
        resampling=resampling,
        nodata=nodata,
    )
    source: dict[str, Any] = {
        "stac": STAC_URL,
        "collection": collection,
        "asset": asset,
        "items": [i.id for i in items],
        "hrefs": [i.assets[asset].href.split("?")[0] for i in items],  # unsigned
        "bbox_4326": list(bbox),
    }
    entry = record_download(
        manifest, out, cfg.root, dataset=dataset, source=source, year=year, **raster_info(out)
    )
    log.info("wrote %s (%.1f MB)", out.name, entry["size_bytes"] / 1e6)
    return out
