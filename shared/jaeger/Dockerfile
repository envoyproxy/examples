FROM jaegertracing/all-in-one:1.74.0@sha256:c87fc1d9b22766284168abb2ac57ac2160dfc26484e4f965ff2dcc6b849b263a
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
