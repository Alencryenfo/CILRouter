# -*- coding: utf-8 -*-
"""
配置模块
"""

from . import config

get_current_provider_endpoint = config.get_current_provider_endpoint
get_current_provider_index = config.get_current_provider_index
get_log_level = config.get_log_level
is_console_log_enabled = config.is_console_log_enabled
is_axiom_enabled = config.is_axiom_enabled
get_axiom_endpoint = config.get_axiom_endpoint
get_axiom_headers = config.get_axiom_headers
get_axiom_query_params = config.get_axiom_query_params
get_axiom_timeout = config.get_axiom_timeout
get_axiom_retry_config = config.get_axiom_retry_config
set_provider_index = config.set_provider_index
get_provider_info = config.get_provider_info
get_all_providers_info = config.get_all_providers_info
get_server_config = config.get_server_config
get_request_config = config.get_request_config
get_rate_limit_config = config.get_rate_limit_config
reload_config = config.reload_config


def __getattr__(name: str):
    if name in {"PROVIDERS", "CURRENT_PROVIDER_INDEX", "AXIOM_ENDPOINT"}:
        return getattr(config, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "config",
    "PROVIDERS",
    "CURRENT_PROVIDER_INDEX",
    "AXIOM_ENDPOINT",
    "get_current_provider_endpoint",
    "get_current_provider_index",
    "get_log_level",
    "is_console_log_enabled",
    "is_axiom_enabled",
    "get_axiom_endpoint",
    "get_axiom_headers",
    "get_axiom_query_params",
    "get_axiom_timeout",
    "get_axiom_retry_config",
    "set_provider_index",
    "get_provider_info",
    "get_all_providers_info",
    "get_server_config",
    "get_request_config",
    "get_rate_limit_config",
    "reload_config",
]
