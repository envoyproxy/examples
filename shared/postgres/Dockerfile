FROM postgres:latest@sha256:099dbb13112c133b37463fd312d3134aabfd5b3db3846f2f336b2996a9566bec
COPY docker-healthcheck.sh /usr/local/bin/
HEALTHCHECK CMD ["docker-healthcheck.sh"]
