#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CHSD Ringhalf Intersection Utility (robust + output-dir)
"""
import argparse, json, math, re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import healpy as hp
except Exception as e:
    hp = None
    _hp_import_error = e

# --- Filename parsing ---
FNAME_PATTERNS = [
    re.compile(r"ns-(\d+)_ps-(\d+)_th-([0-9.]+)", re.IGNORECASE),
    re.compile(r"ns(?:ide)?[=_-](\d+).*?ps(?:atch)?[=_-](\d+).*?th(?:r(?:eshold)?)?[=_-]([0-9.]+)", re.IGNORECASE),
]

def parse_params_from_name(path: Path, debug: bool=False) -> Tuple[int, int, float]:
    name = path.name
    for pat in FNAME_PATTERNS:
        m = pat.search(name)
        if m:
            n, p, t = int(m.group(1)), int(m.group(2)), float(m.group(3))
            if debug:
                print(f"[parse] {name} -> NSIDE={n} PATCH={p} TH={t} (matched {pat.pattern})")
            return n, p, t
    if debug:
        print(f"[parse] FAILED to parse ns/ps/th from filename: {name}")
    raise ValueError(f"Could not parse ns/ps/th from filename: {name}")

def read_catalog(path: Path) -> List[Dict[str, Any]]:
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
        raise RuntimeError("healpy is required for this script. Import error: %r" % (_hp_import_error,))

def gal_to_theta_phi(lon_deg: float, lat_deg: float):
    phi = math.radians(lon_deg % 360.0)
    theta = math.radians(90.0 - lat_deg)
    return theta, phi

def catalog_to_pixel_map(catalog: List[Dict[str, Any]], nside: int) -> Dict[int, Dict[str, Any]]:
    ensure_healpy()
    pix_map: Dict[int, Dict[str, Any]] = {}
    for rec in catalog:
        pix = rec.get("pixel_index")
        if pix is None:
            coords = rec.get("coordinates", {})
            if str(coords.get("system", "")).lower() != "galactic":
                raise ValueError("Only galactic coordinates are supported.")
            lon = float(coords["lon_deg"]); lat = float(coords["lat_deg"])
            theta, phi = gal_to_theta_phi(lon, lat)
            pix = int(hp.ang2pix(nside, theta, phi, nest=False))
            rec["pixel_index"] = pix
        score = float(rec.get("coherence_score", 0.0))
        prev = pix_map.get(pix)
        if prev is None or float(prev.get("coherence_score", 0.0)) < score:
            pix_map[pix] = rec
    return pix_map

def intersect_catalogs(pm1: Dict[int, Dict[str, Any]], pm2: Dict[int, Dict[str, Any]], score_delta_max: float=None):
    keys1 = set(pm1.keys()); keys2 = set(pm2.keys())
    inter = keys1 & keys2
    only1 = [pm1[k] for k in (keys1 - keys2)]
    only2 = [pm2[k] for k in (keys2 - keys1)]
    out = []
    for k in sorted(inter):
        r1 = pm1[k]; r2 = pm2[k]
        s1 = float(r1.get("coherence_score", 0.0))
        s2 = float(r2.get("coherence_score", 0.0))
        mean = 0.5*(s1+s2); delta = abs(s1-s2)
        rec = dict(r1)
        rec.update({"score_rh1": s1, "score_rh2": s2, "score_mean": mean,
                    "score_min": min(s1, s2), "delta_score": delta})
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

def make_difference_map(pm1, pm2, nside: int) -> np.ndarray:
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

def plot_mollweide(data: np.ndarray, title: str, out_png: Path, vmin=None, vmax=None, unit="Coherence Score", cmap="viridis", cbar=True):
    ensure_healpy()
    hp.mollview(data, title=title, unit=unit, min=vmin, max=vmax, cmap=cmap, cbar=cbar, notext=False)
    hp.graticule(ls=":", alpha=0.8)
    plt.savefig(out_png, dpi=200, bbox_inches="tight"); plt.close()

def write_summary_csv(path: Path, counts: Dict[str, Any], score_stats: Dict[str, Any]):
    import csv
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["metric", "value"])
        for k, v in counts.items(): w.writerow([k, v])
        for k, v in score_stats.items(): w.writerow([k, v])

def main(argv=None):
    ap = argparse.ArgumentParser(description="Intersect two CHSD motif catalogs (RH1 & RH2)")
    ap.add_argument("--input1", required=True, type=Path)
    ap.add_argument("--input2", required=True, type=Path)
    ap.add_argument("--output-stem", type=str, default=None, help="Filename prefix (without ns/ps/th).")
    ap.add_argument("--output-dir", type=Path, default=None, help="Directory for all outputs (created if missing).")
    ap.add_argument("--nside", type=int, default=None)
    ap.add_argument("--patch-size", type=int, default=None)
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--score-delta-max", type=float, default=None)
    ap.add_argument("--emit-diff", action="store_true")
    ap.add_argument("--emit-only-sets", action="store_true")
    ap.add_argument("--ndjson", action="store_true")
    ap.add_argument("--debug", action="store_true", help="Print filename parse info.")
    args = ap.parse_args(argv)

    # parse from filenames
    try:
        n1, p1, t1 = parse_params_from_name(args.input1, debug=args.debug)
        n2, p2, t2 = parse_params_from_name(args.input2, debug=args.debug)
    except ValueError:
        n1 = p1 = t1 = None; n2 = p2 = t2 = None

    nside = args.nside or n1 or n2
    patch = args.patch_size or p1 or p2
    thr = args.threshold or t1 or t2

    if nside is None or patch is None or thr is None:
        raise SystemExit("NSIDE, PATCH, and THRESHOLD must be provided via filename pattern or CLI overrides. "
                         "Try adding: --nside <N> --patch-size <P> --threshold <T> or run with --debug.")

    # output stem
    if args.output_stem:
        stem = args.output_stem
    else:
        def strip_ringhalf(name: str) -> str:
            return name.replace("_ringhalf-1", "").replace("-ringhalf-1", "") \
                       .replace("_ringhalf-2", "").replace("-ringhalf-2", "")
        base = strip_ringhalf(args.input1.stem)
        base = FNAME_PATTERNS[0].split(base)[0].rstrip("_-")
        stem = f"{base}_full"

    # base dir
    base_dir = args.output_dir if args.output_dir is not None else args.input1.parent
    base_dir.mkdir(parents=True, exist_ok=True)

    out_json = base_dir / f"{stem}_ns-{nside}_ps-{patch}_th-{thr}.json"
    out_png  = base_dir / f"{stem}_ns-{nside}_ps-{patch}_th-{thr}.png"
    out_summary  = base_dir / f"{stem}_summary.csv"
    out_manifest = base_dir / f"{stem}_manifest.json"
    out_diff = base_dir / f"{stem}_diff.png"
    out_only1 = base_dir / f"{stem}_only-rh1.json"
    out_only2 = base_dir / f"{stem}_only-rh2.json"

    # load
    cat1 = read_catalog(args.input1); cat2 = read_catalog(args.input2)
    pm1 = catalog_to_pixel_map(cat1, nside); pm2 = catalog_to_pixel_map(cat2, nside)
    inter, only1, only2 = intersect_catalogs(pm1, pm2, args.score_delta_max)

    # write catalog
    if args.ndjson: save_ndjson(out_json, inter)
    else: out_json.write_text(json.dumps(inter, ensure_ascii=False, indent=2), encoding="utf-8")

    # plots
    m_inter = make_intersection_map(inter, nside)
    plot_mollweide(m_inter, f"Hexagonal Coherence (RH1 ∩ RH2)\nNSIDE={nside}  PATCH={patch}  TH={thr}",
                   out_png, vmin=0.0, vmax=1.0, unit="Coherence Score", cmap="viridis", cbar=True)
    if args.emit_diff:
        m_diff = make_difference_map(pm1, pm2, nside)
        vmax = float(np.nanmax(np.abs(m_diff))) if np.isfinite(np.nanmax(np.abs(m_diff))) else 1.0
        plot_mollweide(m_diff, f"Coherence Difference (RH1 − RH2)\nNSIDE={nside}  PATCH={patch}  TH={thr}",
                       out_diff, vmin=-vmax, vmax=vmax, unit="ΔScore", cmap="coolwarm", cbar=True)

    if args.emit_only_sets:
        out_only1.write_text(json.dumps(only1, ensure_ascii=False, indent=2), encoding="utf-8")
        out_only2.write_text(json.dumps(only2, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = {"count_rh1": len(pm1), "count_rh2": len(pm2),
              "count_intersection": len(inter), "count_only_rh1": len(only1), "count_only_rh2": len(only2)}
    def smean(vals): return float(np.nanmean(vals)) if vals else float("nan")
    def smin(vals):  return float(np.nanmin(vals)) if vals else float("nan")
    def smax(vals):  return float(np.nanmax(vals)) if vals else float("nan")
    score_stats = {
        "score_mean.mean": smean([r.get("score_mean", np.nan) for r in inter]),
        "score_mean.min":  smin([r.get("score_mean", np.nan) for r in inter]),
        "score_mean.max":  smax([r.get("score_mean", np.nan) for r in inter]),
        "delta_score.mean": smean([r.get("delta_score", np.nan) for r in inter]),
        "delta_score.max":  smax([r.get("delta_score", np.nan) for r in inter]),
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
    if args.emit_diff: manifest["outputs"]["diff_png"] = str(out_diff)
    if args.emit_only_sets:
        manifest["outputs"]["only_rh1_json"] = str(out_only1)
        manifest["outputs"]["only_rh2_json"] = str(out_only2)
    out_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote: {out_json}"); print(f"Wrote: {out_png}")
    print(f"Wrote: {out_summary}"); print(f"Wrote: {out_manifest}")
    if args.emit_diff: print(f"Wrote: {out_diff}")
    if args.emit_only_sets: print(f"Wrote: {out_only1}\nWrote: {out_only2}")

if __name__ == "__main__":
    main()
