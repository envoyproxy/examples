FROM jaegertracing/all-in-one:1.73.0@sha256:fe884668a2bf8d586b6fb7697d48a6a19a02f9e78a1eddf09c5b0f08c27d63b9
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
