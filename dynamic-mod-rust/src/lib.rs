use envoy_proxy_dynamic_modules_rust_sdk::*;
use serde::Deserialize;

// This declares the entry points of the dynamic module:
//
// * `init` is called once when the module is loaded by Envoy.
// * `new_http_filter_config_fn` is called for each `DynamicModuleFilter`
//   configuration that references this module.
declare_init_functions!(init, new_http_filter_config_fn);

/// This implements the [`envoy_proxy_dynamic_modules_rust_sdk::ProgramInitFunction`], called
/// exactly once when the module is loaded. Returning `false` causes Envoy to reject the module.
fn init() -> bool {
    true
}

/// This implements the [`envoy_proxy_dynamic_modules_rust_sdk::NewHttpFilterConfigFunction`],
/// called with the `filter_name` and `filter_config` of each `DynamicModuleFilter` that
/// references this module. Returning `None` causes Envoy to reject the configuration.
fn new_http_filter_config_fn<EC: EnvoyHttpFilterConfig, EHF: EnvoyHttpFilter>(
    _envoy_filter_config: &mut EC,
    filter_name: &str,
    filter_config: &[u8],
) -> Option<Box<dyn HttpFilterConfig<EHF>>> {
    match filter_name {
        "response_mutation" => FilterConfig::new(filter_config)
            .map(|config| Box::new(config) as Box<dyn HttpFilterConfig<EHF>>),
        _ => {
            envoy_log_error!("unknown filter name: {filter_name}");
            None
        }
    }
}

/// This implements the [`envoy_proxy_dynamic_modules_rust_sdk::HttpFilterConfig`] trait, and is
/// deserialized from the JSON representation of the `filter_config` field in the Envoy
/// configuration.
#[derive(Deserialize)]
struct FilterConfig {
    response_header_name: String,
    response_header_value: String,
    response_body_suffix: String,
}

impl FilterConfig {
    fn new(filter_config: &[u8]) -> Option<Self> {
        serde_json::from_slice(filter_config)
            .map_err(|err| envoy_log_error!("error parsing filter config: {err}"))
            .ok()
    }
}

impl<EHF: EnvoyHttpFilter> HttpFilterConfig<EHF> for FilterConfig {
    /// This is called for each new HTTP stream to create the per-stream filter.
    fn new_http_filter(&self, _envoy: &mut EHF) -> Box<dyn HttpFilter<EHF>> {
        Box::new(Filter {
            response_header_name: self.response_header_name.clone(),
            response_header_value: self.response_header_value.clone(),
            response_body_suffix: self.response_body_suffix.clone(),
        })
    }
}

/// This implements the [`envoy_proxy_dynamic_modules_rust_sdk::HttpFilter`] trait, adding a
/// header to the response and appending some text to the response body.
struct Filter {
    response_header_name: String,
    response_header_value: String,
    response_body_suffix: String,
}

impl<EHF: EnvoyHttpFilter> HttpFilter<EHF> for Filter {
    fn on_response_headers(
        &self,
        envoy_filter: &mut EHF,
        _end_of_stream: bool,
    ) -> abi::envoy_dynamic_module_type_on_http_filter_response_headers_status {
        // The body is modified in `on_response_body`, so the content-length header is
        // removed to avoid a mismatch with the mutated body.
        envoy_filter.remove_response_header("content-length");
        envoy_filter.set_response_header(
            &self.response_header_name,
            self.response_header_value.as_bytes(),
        );
        abi::envoy_dynamic_module_type_on_http_filter_response_headers_status::Continue
    }

    fn on_response_body(
        &self,
        envoy_filter: &mut EHF,
        end_of_stream: bool,
    ) -> abi::envoy_dynamic_module_type_on_http_filter_response_body_status {
        if end_of_stream {
            envoy_filter.append_received_response_body(self.response_body_suffix.as_bytes());
        }
        abi::envoy_dynamic_module_type_on_http_filter_response_body_status::Continue
    }
}
