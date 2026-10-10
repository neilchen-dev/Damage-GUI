# DamageLab Web Workbench: Linux deployment

This deployment is intentionally a single-process web service:

```text
Internet → Nginx :443 → app :8000 → shared services → SQLite / models / results
```

The FastAPI process is not published on the host. Nginx is the only service
with public ports. The app uses one Uvicorn worker because batch jobs,
cancellation, model caching, and result caching are process-local. Adding
multiple workers would create independent executors and inconsistent in-memory
state, so it is explicitly disabled in both Compose and the image entrypoint.

## Persistent locations

The Compose file creates three named volumes:

| Volume | Container path | Contents |
| --- | --- | --- |
| `database` | `/var/lib/damagelab/db` | SQLite database and WAL/SHM files |
| `models` | `/var/lib/damagelab/models` | `.joblib` models and metadata sidecars |
| `results` | `/var/lib/damagelab/results` | prediction and batch artifacts |

The model volume is mounted read-only into the app. Logs go to stdout/stderr;
Docker or the host logging driver owns log retention. Result artifacts are
managed by the application and retained for seven days by default.

## Configuration

Copy the example and edit the deployment-owned values:

```sh
cp .env.example .env
```

Supported settings include:

- `DAMAGE_GUI_HOME` — runtime root; default `/var/lib/damagelab` in the image.
- `DAMAGE_GUI_DB` — SQLite path.
- `DAMAGE_GUI_MODEL_DIR` — server-owned model directory.
- `DAMAGE_GUI_RESULT_DIR` — prediction/batch artifact directory.
- `DAMAGE_GUI_RESULT_RETENTION_DAYS` — integer from 1 through 3650.
- `DAMAGE_GUI_DEFAULT_MODEL` — optional model ID; startup fails if it is absent.
- `DAMAGE_GUI_HOST` and `DAMAGE_GUI_PORT` — internal ASGI bind settings.
- `DAMAGE_GUI_DOMAIN` — Nginx TLS/server-name template value.

`DAMAGE_GUI_WEB_RESULT_DIR`, `DAMAGE_GUI_WEB_HOST`, and
`DAMAGE_GUI_WEB_PORT` remain accepted as compatibility aliases. Configure the
required `DAMAGE_GUI_API_TOKEN` in the private deployment environment; never
commit `.env` or model signing keys to source control.

## First deployment

Install Docker Engine and the Compose plugin using the instructions for the
Linux distribution and cloud provider. Then:

```sh
git clone <repository-url> damagelab
cd damagelab
cp .env.example .env
mkdir -p deploy/certbot/www deploy/letsencrypt
```

Provide model artifacts in the named model volume. For a simpler bind-mounted
model directory, create a local Compose override (kept outside source control):

```yaml
services:
  app:
    volumes:
      - ./runtime/models:/var/lib/damagelab/models:ro
```

Then place the `.joblib` model and its `.meta.json` sidecar under
`runtime/models`. The same pattern can be used for database/results when host
filesystem backups are preferred. Never mount a host directory containing
untrusted files over the application or source tree.

Build and start the app first:

```sh
docker compose build --pull app
docker compose up -d app
docker compose logs --tail=100 app
```

The entrypoint creates/validates the runtime directories, initializes SQLite,
checks database/result write access, checks model directory readability, and
validates an explicitly configured default model without loading model bytes.
The process then runs as UID/GID `10001:10001` (`damagelab`).

## TLS with Nginx and Let's Encrypt

Before the first Nginx start:

1. Create a DNS `A`/`AAAA` record for `DAMAGE_GUI_DOMAIN` pointing to the
   server. Ports 80 and 443 must reach this host.
2. Obtain the first certificate while Nginx is stopped. The paths below keep
   certificates in the deployment directory, which is mounted read-only into
   Nginx:

```sh
sudo certbot certonly --standalone \
  --config-dir "$PWD/deploy/letsencrypt" \
  --work-dir "$PWD/deploy/letsencrypt-work" \
  --logs-dir "$PWD/deploy/letsencrypt-logs" \
  -d damage.example.com
```

Replace the domain with the value in `.env`; do not commit the resulting key
or certificate files. Start the reverse proxy:

```sh
docker compose up -d nginx
docker compose ps
```

The Nginx template serves ACME challenge files, redirects HTTP to HTTPS,
proxies `/`, `/api/`, and `/static/` same-origin to the app, and publishes
only ports 80 and 443. It uses `client_max_body_size 64k`, matching the
application request limit, plus bounded proxy timeouts and restrained security
headers. HSTS is sent only by the HTTPS server block.

For renewal, use the webroot already mounted by Compose and reload Nginx after
successful renewal:

```sh
sudo certbot renew --webroot -w "$PWD/deploy/certbot/www" \
  --config-dir "$PWD/deploy/letsencrypt" \
  --work-dir "$PWD/deploy/letsencrypt-work" \
  --logs-dir "$PWD/deploy/letsencrypt-logs"
docker compose exec nginx nginx -s reload
```

Use a systemd timer or the provider's scheduled task runner for renewal; do
not put private keys in the image or repository.

## Firewall

If UFW is used, allow only SSH when required and the public web ports:

```sh
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp       # omit if SSH is managed elsewhere
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Do not allow port 8000. It is only on the Compose internal network.

## Health and smoke checks

Run these through the public HTTPS origin, not the internal app port:

```sh
curl --fail https://damage.example.com/api/health
curl --fail https://damage.example.com/
curl --fail https://damage.example.com/static/app.js
curl --fail -H "Authorization: Bearer $DAMAGE_GUI_API_TOKEN" https://damage.example.com/api/models
```

With a valid model, exercise prediction and its artifacts:

```sh
prediction=$(curl --fail --silent -X POST \
  'https://damage.example.com/api/predict' \
  -H "Authorization: Bearer $DAMAGE_GUI_API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"h":2,"v":200,"deg":10}')
run_id=$(printf '%s' "$prediction" | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["run_id"])')
curl --fail -H "Authorization: Bearer $DAMAGE_GUI_API_TOKEN" "https://damage.example.com/api/results/$run_id/png" -o result.png
curl --fail -H "Authorization: Bearer $DAMAGE_GUI_API_TOKEN" "https://damage.example.com/api/results/$run_id/csv" -o result.csv
```

Batch submission returns immediately; poll its job ID and then download the
CSV:

```sh
job_id=$(curl --fail --silent -X POST \
  'https://damage.example.com/api/batch' \
  -H "Authorization: Bearer $DAMAGE_GUI_API_TOKEN" \
  -H 'content-type: text/csv' \
  -H 'X-Filename: smoke.csv' \
  --data-binary $'job_id,h,v,deg,level\nsmoke,2,200,10,F\n' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')
curl --fail -H "Authorization: Bearer $DAMAGE_GUI_API_TOKEN" "https://damage.example.com/api/jobs/$job_id"
```

## Shutdown, restart, and persistence

`docker compose stop` gives the app a 30-second grace period. Shutdown stops
accepting new batch jobs, requests cooperative cancellation for active jobs,
and cancels queued futures. If a process is terminated before an in-flight job
can close its SQLite row, the next app startup marks the server-owned PENDING or
RUNNING job as failed; it is never falsely resumed or reported as successful.

Recreate containers without deleting volumes:

```sh
docker compose down
docker compose up -d
curl --fail https://damage.example.com/api/health
```

Never use `docker compose down -v` in a normal upgrade or restart. It deletes
the database, models, and results volumes.

## SQLite backup

Do not copy `damage_gui.db` directly while the service is live because WAL
pages may not be in the main file. Use SQLite's backup API through the running
container, then copy the resulting backup out:

```sh
mkdir -p backups
docker compose exec -T app python -c '
import sqlite3
src = sqlite3.connect("/var/lib/damagelab/db/damage_gui.db")
dst = sqlite3.connect("/var/lib/damagelab/db/damage_gui.db.backup")
with dst:
    src.backup(dst)
dst.close()
src.close()
' 
docker cp "$(docker compose ps -q app):/var/lib/damagelab/db/damage_gui.db.backup" \
  "backups/damage_gui-$(date +%Y%m%d-%H%M%S).db"
```

Back up the model volume and selected result artifacts separately. Test a
backup by opening it with `sqlite3` and running `PRAGMA integrity_check;`.

## Upgrade and rollback

For an upgrade, keep volumes mounted and use a versioned image tag:

```sh
git pull --ff-only
docker compose build --pull app
docker compose up -d --no-deps app
docker compose ps
curl --fail https://damage.example.com/api/health
```

If the new image is not compatible with existing traceability data, stop and
restore the previous image tag while retaining all volumes:

```sh
docker compose down
sed -i 's/^DAMAGE_GUI_IMAGE=.*/DAMAGE_GUI_IMAGE=damagelab-web:previous/' .env
docker compose up -d
```

Before upgrades that alter persistence behavior, take the SQLite backup above.
Do not delete volumes or apply an irreversible schema change as part of an
automatic rollback.

## Operational boundaries

The API requires a shared operator access token. This phase does not add
per-user accounts, online training, Redis, Celery, PostgreSQL, Kubernetes,
or distributed workers. The current workload
is served by one app process behind Nginx; scale-out requires a separately
designed shared job/result service before adding workers or replicas.

## Security configuration and model migration

Set `DAMAGE_GUI_API_TOKEN` to a random secret of at least 32 characters before
starting the Web service. Compose and the production entrypoint reject a missing
token. An embedded `create_app()` without a token serves static assets and health
checks, but denies all other API requests. Generate a token with:

```sh
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

API clients send `Authorization: Bearer <token>`. The Workbench asks for the token
on its first protected request and exchanges it for an eight-hour HttpOnly,
SameSite=Strict session cookie; HTTPS sessions also set Secure. Tokens are never
put in URLs or browser storage. Use HTTPS for remote access. `DELETE /api/session`
logs out the browser. Changing the operator token invalidates all sessions.
The token grants access to the shared workspace and its jobs; it does not create
separate user workspaces. Protected API responses use `Cache-Control: no-store`.

AIM probability kernels are limited to 1,000,000 elements before allocation,
and the Web adapter admits at most two concurrent compute requests. The shared
workspace compute limit defaults to 60 requests per minute and is configurable
with `DAMAGE_GUI_RATE_LIMIT`. Oversized
spread values return 422, and excess concurrent computation returns 429.

Expired prediction and batch artifacts are cleaned every 60 seconds while the
server is running. Active batch output files are excluded from cleanup.
`DAMAGE_GUI_MAX_RESULT_BYTES` defaults to 1 GiB: when existing managed result
files reach that threshold, new predict/AIM/batch requests return 507. This is an
admission threshold, not an atomic filesystem quota: admitted requests can finish
writing above it. Use a filesystem/container storage quota if a hard capacity
limit is required. Downloading existing results and viewing history still work.
SQLite history is retained separately and is not purged by artifact retention.

New models saved by DamageLab include a `<model>.joblib.sig` HMAC-SHA256 signature.
Loading verifies the signature before joblib deserialization, and deserializes
exactly the verified bytes. Unsigned, modified, or foreign-key models are rejected.
The key defaults to the private user-data directory (`DamageLab/model-signing.key`)
and is created on first save. Set `DAMAGE_GUI_MODEL_KEY_FILE` to use an explicit
private key path. Keep the 32-byte key secret and separate from model downloads;
anyone with it can authorize executable models. HMAC establishes a trusted source,
not a sandbox for malicious code signed by that source.

For an independently verified legacy model, an administrator can sign its bytes
without deserializing it:

```sh
DAMAGE_GUI_MODEL_KEY_FILE=/private/model-signing.key \
  python scripts/sign_model.py /trusted/model.joblib --approve-trusted-source
```

Do not sign an unknown downloaded model just to bypass a load error. Transfer the
model and `.sig` together; provision the trusted key through a separate private
channel. Back up the key securely to keep saved models loadable after migration.
In Compose the service expects the key at
`/var/lib/damagelab/db/model-signing.key`; provision it in the database volume,
readable by UID 10001 with mode 0600, before loading existing signed models.
Use the same key to sign the models offline. The read-only model volume must
include their `.sig` files. Never commit the key to Git or put it in the model
volume.

Batch/report CSV exports prefix potentially executable text cells with an
apostrophe, including user-provided job identifiers. Numeric fields retain their
numeric representation.
