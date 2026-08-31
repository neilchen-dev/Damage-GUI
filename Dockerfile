# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg \
    DAMAGE_GUI_HOME=/var/lib/damagelab \
    DAMAGE_GUI_HOST=0.0.0.0 \
    DAMAGE_GUI_PORT=8000

RUN groupadd --system --gid 10001 damagelab \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent \
        --shell /usr/sbin/nologin damagelab

WORKDIR /opt/damagelab

# Install the tested direct dependency set before copying the application so
# source-only changes can reuse Docker's dependency layer.
COPY requirements-web.lock ./
RUN python -m pip install --no-cache-dir --only-binary=:all: -r requirements-web.lock

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps .

COPY deploy/entrypoint.sh /usr/local/bin/damagelab-entrypoint
COPY deploy/drop_privileges.py /usr/local/bin/damagelab-drop-privileges
RUN chmod 0755 /usr/local/bin/damagelab-entrypoint \
        /usr/local/bin/damagelab-drop-privileges \
    && mkdir -p /var/lib/damagelab/db /var/lib/damagelab/models \
        /var/lib/damagelab/results \
    && chown -R 10001:10001 /var/lib/damagelab

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()"

# The entrypoint performs volume preparation as root, then execs the ASGI
# process as UID 10001. Uvicorn is explicitly constrained to one process.
ENTRYPOINT ["/usr/local/bin/damagelab-entrypoint"]
