FROM node:26.11-bookworm-slim@sha256:86f07bc9c5dce4578cf37e5a418b7bfc7f817cda25cde66e2b66e95ed86c4567 AS node-base


FROM node-base AS node-http-auth
ARG NODE_APP=.
ARG NODE_APP_NAME=http-service/server
# Add an env to save ARG
ENV NODE_APP_PATH "/app/${NODE_APP_NAME}"
COPY "$NODE_APP" /app
# Dont use exec form to interpolate correctly
CMD node $NODE_APP_PATH


FROM scratch AS app-deps-src


FROM node-base AS yarn
ARG SERVICE_PORT=3000
ENV DEBIAN_FRONTEND=noninteractive \
    SERVICE_PORT=$SERVICE_PORT
COPY --chmod=755 ./scripts/entrypoint.sh /entrypoint.sh
COPY --chmod=755 ./scripts/build.sh /usr/local/bin/build.sh
COPY --chmod=755 ./scripts/dev.sh /usr/local/bin/dev.sh
COPY --chmod=644 ./routes.jq /usr/local/share/routes.jq
RUN echo 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/80-retries
RUN apt-get update \
    && apt-get -qq install -y --no-install-recommends curl gosu jq yq
# Dependencies are installed at build time, outside the bind-mounted /workspace.
# Supply package.json and yarn.lock with `additional_contexts: {app-deps-src: <path>}`
WORKDIR /opt/app
COPY --from=app-deps-src package.json yarn.lock ./
RUN yarn install --frozen-lockfile --non-interactive \
    && chmod -R a+rX /opt/app \
    && yarn cache clean
WORKDIR /
ENTRYPOINT ["/entrypoint.sh"]
CMD ["dev.sh"]
HEALTHCHECK \
    --interval=1s \
    --timeout=2s \
    --start-period=5s \
    --retries=30 \
    CMD curl -sf "http://localhost:${SERVICE_PORT}/" > /dev/null


FROM yarn AS yarn-routed
COPY --chmod=755 ./scripts/build-routed.sh /usr/local/bin/build.sh
