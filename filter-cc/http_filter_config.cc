#include <string>

#include "envoy/registry/registry.h"

#include "source/extensions/filters/http/common/factory_base.h"

#include "http_filter.pb.h"
#include "http_filter.pb.validate.h"
#include "http_filter.h"

namespace Envoy {
namespace Server {
namespace Configuration {

class HttpSampleDecoderFilterConfigFactory
    : public Extensions::HttpFilters::Common::UnifiedFactoryBase<sample::Decoder> {
public:
  HttpSampleDecoderFilterConfigFactory() : UnifiedFactoryBase("sample") {}

private:
  absl::StatusOr<Http::FilterFactoryCb>
  createHttpFilterFactoryFromProtoTyped(const sample::Decoder& proto_config,
                                        ServerFactoryContext&, ExtraFactoryContext&) override {
    Http::HttpSampleDecoderFilterConfigSharedPtr config =
        std::make_shared<Http::HttpSampleDecoderFilterConfig>(proto_config);

    return [config](Http::FilterChainFactoryCallbacks& callbacks) -> void {
      auto filter = new Http::HttpSampleDecoderFilter(config);
      callbacks.addStreamDecoderFilter(Http::StreamDecoderFilterSharedPtr{filter});
    };
  }
};

/**
 * Static registration for this sample filter. @see RegisterFactory.
 */
REGISTER_FACTORY(HttpSampleDecoderFilterConfigFactory, NamedHttpFilterConfigFactory);

} // namespace Configuration
} // namespace Server
} // namespace Envoy
