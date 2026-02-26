//! Envoy Dynamic Module: jq/jaq HTTP Body Transform Filter
//!
//! This module implements an HTTP filter that transforms request and/or response JSON bodies
//! using jq programs compiled with jaq-core.
//!
//! Configuration is a JSON object with optional fields:
//! - `request_program`: jq program string to transform the request body
//! - `response_program`: jq program string to transform the response body
//! - `max_body_bytes`: maximum body size to buffer (default: 1MB); larger bodies pass through

use envoy_proxy_dynamic_modules_rust_sdk::*;
use jaq_core::{load, Compiler, Ctx, Native, RcIter};
use jaq_json::Val;
use load::{Arena, File, Loader};
use serde::Deserialize;

declare_init_functions!(init, new_http_filter_config_fn);

fn init() -> bool {
    true
}

fn new_http_filter_config_fn<EC: EnvoyHttpFilterConfig, EHF: EnvoyHttpFilter>(
    _envoy_filter_config: &mut EC,
    _filter_name: &str,
    filter_config: &[u8],
) -> Option<Box<dyn HttpFilterConfig<EHF>>> {
    let config_str = std::str::from_utf8(filter_config).unwrap_or("");
    FilterConfig::new(config_str).map(|c| Box::new(c) as Box<dyn HttpFilterConfig<EHF>>)
}

/// Raw deserialized config from the Envoy filter config JSON.
#[derive(Deserialize)]
struct FilterConfigData {
    request_program: Option<String>,
    response_program: Option<String>,
    max_body_bytes: Option<usize>,
}

/// Compiled filter configuration, shared across all requests.
pub struct FilterConfig {
    request_filter: Option<jaq_core::Filter<Native<Val>>>,
    response_filter: Option<jaq_core::Filter<Native<Val>>>,
    max_body_bytes: usize,
}

const DEFAULT_MAX_BODY_BYTES: usize = 1024 * 1024; // 1MB

fn compile_jq(program_str: &str) -> Option<jaq_core::Filter<Native<Val>>> {
    let program = File {
        code: program_str,
        path: (),
    };
    let loader = Loader::new(jaq_std::defs().chain(jaq_json::defs()));
    let arena = Arena::default();
    let modules = match loader.load(&arena, program) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("[dynamic-modules-jq] jq parse error: {:?}", e);
            return None;
        }
    };
    match Compiler::default()
        .with_funs(jaq_std::funs().chain(jaq_json::funs()))
        .compile(modules)
    {
        Ok(f) => Some(f),
        Err(e) => {
            eprintln!("[dynamic-modules-jq] jq compile error: {:?}", e);
            None
        }
    }
}

fn run_jq(
    filter: &jaq_core::Filter<Native<Val>>,
    input: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let inputs = RcIter::new(core::iter::empty());
    let mut results = filter.run((Ctx::new([], &inputs), Val::from(input)));
    match results.next() {
        Some(Ok(v)) => Ok(serde_json::Value::from(v)),
        Some(Err(e)) => Err(format!("jq execution error: {:?}", e)),
        None => Err("jq filter produced no output".to_string()),
    }
}

impl FilterConfig {
    fn new(config_str: &str) -> Option<Self> {
        let data: FilterConfigData = match serde_json::from_str(config_str) {
            Ok(d) => d,
            Err(e) => {
                eprintln!("[dynamic-modules-jq] config parse error: {}", e);
                return None;
            }
        };

        let request_filter = match &data.request_program {
            Some(p) => match compile_jq(p) {
                Some(f) => Some(f),
                None => return None,
            },
            None => None,
        };

        let response_filter = match &data.response_program {
            Some(p) => match compile_jq(p) {
                Some(f) => Some(f),
                None => return None,
            },
            None => None,
        };

        Some(FilterConfig {
            request_filter,
            response_filter,
            max_body_bytes: data.max_body_bytes.unwrap_or(DEFAULT_MAX_BODY_BYTES),
        })
    }
}

impl<EHF: EnvoyHttpFilter> HttpFilterConfig<EHF> for FilterConfig {
    fn new_http_filter(&self, _envoy: &mut EHF) -> Box<dyn HttpFilter<EHF>> {
        Box::new(Filter {
            request_filter: self.request_filter.clone(),
            response_filter: self.response_filter.clone(),
            max_body_bytes: self.max_body_bytes,
        })
    }
}

/// Per-request filter state.
pub struct Filter {
    request_filter: Option<jaq_core::Filter<Native<Val>>>,
    response_filter: Option<jaq_core::Filter<Native<Val>>>,
    max_body_bytes: usize,
}

fn is_json_content_type(ct: &[u8]) -> bool {
    let ct = std::str::from_utf8(ct).unwrap_or("");
    ct.contains("application/json")
}

fn transform_jq(
    jq_filter: &jaq_core::Filter<Native<Val>>,
    body_bytes: &[u8],
) -> Result<Vec<u8>, String> {
    // Parse JSON
    let input: serde_json::Value =
        serde_json::from_slice(body_bytes).map_err(|e| format!("JSON parse error: {}", e))?;

    // Run jq filter
    let output = run_jq(jq_filter, input)?;

    // Serialize output
    serde_json::to_vec(&output).map_err(|e| format!("JSON serialize error: {}", e))
}

fn collect_body(body_data: Vec<EnvoyMutBuffer<'_>>) -> Vec<u8> {
    let mut body = Vec::new();
    for chunk in &body_data {
        body.extend_from_slice(chunk.as_slice());
    }
    body
}

impl<EHF: EnvoyHttpFilter> HttpFilter<EHF> for Filter {
    fn on_request_body(
        &mut self,
        envoy_filter: &mut EHF,
        end_of_stream: bool,
    ) -> abi::envoy_dynamic_module_type_on_http_filter_request_body_status {
        let jq_filter = match &self.request_filter {
            Some(f) => f,
            None => {
                return abi::envoy_dynamic_module_type_on_http_filter_request_body_status::Continue
            }
        };

        if !end_of_stream {
            return abi::envoy_dynamic_module_type_on_http_filter_request_body_status::StopIterationAndBuffer;
        }

        // Check Content-Type
        let is_json = envoy_filter
            .get_request_header_value("content-type")
            .map(|ct| is_json_content_type(ct.as_slice()))
            .unwrap_or(false);

        if !is_json {
            return abi::envoy_dynamic_module_type_on_http_filter_request_body_status::Continue;
        }

        // Check body size before reading
        let body_size = envoy_filter.get_buffered_request_body_size();
        if body_size > self.max_body_bytes {
            return abi::envoy_dynamic_module_type_on_http_filter_request_body_status::Continue;
        }

        // Collect body into owned bytes then drop the EnvoyMutBuffer borrows
        let body_bytes = {
            let body_data = match envoy_filter.get_buffered_request_body() {
                Some(d) => d,
                None => {
                    return abi::envoy_dynamic_module_type_on_http_filter_request_body_status::Continue
                }
            };
            collect_body(body_data)
        };

        let result = transform_jq(jq_filter, &body_bytes);
        match result {
            Ok(output_bytes) => {
                envoy_filter.drain_buffered_request_body(body_bytes.len());
                envoy_filter.append_buffered_request_body(&output_bytes);
                let new_len = output_bytes.len().to_string();
                envoy_filter.set_request_header("content-length", new_len.as_bytes());
            }
            Err(e) => {
                let msg = format!("jq transform error: {}", e);
                envoy_filter.send_response(500, vec![], Some(msg.as_bytes()), None);
                return abi::envoy_dynamic_module_type_on_http_filter_request_body_status::StopIterationNoBuffer;
            }
        }

        abi::envoy_dynamic_module_type_on_http_filter_request_body_status::Continue
    }

    fn on_response_body(
        &mut self,
        envoy_filter: &mut EHF,
        end_of_stream: bool,
    ) -> abi::envoy_dynamic_module_type_on_http_filter_response_body_status {
        let jq_filter = match &self.response_filter {
            Some(f) => f,
            None => {
                return abi::envoy_dynamic_module_type_on_http_filter_response_body_status::Continue
            }
        };

        if !end_of_stream {
            return abi::envoy_dynamic_module_type_on_http_filter_response_body_status::StopIterationAndBuffer;
        }

        // Check Content-Type
        let is_json = envoy_filter
            .get_response_header_value("content-type")
            .map(|ct| is_json_content_type(ct.as_slice()))
            .unwrap_or(false);

        if !is_json {
            return abi::envoy_dynamic_module_type_on_http_filter_response_body_status::Continue;
        }

        // Check body size before reading
        let body_size = envoy_filter.get_buffered_response_body_size();
        if body_size > self.max_body_bytes {
            return abi::envoy_dynamic_module_type_on_http_filter_response_body_status::Continue;
        }

        // Collect body into owned bytes then drop the EnvoyMutBuffer borrows
        let body_bytes = {
            let body_data = match envoy_filter.get_buffered_response_body() {
                Some(d) => d,
                None => {
                    return abi::envoy_dynamic_module_type_on_http_filter_response_body_status::Continue
                }
            };
            collect_body(body_data)
        };

        let result = transform_jq(jq_filter, &body_bytes);
        match result {
            Ok(output_bytes) => {
                envoy_filter.drain_buffered_response_body(body_bytes.len());
                envoy_filter.append_buffered_response_body(&output_bytes);
                let new_len = output_bytes.len().to_string();
                envoy_filter.set_response_header("content-length", new_len.as_bytes());
            }
            Err(e) => {
                let msg = format!("jq transform error: {}", e);
                envoy_filter.send_response(500, vec![], Some(msg.as_bytes()), None);
                return abi::envoy_dynamic_module_type_on_http_filter_response_body_status::StopIterationNoBuffer;
            }
        }

        abi::envoy_dynamic_module_type_on_http_filter_response_body_status::Continue
    }
}
