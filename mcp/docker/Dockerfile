# The image of the Python services of docker-compose.yaml and rest_backend/docker-compose.yaml:
# Python, and the official MCP Python SDK at the version that the suite is pinned to, with every
# dependency pinned by hash. The test's sources are not in the image: the compose files mount them,
# read-only, at /e2e.

# python:3.13-slim, pinned to its multi-architecture index digest.
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes --requirement /tmp/requirements.txt \
    && rm /tmp/requirements.txt

WORKDIR /e2e
