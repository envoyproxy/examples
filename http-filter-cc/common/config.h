#pragma once

#include <string>

#include "envoy/router/router.h"

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

/**
 * Per-route configuration for the sample HTTP filter.
 * Allows overriding the filter config on specific routes.
 */
class PerRouteFilterConfig : public Router::RouteSpecificFilterConfig {
public:
  PerRouteFilterConfig(const sample::DecoderPerRoute& proto_config);
  
  const std::string& key() const { return key_; }
  const std::string& val() const { return val_; }
  bool hasKey() const { return !key_.empty(); }
  bool hasVal() const { return !val_.empty(); }

private:
  const std::string key_;
  const std::string val_;
};

} // namespace Sample
} // namespace HttpFilters
} // namespace Extensions
} // namespace Envoy
