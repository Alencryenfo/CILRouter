# -*- coding: utf-8 -*-
"""
pytest configuration file
"""

import pytest
import os

@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Setup test environment"""
    # Set test environment variables
    os.environ["PROVIDER_0_BASE_URL"] = "https://api.test.com"
    os.environ["PROVIDER_0_API_KEY"] = "test-key-1"
    os.environ["PROVIDER_1_BASE_URL"] = "https://api.test2.com"
    os.environ["PROVIDER_1_API_KEY"] = "test-key-2"
    os.environ["CURRENT_PROVIDER_INDEX"] = "0"

@pytest.fixture(autouse=True)
def reload_config():
    """Reload configuration before each test"""
    try:
        import config.config as config
        config.providers = config.load_providers_from_env()
        config.current_provider_index = int(os.getenv('CURRENT_PROVIDER_INDEX', '0'))
    except ImportError:
        pass