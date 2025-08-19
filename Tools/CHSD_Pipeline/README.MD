# CHSD Pipeline

## Overview

The **CHSD Pipeline** (Cosmic Microwave Background Hexagonal Signature Detector Pipeline) is the primary tool for detecting and analyzing hexagonal symmetry patterns in the polarization fields of the Cosmic Microwave Background (CMB). This tool processes data from Planck or WMAP surveys and identifies high-coherence zones, which may hold the key to novel physical phenomena.

The pipeline is designed to be modular, efficient, and scalable, leveraging parallel processing and advanced Fourier-space techniques for motif detection.

---

## Getting Started

### Prerequisites

1. **Python Environment**: Python 3.8 or higher is required.
2. **Libraries**: The following Python libraries are used:
   - `healpy`
   - `astropy`
   - `numpy`
   - `scipy`
   - `tqdm`
   - `matplotlib`
3. **Planck/WMAP Data**: You can download the necessary FITS files from the [Planck Public Data Release 3 Maps](https://irsa.ipac.caltech.edu/data/Planck/release_3/all-sky-maps/).

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/LinaNoor-AGI/static_motifs.git
   cd static_motifs/Tools/CHSD_Pipeline
   ```

2. Install required Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Download the FITS data and place it in the appropriate directory.

---

## Running the Pipeline

To run the pipeline, execute the `chsd_pipeline.py` script with the following arguments:

```bash
python chsd_pipeline.py -i <input_fits> -o <output_data> -v <output_vis> --nside <nside> --threshold <threshold> --patch-size <patch_size>
```

### Example Command

```bash
python chsd_pipeline.py -i mock_cmb_data.fits -o high_coherence_zones.json -v coherence_map.png --nside 32 --threshold 0.9 --patch-size 32
```

### Arguments

- `-i` or `--input-fits`: Path to the input HEALPix FITS file.
- `-o` or `--output-data`: Path for the output file (JSON or CSV).
- `-v` or `--output-vis`: Path to save the visualization of the coherence map.
- `--nside`: HEALPix NSIDE resolution for the data (must be a power of 2).
- `--patch-size`: Size of square patches for FFT analysis.
- `--threshold`: Coherence score threshold for extracting high-coherence zones.

---

## Pipeline Details

The CHSD Pipeline consists of the following stages:

### 1. **Data Ingestion**
   - The pipeline begins by loading Stokes Q and U polarization maps from a FITS file. 
   - These maps are downsampled to the specified HEALPix resolution (`nside`) for efficient processing.

   **Code Reference**: `load_fits_data(fits_path, nside)`

### 2. **Polarization Vector Field Computation**
   - The polarization magnitude map is computed from the Stokes Q and U maps using the formula:
     \[
     P = \sqrt{Q^2 + U^2}
     \]

   **Code Reference**: `compute_polarization_field(stokes_q, stokes_u)`

### 3. **Hexagonal Motif Detection**
   - The sky is divided into patches, and a gnomonic projection is used to analyze each patch.
   - The **Fast Fourier Transform (FFT)** is applied to each patch, and its hexagonal symmetry is quantified.
   - A coherence score is calculated for each patch.

   **Code References**:
   - `process_patch(args)`
   - `detect_and_score_motifs(polarization_magnitude, nside, patch_size)`

### 4. **Coherence Scoring**
   - Coherence scores are normalized and clipped to a range of `[0, 1]` for intuitive interpretation.
   - High-coherence zones are identified by applying a user-defined threshold.

   **Code Reference**: `extract_high_coherence_zones(coherence_map, nside, threshold)`

### 5. **Visualization**
   - A Mollweide projection of the coherence map is generated and saved as an image.

   **Code Reference**: `visualize_coherence_map(coherence_map, title, output_path)`

### 6. **Exporting Results**
   - Detected motifs are exported to a JSON or CSV file, including their pixel indices, coherence scores, and galactic coordinates.

   **Code Reference**: `export_results(results, output_path, format)`

---

## Mock Data Support

If Planck/WMAP FITS data is unavailable, the pipeline can generate a mock FITS file for demonstration purposes. The mock file contains a simple gradient map for Q and a noisy map for U.

To create a mock FITS file:
```bash
python chsd_pipeline.py -i mock_cmb_data.fits
```

---

## Code Modules

The CHSD Pipeline relies on two key modules in this folder:

1. **`chsd_pipeline.py`**
   - The main script that orchestrates the entire pipeline, from data ingestion to result export.

2. **`motif_kernels.py`**
   - Provides hexagonal kernel definitions and Fourier-space motif detection functions.

---

## Example Outputs

1. **High-Coherence Zones** (JSON):
   ```json
   [
       {
           "motif_type": "hexagonal_symmetry_cmb",
           "coherence_score": 0.92,
           "coordinates": {
               "system": "galactic",
               "lon_deg": 123.45,
               "lat_deg": -67.89
           },
           "pixel_index": 11234
       }
   ]
   ```

2. **Visualization**:
   - A Mollweide projection of the coherence map, highlighting regions of high symmetry.

---

## Notes

- **Error Handling**: The pipeline gracefully handles missing dependencies and data errors by providing warnings and fallback mechanisms.
- **Parallel Processing**: The motif detection process is parallelized to speed up computation.

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## Acknowledgments

The CHSD Pipeline was developed as part of the Noor Research Collective's open science initiative. Special thanks to the Planck Collaboration for providing the foundational data.

---

### Join the Journey

Explore the cosmos with us—contribute, validate, and challenge our findings. Together, we can uncover the mysteries of the universe!
