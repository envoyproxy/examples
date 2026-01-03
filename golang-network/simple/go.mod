module github.com/envoyproxy/examples/golang-network/simple

// the version should >= 1.18
go 1.24.0

toolchain go1.24.9

// NOTICE: these lines could be generated automatically by "go mod tidy"
require (
	github.com/cncf/xds/go v0.0.0-20251110193048-8bfbf64dc13e
	github.com/envoyproxy/envoy v1.36.3
	google.golang.org/protobuf v1.36.10
)

require (
	cel.dev/expr v0.24.0 // indirect
	github.com/envoyproxy/protoc-gen-validate v1.2.1 // indirect
	google.golang.org/genproto/googleapis/api v0.0.0-20240903143218-8af14fe29dc1 // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20240903143218-8af14fe29dc1 // indirect
)
