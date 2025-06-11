FROM jaegertracing/all-in-one:1.70.0@sha256:c73bec5e6220b91eeda2574ec6aabbb8232f531e6b0bd11819f53548eefa6424
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
