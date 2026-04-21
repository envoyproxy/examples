#pragma once

#include "source/extensions/filters/http/common/pass_through_filter.h"
#include "source/common/http/utility.h"

#include "common/config.h"

namespace Envoy {
namespace Extensions {
namespace HttpFilters {
namespace Sample {

/**
 * Sample HTTP decoder filter that adds a custom header to requests.
 */
class Filter : public Http::PassThroughDecoderFilter {
public:
  Filter(FilterConfigSharedPtr config);
  ~Filter() override;

  // Http::StreamDecoderFilter
  void onDestroy() override;
  Http::FilterHeadersStatus decodeHeaders(Http::RequestHeaderMap& headers, bool end_stream) override;
  Http::FilterDataStatus decodeData(Buffer::Instance& data, bool end_stream) override;
  void setDecoderFilterCallbacks(Http::StreamDecoderFilterCallbacks& callbacks) override;

private:
  const FilterConfigSharedPtr config_;
  Http::StreamDecoderFilterCallbacks* decoder_callbacks_{nullptr};
};

} // namespace Sample
} // namespace HttpFilters
} // namespace Extensions
} // namespace Envoy
