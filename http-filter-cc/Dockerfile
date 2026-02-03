FROM envoyproxy/envoy:dev

COPY bin/envoy /usr/local/bin/envoy
COPY envoy.yaml /etc/envoy/envoy.yaml
CMD ["/usr/local/bin/envoy", "-c", "/etc/envoy/envoy.yaml"]
