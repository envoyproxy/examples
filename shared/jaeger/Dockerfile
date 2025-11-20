FROM jaegertracing/all-in-one:1.75.0@sha256:e493bff54e457ba5827f82418d744a322165cd5d46146607fb76489bfb2a8885
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
