FROM postgres:latest@sha256:c62fdb7fd6f519ef425c54760894c74e8d0cb04fbf4f7d3d79aafd86bae24edd
COPY docker-healthcheck.sh /usr/local/bin/
HEALTHCHECK CMD ["docker-healthcheck.sh"]
