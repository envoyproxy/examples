FROM jaegertracing/all-in-one@sha256:fd5697c37ba041a91cfca1d62621d32cdeb2041c0febc2f1579e5bac6f21e34b
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
