FROM jaegertracing/all-in-one:1.65.0@sha256:12fa17a231abded2c3b5b715bd252a043678495c588cbe772173991fbdcdf7c8
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
