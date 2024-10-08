FROM jaegertracing/all-in-one@sha256:836e9b69c88afbedf7683ea7162e179de63b1f981662e83f5ebb68badadc710f
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
