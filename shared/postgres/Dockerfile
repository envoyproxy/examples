FROM postgres:latest@sha256:59c554e6f26822fd489ebbdef431457db2debd0c5762b24f11f603db5b91dfcc
COPY docker-healthcheck.sh /usr/local/bin/
HEALTHCHECK CMD ["docker-healthcheck.sh"]
