FROM jaegertracing/all-in-one@sha256:4fd2d70fa347d6a47e79fcb06b1c177e6079f92cba88b083153d56263082135e
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=60 \
    CMD wget -q --header='Content-Type:application/json' -O - http://localhost:14269/health | grep "Server available"
