FROM postgres:latest@sha256:fe4dbda1be91f4297f8037728ccb184568dbb201ea389fe915b965af1c5e87c0
COPY docker-healthcheck.sh /usr/local/bin/
HEALTHCHECK CMD ["docker-healthcheck.sh"]
