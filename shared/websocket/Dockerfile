FROM debian:bookworm-slim@sha256:d365f4920711a9074c4bcd178e8f457ee59250426441ab2a5f8106ed8fe948eb AS websocket-base
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get -qq update \
    && apt-get -qq install --no-install-recommends -y ca-certificates musl wget
RUN wget -qO /usr/local/bin/websocat https://github.com/vi/websocat/releases/download/v1.11.0/websocat.x86_64-unknown-linux-musl \
    && echo 'dc5524b9f03a344b88a12c859fb02f8bb56b3373dbc43a6e0c45a2ab52b853d7 /usr/local/bin/websocat' | sha256sum -c - \
    && chmod +x /usr/local/bin/websocat
ENTRYPOINT ["websocat"]


FROM websocket-base AS websocket-client
ENV DEBIAN_FRONTEND=noninteractive
ADD interact.sh /interact.sh
RUN chmod +x /interact.sh
RUN echo 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/80-retries
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get -qq update \
    && apt-get -qq install --no-install-recommends -y expect
ENTRYPOINT ["/interact.sh"]


FROM websocket-base
