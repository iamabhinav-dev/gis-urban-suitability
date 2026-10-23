"""Download OpenStreetMap layers for the AOI + buffer (PRD FR-2.4, FR-2.5; decisions D8, D9).

Two snapshots (named like ``schema.vector_snapshot_for``):
- ``"2018"``: the data as it was on ``osm.snapshot_baseline`` (Overpass ``[date:]``),
  for the validation run. Today's OSM would leak growth after the baseline.
- ``"current"``: today's data, for the final map.

Layers: roads (``highway``), water (``natural=water``, ``waterway``) and buildings
(``building``) for both snapshots; protected areas for ``current`` only (a static
layer). Each layer is saved as ``data/raw/osm/<snapshot>/<layer>.gpkg`` (EPSG:4326)
with a fixed set of tag columns, and recorded in the manifest.

Each tag key is queried separately, key-only where possible (``LOCAL_FILTERS`` keeps
e.g. ``natural=water`` afterwards): Overpass history queries with key=value filters
run out of memory. Overpass mirrors from ``osm.overpass_mirrors`` are tried in order,
each with retries.
osmnx caches raw responses in ``data/raw/osm/cache``, so reruns are fast.

Run: python -m src.download.osm [--snapshot 2018|current] [--layer roads ...] [--force]
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import load_config
from src.download.stac import aoi_bounds_4326
from src.io_utils import (
    DownloadError,
    Manifest,
    manifest_key,
    needs_download,
    record_download,
    setup_logging,
)

log = logging.getLogger(__name__)

# layer -> (osmnx tags, kept geometry types, kept tag columns)
LAYERS: dict[str, tuple[dict, tuple[str, ...], tuple[str, ...]]] = {
    "roads": (
        {"highway": True},
        ("LineString", "MultiLineString"),
        (
            "highway",
            "name",
            "ref",
            "oneway",
            "lanes",
            "surface",
            "service",
            "access",
            "bridge",
            "tunnel",
        ),
    ),
    "water": (
        {"natural": True, "waterway": True},  # natural=water kept locally, see LOCAL_FILTERS
        ("Polygon", "MultiPolygon", "LineString", "MultiLineString"),
        ("natural", "water", "waterway", "name", "intermittent"),
    ),
    "buildings": (
        {"building": True},
        ("Polygon", "MultiPolygon"),
        ("building", "name", "amenity", "shop", "building:levels", "start_date"),
    ),
    "protected": (
        # national parks (e.g. Bannerghatta, relation 8124064) use boundary=national_park
        {"boundary": ["protected_area", "national_park"], "leisure": "nature_reserve"},
        ("Polygon", "MultiPolygon"),
        ("boundary", "leisure", "protect_class", "protection_title", "name"),
    ),
}
# Values filtered on our side after a key-only query: (layer, key) -> value.
# Overpass history queries with key=value filters use the global tag index and run
# out of memory (2 GB) for natural=water; key-only queries are bounded by the bbox.
LOCAL_FILTERS: dict[tuple[str, str], str] = {("water", "natural"): "water"}
SNAPSHOT_LAYERS = {
    "baseline": ("roads", "water", "buildings"),
    "current": ("roads", "water", "buildings", "protected"),
}
OVERPASS_TIMEOUT_S = 900


def snapshots(cfg) -> dict[str, str | None]:
    """Snapshot name -> Overpass date (``current`` is pinned by ``osm.snapshot_current``;
    None = the day of the download)."""
    date = str(cfg["osm"]["snapshot_baseline"])
    cur = cfg["osm"].get("snapshot_current")
    return {date[:4]: f"{date}T00:00:00Z", "current": f"{cur}T00:00:00Z" if cur else None}


def layers_for(snapshot: str) -> tuple[str, ...]:
    """OSM layers of a snapshot (protected areas only for ``current``)."""
    return SNAPSHOT_LAYERS["current" if snapshot == "current" else "baseline"]


def _tag_label(key: str, value) -> str:
    return f"{key}={','.join(value) if isinstance(value, list) else value}"


def osm_path(cfg, snapshot: str, layer: str) -> Path:
    return Path(cfg.paths["data_raw"]) / "osm" / snapshot / f"{layer}.gpkg"


def overpass_settings(date: str | None) -> str:
    """osmnx ``overpass_settings`` string, with ``[date:]`` for a historical snapshot."""
    base = "[out:json][timeout:{timeout}]{maxsize}"
    return base + (f'[date:"{date}"]' if date else "")


def _use_system_dns() -> None:
    """Stop osmnx from pinning the Overpass host to its IPv4 address.

    osmnx resolves the host with ``socket.gethostbyname`` (IPv4 only) and patches
    ``socket.getaddrinfo`` to always use that address. On networks where IPv4 to the
    Overpass servers times out but IPv6 works (seen on Harsh's connection), every
    query then hangs. Normal resolution lets the OS pick a working address.
    """
    import socket

    from osmnx import _http

    _http._config_dns = lambda _url: None
    socket.getaddrinfo = _http._original_getaddrinfo


def _query(bbox, tags: dict, date: str | None, mirror: str) -> gpd.GeoDataFrame:
    import osmnx as ox

    _use_system_dns()
    ox.settings.overpass_url = mirror.removesuffix("/interpreter")
    ox.settings.overpass_settings = overpass_settings(date)
    # only the main instance has the /status endpoint osmnx uses for rate limiting
    ox.settings.overpass_rate_limit = "overpass-api.de" in mirror
    ox.settings.requests_timeout = OVERPASS_TIMEOUT_S
    return ox.features_from_bbox(bbox, tags)


class NoFeatures(DownloadError):
    """The mirrors answered, but with no matching features."""


EMPTY_CONFIRMATIONS = 2  # mirrors that must agree a tag has no features
EMPTY_RETRY_WAIT_S = 20


def _is_empty_answer(exc: BaseException) -> bool:
    return type(exc).__name__ == "InsufficientResponseError"


def fetch_features(cfg, bbox, tags: dict, date: str | None) -> tuple[gpd.GeoDataFrame, str]:
    """Features from the first Overpass mirror that answers; returns (gdf, mirror).

    Raises ``NoFeatures`` if every mirror reports no matching features. osmnx also
    reports an Overpass timeout that way, so callers must sanity-check counts (the
    Phase 2 gate compares them with the ohsome counts from P1.6).
    """
    errors, n_empty = [], 0
    mirrors = cfg["osm"]["overpass_mirrors"]
    for mirror in mirrors:
        what = f"Overpass {mirror} {tags} {date or 'current'}"
        for attempt in (1, 2):
            try:
                return _query(bbox, tags, date, mirror), mirror
            except Exception as exc:  # noqa: BLE001 - network / Overpass errors
                if _is_empty_answer(exc):
                    # an empty answer is an answer: don't retry it on the same mirror
                    n_empty += 1
                    log.info("%s: no matching features", what)
                    break
                log.warning("%s failed (attempt %d/2): %s", what, attempt, exc)
                if attempt == 1:
                    time.sleep(EMPTY_RETRY_WAIT_S)
                else:
                    errors.append(f"{what}: {exc}")
        # osmnx reports a timeout like an empty answer, so confirm on a second mirror
        if n_empty >= min(EMPTY_CONFIRMATIONS, len(mirrors)):
            raise NoFeatures(f"No {tags} features on {n_empty} mirrors ({date or 'current'}).")
        log.warning("mirror failed, trying the next one: %s", mirror)
    if n_empty and not errors:
        raise NoFeatures(f"No {tags} features on any mirror ({date or 'current'}).")
    raise DownloadError(
        f"All Overpass mirrors failed for {tags} ({date or 'current'}):\n  "
        + "\n  ".join(errors)
        + "\nLast resort (PRD §18): use major roads only for the validation run."
    )


def tidy(
    gdf: gpd.GeoDataFrame, geom_types: tuple[str, ...], columns: tuple[str, ...]
) -> gpd.GeoDataFrame:
    """Keep the wanted geometry types and tag columns; add ``osm_type``, ``osm_id``."""
    gdf = gdf[gdf.geometry.notna() & gdf.geom_type.isin(geom_types)]
    out = gdf.reset_index()
    out = out.rename(columns={"element": "osm_type", "element_type": "osm_type", "id": "osm_id"})
    keep = ["osm_type", "osm_id"] + [c for c in columns if c in out.columns]
    out = out[keep + ["geometry"]].copy()
    for c in keep[2:]:
        out[c] = out[c].astype("string")
    return gpd.GeoDataFrame(out, geometry="geometry", crs=gdf.crs or "EPSG:4326")


def download_layer(
    cfg, snapshot: str, layer: str, force: bool = False, manifest: Manifest | None = None
) -> Path:
    """Download one layer of one snapshot, unless it is already there."""
    import osmnx as ox

    manifest = manifest or Manifest.for_config(cfg)
    out = osm_path(cfg, snapshot, layer)
    bbox = aoi_bounds_4326(cfg)
    if not force and not needs_download(out, manifest, cfg.root):
        entry = manifest.get(manifest_key(out, cfg.root)) or {}
        old = entry.get("source", {}).get("bbox_4326")
        old_date = entry.get("source", {}).get("date")
        same_date = old_date == (snapshots(cfg)[snapshot] or "current (download date)")
        if old is not None and np.allclose(old, bbox, atol=1e-9) and same_date:
            log.info("skip %s/%s (exists, checksum matches)", snapshot, out.name)
            return out
        log.info(
            "%s/%s covers a different area or date than requested; re-downloading",
            snapshot,
            out.name,
        )
    date = snapshots(cfg)[snapshot]
    tags, geom_types, columns = LAYERS[layer]
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(Path(cfg.paths["data_raw"]) / "osm" / "cache")
    # one query per tag key: smaller historical queries time out far less often
    parts, mirrors, counts = [], [], {}
    for key, value in tags.items():
        log.info("OSM %s/%s: querying %s=%s", snapshot, layer, key, value)
        try:
            part, mirror = fetch_features(cfg, bbox, {key: value}, date)
        except NoFeatures:
            log.warning(
                "OSM %s/%s: no %s=%s features (or every query timed out)",
                snapshot,
                layer,
                key,
                value,
            )
            counts[_tag_label(key, value)] = 0
            continue
        part = tidy(part, geom_types, columns)
        wanted = LOCAL_FILTERS.get((layer, key))
        if wanted is not None:
            part = part[part[key] == wanted]
            value = wanted
        counts[_tag_label(key, value)] = len(part)
        parts.append(part)
        mirrors.append(mirror)
    if not parts:
        raise DownloadError(f"OSM {snapshot}/{layer}: no features for any of {tags}.")
    gdf = pd.concat(parts, ignore_index=True)
    gdf = gpd.GeoDataFrame(
        gdf.drop_duplicates(subset=["osm_type", "osm_id"]).reset_index(drop=True),
        geometry="geometry",
        crs="EPSG:4326",
    )
    mirror = mirrors[0] if len(set(mirrors)) == 1 else mirrors
    if gdf.empty:
        raise DownloadError(f"OSM {snapshot}/{layer}: no features of types {geom_types}.")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.gpkg")
    gdf.to_file(tmp, driver="GPKG", layer=layer)
    tmp.replace(out)  # only a complete file ever appears at ``out``
    record_download(
        manifest,
        out,
        cfg.root,
        dataset=f"osm-{layer}",
        snapshot=snapshot,
        source={
            "api": "overpass",
            "mirror": mirror,
            "tags": {k: v for k, v in tags.items()},
            "date": date or "current (download date)",
            "bbox_4326": list(bbox),
        },
        crs="EPSG:4326",
        n_features=len(gdf),
        n_features_by_tag=counts,
        geom_types=sorted(gdf.geom_type.unique().tolist()),
    )
    log.info("wrote %s/%s (%d features)", snapshot, out.name, len(gdf))
    return out


def download_osm(
    cfg,
    snapshot_names: list[str] | None = None,
    layer_names: list[str] | None = None,
    force: bool = False,
) -> list[Path]:
    """All layers for all snapshots (or the given subset)."""
    manifest = Manifest.for_config(cfg)
    paths = []
    for snap in snapshot_names or list(snapshots(cfg)):
        for layer in layers_for(snap):
            if layer_names and layer not in layer_names:
                continue
            paths.append(download_layer(cfg, snap, layer, force=force, manifest=manifest))
    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", action="append", help="2018 and/or current (default both)")
    parser.add_argument("--layer", action="append", choices=list(LAYERS))
    parser.add_argument("--force", action="store_true", help="download even if files exist")
    args = parser.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "download")
    download_osm(cfg, args.snapshot, args.layer, force=args.force)


if __name__ == "__main__":
    main()
