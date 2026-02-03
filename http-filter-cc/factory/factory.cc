#include "envoy/registry/registry.h"

#include "source/extensions/filters/http/common/factory_base.h"

#include "api/http_filter.pb.h"
#include "api/http_filter.pb.validate.h"
#include "common/config.h"
#include "filter/filter.h"

namespace Envoy {
namespace Extensions {
namespace HttpFilters {
namespace Sample {

/**
 * Factory for the sample HTTP filter.
 * Uses DualFactoryBase to support both downstream and upstream filter chains.
 */
class FilterFactory : public Common::DualFactoryBase<sample::Decoder, sample::DecoderPerRoute> {
public:
  FilterFactory() : DualFactoryBase("sample") {}

  absl::StatusOr<Http::FilterFactoryCb>
  createFilterFactoryFromProtoTyped(const sample::Decoder& proto_config,
                                    const std::string& /*stats_prefix*/,
                                    DualInfo /*info*/,
                                    Server::Configuration::ServerFactoryContext& /*context*/) override {
    auto config = std::make_shared<FilterConfig>(proto_config);
    return [config](Http::FilterChainFactoryCallbacks& callbacks) -> void {
      callbacks.addStreamDecoderFilter(std::make_shared<Filter>(config));
    };
  }

  absl::StatusOr<Router::RouteSpecificFilterConfigConstSharedPtr>
  createRouteSpecificFilterConfigTyped(const sample::DecoderPerRoute& proto_config,
                                        Server::Configuration::ServerFactoryContext&,
                                        ProtobufMessage::ValidationVisitor&) override {
    return std::make_shared<PerRouteFilterConfig>(proto_config);
  }
};

// Type alias is required to avoid redefinition error when registering for both
// downstream and upstream filter chains
using UpstreamFilterFactory = FilterFactory;

REGISTER_FACTORY(FilterFactory, Server::Configuration::NamedHttpFilterConfigFactory);
REGISTER_FACTORY(UpstreamFilterFactory, Server::Configuration::UpstreamHttpFilterConfigFactory);

} // namespace Sample
} // namespace HttpFilters
} // namespace Extensions
} // namespace Envoy
