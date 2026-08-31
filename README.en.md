# DamageLab — Fast Damage-Field Prediction Workbench

![DamageLab](src/damage_gui/webapp/static/assets/damagelab-icon.png)

[中文 README](README.md) · **English**

DamageLab is an engineering workbench for fast reconstruction and assessment of two-dimensional damage fields from simulated flight or impact conditions. Given `(h, v, deg)` and a damage level (`F`, `M`, or `P`), it predicts a continuous `473 × 473` field instead of a single scalar value.

The project provides a Windows desktop GUI, a command-line interface, and an optional FastAPI service. The desktop and Web workbenches support live Chinese / English switching through their language selectors; language changes affect presentation only and never alter model files, CSV/SQLite formats, or scientific results.

**Research positioning:** Centroid-Aligned POD-RBF Surrogate Model for Fast Reconstruction and Assessment of High-Dimensional Damage Fields.

## Why centroid-aligned POD-RBF?

Damage patterns move spatially as the operating condition changes. Direct pixel-wise interpolation can therefore blur or duplicate the pattern. DamageLab separates shape from translation:

```text
DamageMatrix simulation data
  → bilateral denoising
  → centroid extraction and alignment
  → POD / PCA dimensionality reduction
  → RBF interpolation of shape coefficients and centroids
  → centroid restoration and 2-D field reconstruction
  → metrics, OOD confidence, visualization, and aim-point optimization
```

The implementation also supports structured validation (random, leave-h, leave-v, leave-deg, and corner holdout), raw/smoothed evaluation, spatial metrics (centroid, peak, IoU, Dice), and CEP / REP-DEP aim-point optimization.

## Product capabilities

- Windows-native Tkinter / ttk desktop workbench with DPI-aware rendering and runtime language switching.
- Background task state machine for training, prediction, and batch operations, including cooperative cancellation.
- Model registry with joblib bundles, sidecar metadata, data fingerprints, software/model/schema versions, and Git commit traceability.
- OOD confidence based on nearest-neighbor distance, global SVD support, and local training-neighborhood support.
- CSV batch prediction with row-level failure isolation, progress, cancellation, and SQLite traceability.
- FastAPI endpoints and a dependency-light browser workbench for health, models, prediction, batch jobs, history, results, and aim optimization.
- PyInstaller onedir Windows release packaging and Docker Compose deployment for the Web service.

## Technology stack

| Layer | Technology | Role |
|---|---|---|
| Runtime | Python 3.10–3.12 | Scientific computing, desktop, CLI, and Web service |
| Desktop UI | Tkinter / ttk, Windows ctypes DPI APIs | Native workbench, fonts, and multi-monitor scaling |
| Scientific computing | NumPy, SciPy, Pandas, scikit-learn, joblib | Arrays, filtering, interpolation, reduction, data, and persistence |
| Surrogate model | POD/PCA, centroid alignment, RBF | Reduced-order damage-field reconstruction |
| Evaluation | RMSE, MAE, R², relative error, IoU, Dice, OOD geometry | Numerical, spatial, and extrapolation-risk assessment |
| Visualization | Matplotlib, TkAgg, high-DPI PNG rendering | Damage, prediction, error, and aim-point views |
| Service | FastAPI, Pydantic, Uvicorn, httpx2 | Health, model, prediction, batch, history, and result APIs |
| Web UI | Native HTML, CSS, and JavaScript | No-build browser workbench |
| Traceability | SQLite, CSV, JSON sidecars, rotating logs | Model, job, result, input, and version history |
| Delivery | PyInstaller onedir, Docker, Docker Compose, Nginx | Windows release and reverse-proxied server deployment |
| Quality | unittest, ruff, GitHub Actions, numerical golden values | Linting, cross-platform tests, builds, and regression control |

## Screenshots and branding

These are screenshots captured from the current running desktop application, not mockups:

![DamageLab desktop workbench — Chinese](examples/screenshots/gui.png)

![DamageLab desktop workbench — English](examples/screenshots/gui_en.png)

The `DL` product mark is shared by the desktop and Web interfaces. Source assets are kept in `src/damage_gui/gui/assets/` and `src/damage_gui/webapp/static/assets/`; the PyInstaller scripts include the desktop icon in the release package.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m damage_gui.app
```

In the desktop GUI, select a local data directory, damage level, model type (RBF / POD-RBF), and validation mode. Train or load a model, then enter the operating condition for prediction. Training runs in the background and results include elapsed time, metrics, and model confidence.

## CLI

```powershell
# Inspect model metadata
python -m damage_gui.cli info --model damage_model_F.joblib

# Predict one condition and optionally export the field
python -m damage_gui.cli predict --model damage_model_F.joblib `
    --h 1 --v 300 --deg 30 --export pred.csv

# Predict a CSV batch with optional truth comparison
python -m damage_gui.cli batch --model damage_model_F.joblib `
    --input batch.csv --output batch_result.csv --data-dir data
```

Batch failures are isolated per row. Exit codes are `0` for all successful rows, `1` for failed or cancelled work, and `2` for invalid input.

## Web service and Docker

Install the optional service dependencies and run the API:

```powershell
pip install -e ".[web]"
damage-gui-web
```

Alternatively:

```powershell
uvicorn damage_gui.webapp.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` for the browser workbench and `/docs` for the OpenAPI documentation. For a containerized deployment:

```powershell
docker compose up --build
```

The server loads models lazily, keeps large matrices out of JSON responses, writes generated artifacts to the configured result directory, and exposes health checks for deployment orchestration. See [`docs/web-api.md`](docs/web-api.md) and [`docs/deployment.md`](docs/deployment.md) for the operational details.

## Reproducible validation

The repository includes synthetic-data unit tests, end-to-end service tests, storage and task tests, headless import guards, and numerical regression tests with fixed golden values. Private simulation matrices are intentionally not committed. With local data available, structured validation and study reports can be regenerated with:

```powershell
$env:PYTHONPATH = "src"
python scripts/validation_study.py --data-dir path\to\data --level F
python scripts/generate_results.py --data-dir path\to\data --level F
```

Run the test suite and lint checks:

```powershell
python -m unittest discover -s tests -v
ruff check .
```

## Windows build

The supported engineering distribution is a PyInstaller onedir package:

```powershell
.\scripts\build_release.bat
```

The build scripts package the `DL` icon and UI assets and do not include private training matrices or pre-trained models by default.

## Project structure

```text
src/damage_gui/
├── app.py                 # thin desktop launcher
├── cli.py                 # info / predict / batch CLI
├── services/              # shared training, prediction, batch, export, and AIM orchestration
├── model/                 # RBF, POD, validation, OOD, bundles, metadata, registry
├── evaluation/            # numerical and spatial metrics
├── optimization/          # pure aim-point optimization
├── storage/               # SQLite schema and repositories
├── gui/                   # Tkinter workbench, panels, i18n, styles, and assets
└── webapp/                # FastAPI routes, schemas, jobs, rendering, and static UI
```

## License

MIT License. See [`LICENSE`](LICENSE).
