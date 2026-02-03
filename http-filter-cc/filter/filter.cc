#include "filter/filter.h"

namespace Envoy {
namespace Extensions {
namespace HttpFilters {
namespace Sample {

Filter::Filter(FilterConfigSharedPtr config) : config_(config) {}

Filter::~Filter() = default;

void Filter::onDestroy() {}

void Filter::setDecoderFilterCallbacks(Http::StreamDecoderFilterCallbacks& callbacks) {
  decoder_callbacks_ = &callbacks;
  Http::PassThroughDecoderFilter::setDecoderFilterCallbacks(callbacks);
}

Http::FilterHeadersStatus Filter::decodeHeaders(Http::RequestHeaderMap& headers, bool) {
  std::string key = config_->key();
  std::string val = config_->val();
  
  // Check for per-route configuration override
  const auto* per_route_config = 
      Http::Utility::resolveMostSpecificPerFilterConfig<PerRouteFilterConfig>(decoder_callbacks_);
  
  if (per_route_config != nullptr) {
    if (per_route_config->hasKey()) {
      key = per_route_config->key();
    }
    if (per_route_config->hasVal()) {
      val = per_route_config->val();
    }
  }
  
  headers.addCopy(Http::LowerCaseString(key), val);
  return Http::FilterHeadersStatus::Continue;
}

Http::FilterDataStatus Filter::decodeData(Buffer::Instance&, bool) {
  return Http::FilterDataStatus::Continue;
}

} // namespace Sample
} // namespace HttpFilters
} // namespace Extensions
} // namespace Envoy
