FROM jaegertracing/all-in-one:1.67.0@sha256:34e3d18e0f2eeb9abd9bb53d0dc7abaf2a5b1c884fdca575093af3126811a9d3
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
