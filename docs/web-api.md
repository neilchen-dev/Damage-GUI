# Damage GUI Web API

Phase 4 adds an optional, headless FastAPI adapter. It reuses the existing
condition validator, prediction service, AIM service, SQLite traceability
repository, and Matplotlib plot/export helpers. Importing or running it does
not create a Tk root or import the desktop GUI.

Install the optional server dependencies with `pip install -e ".[web]"`, then
run either:

```text
damage-gui-web
```

or:

```text
uvicorn damage_gui.webapp.app:app --host 127.0.0.1 --port 8000
```

The server reads models only from the server-configured `models` directory
under the application root by default. `DAMAGE_GUI_MODEL_DIR`,
`DAMAGE_GUI_DEFAULT_MODEL`, `DAMAGE_GUI_DATA_DIR`, and `DAMAGE_GUI_DB` can be
set by the server operator. Requests select models by discovered model ID;
they cannot supply filesystem paths. Models are loaded lazily and cached under
a lock.

Prediction results are retained in a bounded in-process cache and in the
server-owned result directory. Large matrices are never placed in JSON; PNG
and coordinate-labelled CSV are separate result endpoints. The result
directory is `DAMAGE_GUI_WEB_RESULT_DIR` when configured, otherwise
`<data-dir>/web-results` or `<application-root>/web-results`. Prediction and
batch artifacts are retained for 7 days and are removed during server
startup cleanup. Completed artifacts survive a process restart; in-progress
jobs are marked failed on restart and are not resumed.

## Batch jobs

`POST /api/batch?model_id=<public-model-id>` accepts the CSV as the raw
request body. The browser sends the original filename in the
`X-Filename` header; the server never accepts a client filesystem path. The
current limits are 64 KiB per upload and 1,000 parsed rows. A valid request
returns a generated `job_id` immediately. Poll `GET /api/jobs/{job_id}` for
`PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, or `CANCELLED`, including compact
progress fields. `POST /api/jobs/{job_id}/cancel` requests cooperative
cancellation. `GET /api/jobs/{job_id}/result` returns a batch summary and
`GET /api/jobs/{job_id}/result/csv` downloads the server-generated output.

The web server uses one worker and a maximum of two queued/running batch jobs
per process. Batch execution delegates to the existing CSV parser and batch
service; it does not duplicate prediction mathematics. `/api/history` reads
the existing SQLite `jobs` traceability table, which now also permits
`prediction` and `aim` records through a narrowly scoped compatibility
migration for the existing `kind` constraint.
