FROM jaegertracing/all-in-one@sha256:85f1eb56e8ac24e53c031c6bcf7cdf6bff1dc4885b69e54605b932022054b612
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
