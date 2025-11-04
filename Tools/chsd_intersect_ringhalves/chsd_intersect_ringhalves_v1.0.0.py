#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CHSD Ringhalf Intersection Utility
----------------------------------
Combine two CHSD motif catalogs (e.g., ESA PR4 Ringhalf-1 & Ringhalf-2),
keep only detections present in BOTH, enrich with per-ringhalf scores,
and export an intersected JSON catalog + diagnostic plots.

Assumptions
* Catalogs contain a list of JSON objects OR are NDJSON (one object per line).
* Each object follows the "motif_catalog_format_(JSON)" shown by Lina:
  {
    "motif_type": "hexagonal_symmetry_cmb",
    "coherence_score": 1.0,
    "coordinates": {"system": "galactic", "lon_deg": 135.0, "lat_deg": 89.26},
    "pixel_index": 1
  }
* Coordinates are GALACTIC (lon/lat in degrees).  Pixel indices are HEALPix RING.
* NSIDE, PATCH SIZE, and THRESHOLD are parsed from the filename pattern:
    ns-<nside>_ps-<patch>_th-<thr>
  You may override with CLI flags.

Outputs
* <stem>_full_ns-<n>_ps-<p>_th-<t>.json       (intersection; enriched fields)
* <stem>_full_ns-<n>_ps-<p>_th-<t>.png        (mollweide of mean scores)
* <stem>_summary.csv                          (simple counts & stats)
* <stem>_manifest.json                        (provenance)
* Optional:
  - <stem>_diff.png                           (RH1−RH2 map)
  - <stem>_only-rh1.json / <stem>_only-rh2.json

Usage
  python chsd_intersect_ringhalves.py     --input1 HFI_SkyMap_100-..._full-ringhalf-1_ns-256_ps-32_th-0.92.json     --input2 HFI_SkyMap_100-..._full-ringhalf-2_ns-256_ps-32_th-0.92.json
"""
import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np

# Headless plotting
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import healpy as hp
except Exception as e:
    hp = None
    _hp_import_error = e

# -----------------------------
# Helpers
# -----------------------------

FNAME_PARAMS = re.compile(r"ns-(\d+)_ps-(\d+)_th-([0-9.]+)")

def parse_params_from_name(path: Path) -> Tuple[int, int, float]:
    """Extract (nside, patch_size, threshold) from filename; raise if missing."""
    m = FNAME_PARAMS.search(path.name)
    if not m:
        raise ValueError(f"Could not parse ns/ps/th from filename: {path.name}")
    return int(m.group(1)), int(m.group(2)), float(m.group(3))

def read_catalog(path: Path) -> List[Dict[str, Any]]:
    """Read JSON list or NDJSON. Return list of dicts."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text[0] == "[":
        data = json.loads(text)
        if isinstance(data, dict) and "records" in data:
            data = data["records"]
        if not isinstance(data, list):
            raise ValueError(f"Top-level JSON not a list in {path}")
        return data
    # NDJSON
    out = []
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"Bad JSON on line {i+1} of {path}: {e}") from e
    return out

def ensure_healpy():
    if hp is None:
        raise RuntimeError(
            "healpy is required for this script (for HEALPix pixelization & plots).\n"
            f"Import error: {_hp_import_error}"
        )

def gal_to_theta_phi(lon_deg: float, lat_deg: float) -> Tuple[float, float]:
    """Galactic lon/lat (deg) -> theta (0..pi), phi (0..2pi) for HEALPix."""
    phi = math.radians(lon_deg % 360.0)
    theta = math.radians(90.0 - lat_deg)  # colatitude
    return theta, phi

def catalog_to_pixel_map(catalog: List[Dict[str, Any]], nside: int) -> Dict[int, Dict[str, Any]]:
    """Map pixel_index -> record (dedup by keeping max coherence_score)."""
    ensure_healpy()
    pix_map: Dict[int, Dict[str, Any]] = {}
    for rec in catalog:
        # Resolve pixel index
        pix = rec.get("pixel_index")
        if pix is None:
            coords = rec.get("coordinates", {})
            if str(coords.get("system", "")).lower() != "galactic":
                raise ValueError("Only galactic coordinates are supported.")
            lon = float(coords["lon_deg"])  # may raise KeyError, that's fine
            lat = float(coords["lat_deg"])
            theta, phi = gal_to_theta_phi(lon, lat)
            pix = int(hp.ang2pix(nside, theta, phi, nest=False))
            rec["pixel_index"] = pix

        # Keep the record with highest coherence_score if duplicates
        score = float(rec.get("coherence_score", 0.0))
        prev = pix_map.get(pix)
        if prev is None or float(prev.get("coherence_score", 0.0)) < score:
            pix_map[pix] = rec
    return pix_map

def intersect_catalogs(pm1: Dict[int, Dict[str, Any]],
                       pm2: Dict[int, Dict[str, Any]],
                       score_delta_max: float = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (intersection_records, only1, only2).  Enrich intersection with score fields."""
    keys1 = set(pm1.keys())
    keys2 = set(pm2.keys())
    inter = keys1 & keys2
    only1 = [pm1[k] for k in (keys1 - keys2)]
    only2 = [pm2[k] for k in (keys2 - keys1)]

    out = []
    for k in sorted(inter):
        r1 = pm1[k]
        r2 = pm2[k]
        s1 = float(r1.get("coherence_score", 0.0))
        s2 = float(r2.get("coherence_score", 0.0))
        mean = 0.5 * (s1 + s2)
        delta = abs(s1 - s2)
        rec = dict(r1)  # base on r1
        rec["score_rh1"] = s1
        rec["score_rh2"] = s2
        rec["score_mean"] = mean
        rec["score_min"] = min(s1, s2)
        rec["delta_score"] = delta
        if score_delta_max is None or delta <= score_delta_max:
            out.append(rec)
    return out, only1, only2

def save_ndjson(path: Path, records: List[Dict[str, Any]]):
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def make_intersection_map(inter: List[Dict[str, Any]], nside: int) -> np.ndarray:
    ensure_healpy()
    m = np.full(hp.nside2npix(nside), np.nan, dtype=float)
    for r in inter:
        pix = int(r["pixel_index"])
        m[pix] = float(r.get("score_mean", r.get("coherence_score", 0.0)))
    return m

def make_difference_map(pm1: Dict[int, Dict[str, Any]], pm2: Dict[int, Dict[str, Any]], nside: int) -> np.ndarray:
    ensure_healpy()
    m = np.full(hp.nside2npix(nside), np.nan, dtype=float)
    union = set(pm1.keys()) | set(pm2.keys())
    for k in union:
        s1 = float(pm1.get(k, {}).get("coherence_score", np.nan))
        s2 = float(pm2.get(k, {}).get("coherence_score", np.nan))
        if np.isnan(s1) and np.isnan(s2):
            continue
        if np.isnan(s1): s1 = 0.0
        if np.isnan(s2): s2 = 0.0
        m[k] = s1 - s2
    return m

def plot_mollweide(data: np.ndarray,
                   title: str,
                   out_png: Path,
                   vmin: float = None,
                   vmax: float = None,
                   unit: str = "Coherence Score",
                   cmap: str = "viridis",
                   cbar: bool = True):
    ensure_healpy()
    hp.mollview(data, title=title, unit=unit, min=vmin, max=vmax, cmap=cmap, cbar=cbar, notext=False)
    hp.graticule(ls=":", alpha=0.8)
    plt.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close()

def stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"count": 0, "mean": np.nan, "min": np.nan, "max": np.nan}
    arr = np.array(values, dtype=float)
    return {
        "count": int(arr.size),
        "mean": float(np.nanmean(arr)),
        "min": float(np.nanmin(arr)),
        "max": float(np.nanmax(arr)),
    }

def write_summary_csv(path: Path, counts: Dict[str, Any], score_stats: Dict[str, Any]):
    import csv
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in counts.items():
            w.writerow([k, v])
        for k, v in score_stats.items():
            w.writerow([k, v])

# -----------------------------
# Main
# -----------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description="Intersect two CHSD motif catalogs (Ringhalf-1 & Ringhalf-2)")
    p.add_argument("--input1", required=True, type=Path, help="RH1 catalog JSON/NDJSON")
    p.add_argument("--input2", required=True, type=Path, help="RH2 catalog JSON/NDJSON")
    p.add_argument("--output-stem", type=str, default=None,
                   help="Output stem (prefix). If omitted, inferred from input names with '-ringhalf-*' removed.")
    p.add_argument("--nside", type=int, default=None, help="Override NSIDE (if not parsable from filename)")
    p.add_argument("--patch-size", type=int, default=None, help="Override PATCH size (if not parsable) ")
    p.add_argument("--threshold", type=float, default=None, help="Override THRESHOLD (if not parsable) ")
    p.add_argument("--score-delta-max", type=float, default=None,
                   help="If set, drop intersections with |RH1-RH2| > this (e.g., 0.1 for very conservative)." )
    p.add_argument("--emit-diff", action="store_true", help="Also write a RH1−RH2 difference map PNG.")
    p.add_argument("--emit-only-sets", action="store_true", help="Also write only-rh1/only-rh2 JSONs.")
    p.add_argument("--ndjson", action="store_true", help="Write NDJSON instead of JSON array for intersection.")
    args = p.parse_args(argv)

    # Parse parameters from filenames unless overridden
    try:
        n1, p1, t1 = parse_params_from_name(args.input1)
        n2, p2, t2 = parse_params_from_name(args.input2)
    except ValueError:
        n1 = p1 = t1 = None
        n2 = p2 = t2 = None

    nside = args.nside or n1 or n2
    patch = args.patch_size or p1 or p2
    thr = args.threshold or t1 or t2

    if nside is None or patch is None or thr is None:
        raise SystemExit("NSIDE, PATCH, and THRESHOLD must be provided via filename pattern or CLI overrides.")

    # Build output stem
    if args.output_stem:
        stem = args.output_stem
    else:
        # Remove '-ringhalf-1' or '-ringhalf-2' from a base prefix
        def strip_ringhalf(name: str) -> str:
            return name.replace("_ringhalf-1", "").replace("-ringhalf-1", "")                        .replace("_ringhalf-2", "").replace("-ringhalf-2", "")
        base = strip_ringhalf(args.input1.stem)
        # Drop trailing ns/ps/th if present to rebuild consistently:
        base = FNAME_PARAMS.split(base)[0].rstrip("_")
        stem = f"{base}_full"

    out_json = args.input1.parent / f"{stem}_ns-{nside}_ps-{patch}_th-{thr}.json"
    out_png = args.input1.parent / f"{stem}_ns-{nside}_ps-{patch}_th-{thr}.png"
    out_summary = args.input1.parent / f"{stem}_summary.csv"
    out_manifest = args.input1.parent / f"{stem}_manifest.json"
    out_diff = args.input1.parent / f"{stem}_diff.png"
    out_only1 = args.input1.parent / f"{stem}_only-rh1.json"
    out_only2 = args.input1.parent / f"{stem}_only-rh2.json"

    # Load catalogs
    cat1 = read_catalog(args.input1)
    cat2 = read_catalog(args.input2)

    pm1 = catalog_to_pixel_map(cat1, nside)
    pm2 = catalog_to_pixel_map(cat2, nside)

    inter, only1, only2 = intersect_catalogs(pm1, pm2, args.score_delta_max)

    # Write outputs
    if args.ndjson:
        save_ndjson(out_json, inter)
    else:
        out_json.write_text(json.dumps(inter, ensure_ascii=False, indent=2), encoding="utf-8")

    # Maps
    m_inter = make_intersection_map(inter, nside)
    plot_mollweide(
        data=m_inter,
        title=f"Hexagonal Coherence (Intersection RH1 ∩ RH2)\nNSIDE={nside}  PATCH={patch}  TH={thr}",
        out_png=out_png,
        vmin=0.0,
        vmax=1.0,
        unit="Coherence Score",
        cmap="viridis",
        cbar=True,
    )

    if args.emit_diff:
        m_diff = make_difference_map(pm1, pm2, nside)
        vmax = float(np.nanmax(np.abs(m_diff)))
        plot_mollweide(
            data=m_diff,
            title=f"Coherence Difference (RH1 − RH2)\nNSIDE={nside}  PATCH={patch}  TH={thr}",
            out_png=out_diff,
            vmin=-vmax,
            vmax=vmax,
            unit="ΔScore",
            cmap="coolwarm",
            cbar=True,
        )

    if args.emit_only_sets:
        out_only1.write_text(json.dumps(only1, ensure_ascii=False, indent=2), encoding="utf-8")
        out_only2.write_text(json.dumps(only2, ensure_ascii=False, indent=2), encoding="utf-8")

    # Summary & manifest
    counts = {
        "count_rh1": len(pm1),
        "count_rh2": len(pm2),
        "count_intersection": len(inter),
        "count_only_rh1": len(only1),
        "count_only_rh2": len(only2),
    }
    score_stats = {
        "score_mean.mean": float(np.nanmean([r.get("score_mean", np.nan) for r in inter])) if inter else np.nan,
        "score_mean.min": float(np.nanmin([r.get("score_mean", np.nan) for r in inter])) if inter else np.nan,
        "score_mean.max": float(np.nanmax([r.get("score_mean", np.nan) for r in inter])) if inter else np.nan,
        "delta_score.mean": float(np.nanmean([r.get("delta_score", np.nan) for r in inter])) if inter else np.nan,
        "delta_score.max": float(np.nanmax([r.get("delta_score", np.nan) for r in inter])) if inter else np.nan,
    }
    write_summary_csv(out_summary, counts, score_stats)

    manifest = {
        "_schema": "chsd-intersection-manifest-v1",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "inputs": {"ringhalf_1": str(args.input1), "ringhalf_2": str(args.input2)},
        "params": {"nside": nside, "patch_size": patch, "threshold": thr, "score_delta_max": args.score_delta_max},
        "outputs": {"catalog": str(out_json), "png": str(out_png), "summary_csv": str(out_summary)},
        "counts": counts,
    }
    if args.emit_diff:
        manifest["outputs"]["diff_png"] = str(out_diff)
    if args.emit_only_sets:
        manifest["outputs"]["only_rh1_json"] = str(out_only1)
        manifest["outputs"]["only_rh2_json"] = str(out_only2)

    out_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote: {out_json}")
    print(f"Wrote: {out_png}")
    print(f"Wrote: {out_summary}")
    print(f"Wrote: {out_manifest}")
    if args.emit_diff:
        print(f"Wrote: {out_diff}")
    if args.emit_only_sets:
        print(f"Wrote: {out_only1}") ; print(f"Wrote: {out_only2}")

if __name__ == "__main__":
    main()
