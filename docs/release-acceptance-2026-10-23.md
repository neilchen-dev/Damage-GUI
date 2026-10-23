# Release acceptance — 2026-10-23

Scope: `main` release candidate 2.2.0, checked on Apple Silicon macOS. This report separates automated/offscreen evidence from native GUI checks that require target devices.

## Results

| Area | Result | Evidence / limits |
|---|---|---|
| Python test suite | PASS | `pytest tests/ -q`: 327 passed; CI unittest discovery: 272 passed. Both rerun after the Web startup fix. |
| Static checks | PASS | `ruff check .` and `git diff --check`. |
| macOS packaging | PASS | Fresh `scripts/build_qt_release.sh` build produced `release/DamageLab-2.2.0-macos-arm64/DamageLab.app`; `codesign --verify` passed. |
| Packaged app cold launch | PASS (offscreen) | Copied the rebuilt app to a temporary folder, launched from a separate working directory with an empty data directory, and confirmed the startup log was written under `DAMAGE_GUI_HOME`. This does not replace a native desktop launch. |
| Qt workflow | PASS (offscreen) | Cold empty state; 1100×700, 1280×720, 1440×900, 1600×1000 and maximized layouts; Unicode/space paths; prediction, validation, batch, history, model registry and PNG export; corrupted model metadata/CSV, read-only export and busy-close behavior. |
| HiDPI layout | PASS (offscreen) | `QT_SCALE_FACTOR=2`, device pixel ratio 2.0, 1280×720 logical window and 2560×1440 capture. |
| Plot lifecycle | PASS | 20 predictions and 5 validations retained the same 5 window-owned figures; RSS did not grow during the run. |
| Web service | PASS | Started through the production entrypoint with isolated paths; `/api/health` returned 200 and SQLite was created. The pre-initialization history scan was moved into service startup; the database warning no longer appears. |
| Windows native GUI | NOT TESTED | No Windows desktop was available for manual launch and workflow checks. |
| Linux native GUI | NOT TESTED | No Linux desktop was available for manual launch and workflow checks. |
| Native macOS GUI interaction | NOT TESTED | Automated checks used Qt offscreen mode; window manager, file dialogs and Gatekeeper interaction need a visible desktop check. |

## Evidence files

The generated JSON reports and screenshots are local, ignored acceptance artifacts under `outputs/release_acceptance_final_2026-10-23/`.

## Release decision

The code, tests, Web service, macOS package build and offscreen desktop workflows pass. Treat this as **automated acceptance complete, native platform acceptance incomplete**. Before a cross-platform release, run the checklist's visible GUI workflows on macOS, Windows and Linux; record unavailable platforms as NOT TESTED.
