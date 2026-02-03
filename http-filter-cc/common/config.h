#pragma once

#include <string>

#include "api/http_filter.pb.h"

namespace Envoy {
namespace Extensions {
namespace HttpFilters {
namespace Sample {

/**
 * Configuration for the sample HTTP filter.
 * Holds the parsed proto config values.
 */
class FilterConfig {
public:
  FilterConfig(const sample::Decoder& proto_config);

  const std::string& key() const { return key_; }
  const std::string& val() const { return val_; }

private:
  const std::string key_;
  const std::string val_;
};

using FilterConfigSharedPtr = std::shared_ptr<FilterConfig>;

} // namespace Sample
} // namespace HttpFilters
} // namespace Extensions
} // namespace Envoy
