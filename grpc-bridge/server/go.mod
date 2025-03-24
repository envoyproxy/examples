module github.com/envoyproxy/envoy/examples/grpc-bridge/server

go 1.13
toolchain go1.24.1

require (
	github.com/golang/protobuf v1.5.4
	golang.org/x/net v0.37.0
	google.golang.org/grpc v1.71.0
)

require (
	golang.org/x/sys v0.31.0 // indirect
	golang.org/x/text v0.23.0 // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20250115164207-1a7da9e5054f // indirect
	google.golang.org/protobuf v1.36.4 // indirect
)
