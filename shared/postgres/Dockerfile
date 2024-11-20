FROM postgres:latest@sha256:163763c8afd28cae69035ce84b12d8180179559c747c0701b3cad17818a0dbc5
COPY docker-healthcheck.sh /usr/local/bin/
HEALTHCHECK CMD ["docker-healthcheck.sh"]
