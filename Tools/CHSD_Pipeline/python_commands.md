# environment

export MPLBACKEND=Agg 

tr -d '\r' < run_fits.sh > run_fits_unix.sh && mv run_fits_unix.sh run_fits.sh
chmod +x run_fits.sh

## Command example

python3 chsd_pipeline.py \
  -i ./data/LFI_SkyMap_070-BPassCorrected_1024_R4.00_full-ringhalf-1.fits \
  -o ./chsd_results/LFI_SkyMap_070-BPassCorrected_1024_R4.00_full-ringhalf-1.json -v \
  ./chsd_results/LFI_SkyMap_070-BPassCorrected_1024_R4.00_full-ringhalf-1.png \
  --nside 64 --patch-size 32 --threshold 0.9
  
## NSIDE=64
# Baseline
./run_fits.sh # Default: 64 32 0.90
# Medium-fine
./run_fits.sh 64 24 0.90
# Fine
./run_fits.sh 64 16 0.93

## NSIDE=128
# Baseline
./run_fits.sh 128 32 0.90
# Medium-fine
./run_fits.sh 128 24 0.92
# Fine
./run_fits.sh 128 16 0.94