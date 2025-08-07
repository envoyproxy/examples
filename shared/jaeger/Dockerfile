FROM jaegertracing/all-in-one:1.72.0@sha256:144b7028db6045b28b50c4728dd3bea14fa76ab024b64afeccec51c8cb1edd63
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
