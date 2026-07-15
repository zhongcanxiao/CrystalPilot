"""Deployment constants for the vendored EIC client (extracted from eic_client.py)."""

use_https_in_production = True
# default_eic_ssl_port = '443'
default_eic_ssl_port = "8443"

default_url_base_dev = "http://127.0.0.1:5000"

default_ping_fed_host_url = "https://extidp.ornl.gov/as/token.oauth2"
default_system_openssl_path = "/bin/openssl"

if use_https_in_production:
    default_verify_ssl = True
else:
    default_verify_ssl = False
