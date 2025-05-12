FROM jaegertracing/all-in-one:1.69.0@sha256:82505210a99b18f587c94f40120c2e13ef3a6ac3095eebdb9e9cba9bf5839efd
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
