FROM postgres:latest@sha256:0cf02e45421b780449f0bab6b4af7e5ab2c37d3ca729e284fcec1a18f3fa9354
COPY docker-healthcheck.sh /usr/local/bin/
HEALTHCHECK CMD ["docker-healthcheck.sh"]
