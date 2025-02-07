FROM jaegertracing/all-in-one:1.66.0@sha256:9864182b4e01350fcc64631bdba5f4085f87daae9d477a04c25d9cb362e787a9
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
