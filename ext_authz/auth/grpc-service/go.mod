module github.com/envoyproxy/envoy/examples/ext_authz/auth/grpc-service

go 1.21
toolchain go1.22.9

require (
	github.com/envoyproxy/go-control-plane v0.13.1
	github.com/golang/protobuf v1.5.4
	google.golang.org/genproto/googleapis/rpc v0.0.0-20240903143218-8af14fe29dc1
	google.golang.org/grpc v1.68.0
)

require (
	github.com/cncf/xds/go v0.0.0-20240905190251-b4127c9b8d78 // indirect
	github.com/envoyproxy/protoc-gen-validate v1.1.0 // indirect
	github.com/planetscale/vtprotobuf v0.6.1-0.20240319094008-0393e58bdf10 // indirect
	golang.org/x/net v0.29.0 // indirect
	golang.org/x/sys v0.25.0 // indirect
	golang.org/x/text v0.18.0 // indirect
	google.golang.org/protobuf v1.34.2 // indirect
)
