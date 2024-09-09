FROM postgres:latest@sha256:eaacb93233a75db84e23584ededdfb3e416a4b68a1815aa3b7cbb0e5d0fa3744
COPY docker-healthcheck.sh /usr/local/bin/
HEALTHCHECK CMD ["docker-healthcheck.sh"]
