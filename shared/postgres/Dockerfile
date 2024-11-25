FROM postgres:latest@sha256:994cc3113ce004ae73df11f0dbc5088cbe6bb0da1691dd7e6f55474202a4f211
COPY docker-healthcheck.sh /usr/local/bin/
HEALTHCHECK CMD ["docker-healthcheck.sh"]
