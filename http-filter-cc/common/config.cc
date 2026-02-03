#include "common/config.h"

namespace Envoy {
namespace Extensions {
namespace HttpFilters {
namespace Sample {

FilterConfig::FilterConfig(const sample::Decoder& proto_config)
    : key_(proto_config.key()), val_(proto_config.val()) {}

} // namespace Sample
} // namespace HttpFilters
} // namespace Extensions
} // namespace Envoy
