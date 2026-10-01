# syntax=docker/dockerfile:1
#
# Two images from one file (D-063):
#
#   api          the web app, what ECS runs behind the load balancer. Only
#                requirements.txt: no developer tools, no torch.
#   embeddings   api plus CPU torch and the embedding model, baked in. It runs
#                scripts/refresh_embeddings.py as a scheduled task. D-052 kept
#                torch out of the API: no request ever loads the model (it
#                takes about 23 seconds), and torch's advisory surface stays
#                out of the strict audit the API image is held to.
#
#   docker build --target api -t nicheconnect-api .
#   docker build --target embeddings -t nicheconnect-embeddings .
#
# The base is pinned by digest, not by tag, so the same bytes build every
# time; a newer base is a reviewed change (D-047's upgrade rule).

ARG PYTHON_IMAGE=python:3.12-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

# --- build: packages into a virtual environment, then discarded --------------
FROM ${PYTHON_IMAGE} AS build
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install -r /tmp/requirements.txt

# --- api: what runs behind the load balancer ------------------------------------
FROM ${PYTHON_IMAGE} AS api
# A fixed, unprivileged user: the app never needs root, so it never has it.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /srv --no-create-home app
# Debian security fixes the pinned base does not carry yet (D-068): OpenSSL
# (9 CVEs, one High) and PCRE2 (one High), published after the base was
# built on 19 September. Exact versions, upgrade only, so the build stays
# reproducible. Remove this step when the base digest moves to an image
# that already has these versions or newer; Grype will say if it is early.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends --only-upgrade \
        openssl=3.5.7-1~deb13u3 \
        libssl3t64=3.5.7-1~deb13u3 \
        openssl-provider-legacy=3.5.7-1~deb13u3 \
        libpcre2-8-0=10.46-1~deb13u3 \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=build /opt/venv /opt/venv
# pip only installs things, and nothing is installed at run time, so the
# running image carries none: neither the system's nor the environment's.
# The system Python is named by full path: with the venv first on PATH, a
# bare `python` is the venv's, and the second uninstall would find no pip.
RUN /usr/local/bin/python -m pip uninstall --yes --quiet pip \
    && /opt/venv/bin/python -m pip uninstall --yes --quiet pip
WORKDIR /srv
# Only what runs: the app, the migrations, and the scripts a founder runs
# against production (make_admin, refresh_embeddings). Tests, docs and the
# developer's .env never enter the image (.dockerignore).
COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app scripts ./scripts
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
# One process per container: rate limits and idempotency live in Valkey and
# jobs in DBOS, so more capacity is more containers, not more workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]

# --- embeddings: api plus the model, for the scheduled refresh ------------------
FROM build AS embeddings-build
COPY requirements-ml.txt /tmp/requirements-ml.txt
# The CPU index: the default torch wheel drags in about 1.4 GB of CUDA for
# a workload that never touches a GPU (requirements-ml.txt).
RUN /opt/venv/bin/pip install -r /tmp/requirements-ml.txt \
        --extra-index-url https://download.pytorch.org/whl/cpu
# The model at a fixed revision, fetched once at build time and never at run
# time. A new revision is a reviewed change, like any other dependency. It
# must equal MODEL_REVISION in app/modules/matching/embedder.py, which asks
# for this exact commit; offline, any other would not be found. A test
# (test_embedding_service.py) fails if the two differ.
ARG MODEL_REVISION=97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
ENV HF_HOME=/opt/hf
RUN /opt/venv/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3-Embedding-0.6B', revision='${MODEL_REVISION}')"

FROM api AS embeddings
USER root
COPY --from=embeddings-build /opt/venv /opt/venv
COPY --from=embeddings-build --chown=app:app /opt/hf /opt/hf
RUN /opt/venv/bin/python -m pip uninstall --yes --quiet pip
# Offline: a running task must never reach out to download anything.
ENV HF_HOME=/opt/hf \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
USER app
HEALTHCHECK NONE
CMD ["python", "scripts/refresh_embeddings.py"]
