FROM postgres:latest@sha256:53108e06bdce361fcdcb1de7d91bb8695ffddc6e6560249c710b62ba95ff3216
COPY docker-healthcheck.sh /usr/local/bin/
HEALTHCHECK CMD ["docker-healthcheck.sh"]
