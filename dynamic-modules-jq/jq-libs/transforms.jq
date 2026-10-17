# Example jq library demonstrating the import/include feature.
#
# Usage in envoy.yaml filter_config:
#   request_program: 'import "transforms" as t; . | t::sanitize'
#   response_program: 'import "transforms" as t; . | t::sanitize'

# Remove fields that should not leave the service boundary.
def sanitize: del(.internal_id, .debug_info, ._metadata);

# Reshape a user object to a public-facing representation.
def reshape: {id: .user_id, name: .display_name, email: .email};
