#!/bin/sh
set -eu

runtime_home="${DAMAGE_GUI_HOME:-/var/lib/damagelab}"

# Named volumes are mounted root-owned on first use.  Prepare only the
# operator data directories; model artifacts remain read-only in Compose.
mkdir -p \
    "$runtime_home" \
    "$runtime_home/db" \
    "$runtime_home/models" \
    "$runtime_home/results"
chown 10001:10001 \
    "$runtime_home" \
    "$runtime_home/db" \
    "$runtime_home/results"

if [ -d "$runtime_home/data" ]; then
    chown 10001:10001 "$runtime_home/data"
fi

python /usr/local/bin/damagelab-drop-privileges \
    python -m damage_gui.webapp.startup

server_host="${DAMAGE_GUI_HOST:-${DAMAGE_GUI_WEB_HOST:-0.0.0.0}}"
server_port="${DAMAGE_GUI_PORT:-${DAMAGE_GUI_WEB_PORT:-8000}}"

exec python /usr/local/bin/damagelab-drop-privileges \
    uvicorn damage_gui.webapp.app:app \
    --host "$server_host" \
    --port "$server_port" \
    --workers 1 \
    --proxy-headers
