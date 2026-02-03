#include "filter/filter.h"

namespace Envoy {
namespace Extensions {
namespace HttpFilters {
namespace Sample {

Filter::Filter(FilterConfigSharedPtr config) : config_(config) {}

Filter::~Filter() = default;

void Filter::onDestroy() {}

const Http::LowerCaseString Filter::headerKey() const {
  return Http::LowerCaseString(config_->key());
}

const std::string Filter::headerValue() const {
  return config_->val();
}

Http::FilterHeadersStatus Filter::decodeHeaders(Http::RequestHeaderMap& headers, bool) {
  headers.addCopy(headerKey(), headerValue());
  return Http::FilterHeadersStatus::Continue;
}

Http::FilterDataStatus Filter::decodeData(Buffer::Instance&, bool) {
  return Http::FilterDataStatus::Continue;
}

void Filter::setDecoderFilterCallbacks(Http::StreamDecoderFilterCallbacks& callbacks) {
  decoder_callbacks_ = &callbacks;
}

} // namespace Sample
} // namespace HttpFilters
} // namespace Extensions
} // namespace Envoy
