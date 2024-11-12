FROM postgres:latest@sha256:e49dd801ba4d7417bf4c5a3e40624a492f8a1c41d2992a45f888841ec3f3621c
COPY docker-healthcheck.sh /usr/local/bin/
HEALTHCHECK CMD ["docker-healthcheck.sh"]
