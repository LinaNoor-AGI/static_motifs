#!/usr/bin/env bash
# Run CHSD on every FITS in ./data, one at a time.

set -u  # (no -e so we keep going on errors)
export MPLBACKEND=${MPLBACKEND:-Agg}  # no GUI needed

DATADIR="./data"
OUTDIR="./chsd_results"

# Optional CLI overrides: ./run_fits.sh [NSIDE] [PATCH] [THRESHOLD]
NSIDE="${1:-64}"
PATCH="${2:-32}"
THR="${3:-0.90}"

mkdir -p "$OUTDIR"

# Collect FITS files (case-insensitive), sorted
mapfile -t FITS_LIST < <(find "$DATADIR" -maxdepth 1 -type f \( -iname "*.fits" -o -iname "*.fit" \) | sort)

if (( ${#FITS_LIST[@]} == 0 )); then
  echo "No FITS files found in $DATADIR"
  exit 0
fi

echo "NSIDE=$NSIDE  PATCH=$PATCH  THRESHOLD=$THR"
echo "Output -> $OUTDIR"
echo

for f in "${FITS_LIST[@]}"; do
  base="$(basename "$f")"
  stem="${base%.*}"
  json_out="$OUTDIR/${stem}_ns-${NSIDE}_ps-${PATCH}_th-${THR}.json"
  png_out="$OUTDIR/${stem}_ns-${NSIDE}_ps-${PATCH}_th-${THR}.png"

  echo ">> Processing: $base"
  python3 chsd_pipeline.py \
    -i "$f" \
    -o "$json_out" \
    -v "$png_out" \
    --nside "$NSIDE" --patch-size "$PATCH" --threshold "$THR"

  status=$?
  if [ $status -ne 0 ]; then
    echo "   ! Failed (exit $status). Skipping."
  else
    echo "   ✓ Done -> $json_out"
    echo "            $png_out"
  fi
  echo
done
