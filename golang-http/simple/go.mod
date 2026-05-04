module github.com/envoyproxy/envoy/examples/golang-http/simple

// the version should >= 1.18
go 1.24.6

toolchain go1.24.9

// NOTICE: these lines could be generated automatically by "go mod tidy"
require (
	github.com/cncf/xds/go v0.0.0-20251210132809-ee656c7534f5
	github.com/envoyproxy/envoy v1.38.0
	google.golang.org/protobuf v1.36.11
)

require (
	cel.dev/expr v0.24.0 // indirect
	github.com/envoyproxy/protoc-gen-validate v1.3.0 // indirect
	google.golang.org/genproto/googleapis/api v0.0.0-20251202230838-ff82c1b0f217 // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20251202230838-ff82c1b0f217 // indirect
)
