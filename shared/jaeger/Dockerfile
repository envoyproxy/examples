FROM jaegertracing/all-in-one:1.68.0@sha256:6279882637ae03e70f519965d2ba5ca84cb785f4baf4f0d7237e827a37c33a42
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
