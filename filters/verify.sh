

if [[ ! -e envoy ]]; then
    git clone https://github.com/envoyproxy/envoy
fi

echo FILTER_DEV > SOURCE_VERSION

mkdir -p bazel
cp -a envoy/bazel/get_workspace_status bazel/
cp -a envoy/bazel/platform_mappings bazel/
cp -a envoy/bazel/protoc bazel/
cp -f envoy/.bazelrc .
cp -f envoy/.bazelversion .

docker compose -f docker-compose-filters.yaml up --build --quiet-pull --remove-orphans filter_example_compile
