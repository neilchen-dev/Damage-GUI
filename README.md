# Data-Driven Damage Field Prediction

A Python desktop tool for reconstructing 2D damage fields from simulation data under varying operating conditions. It combines a field-level RBF surrogate model, robust evaluation metrics, and a Tkinter GUI for prediction, visualization, and aim-point optimization.

## Problem

The input is a flight/impact condition `(h, v, deg)` plus a damage level (`F`, `M`, or `P`). The output is a continuous `473 x 473` damage field rather than a single scalar prediction.

Direct pixel-wise interpolation can blur or duplicate patterns when a damage field moves across the plane. This project separates pattern shape from spatial translation before interpolation.

## Method

```text
Simulation DamageMatrix files
        -> bilateral denoising
        -> centroid extraction and alignment
        -> RBF interpolation in (h, v, deg) space
        -> centroid restoration
        -> predicted 2D damage field
        -> metrics, visualization, and aim-point optimization
```

- Bilateral filtering reduces Monte Carlo noise while preserving sharp damage peaks.
- Centroid alignment decouples spatial translation from shape interpolation and reduces ghosting.
- RBF interpolation reconstructs the full field over the low-dimensional condition space.
- Evaluation includes RMSE, MAE, R2, damage-area ratio, relative error, and hybrid error metrics.
- Aim-point optimization convolves the damage field with a CEP or REP/DEP probability kernel.

## Repository layout

```text
.
├── src/damage_gui/
│   ├── app.py                 # GUI, data loading, RBF model, and evaluation
│   └── aim_optimization.py    # Standalone aim-point optimization mathematics
├── scripts/build.bat          # PyInstaller build entry point
├── tests/                     # Reproducible numerical and metric tests
├── requirements.txt
└── README.md
```

The original simulation matrices, trained model files, virtual environments, and packaged executables are intentionally excluded from Git. Supply a local `data/` directory containing files named `DamageMatrix_<F|M|P>_h_<h>_v_<v>_deg_<deg>` before training.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m damage_gui.app
```

In the GUI, select the local data directory, choose a damage level, train or load a model, then enter a condition to generate a field prediction.

## Tests

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

The tests cover dispersion conversions, probability-kernel normalization, zero-dispersion behavior, and core evaluation metrics.

## Build

From the repository root, run:

```powershell
.\scripts\build.bat
```

The build script creates a PyInstaller application under `dist/DamageEfficiencyApp`. If local data or pre-trained `.joblib` files are present, it copies them into the package for deployment.

## Limitations and next steps

The current random hold-out split is useful for interpolation checks but can be optimistic for a regular condition grid. Stronger validation should hold out complete `h`, `deg`, or spatial-condition regions to assess interpolation across unseen conditions.

Training currently runs in the GUI process; a future worker-thread implementation would keep the interface responsive for larger datasets.
