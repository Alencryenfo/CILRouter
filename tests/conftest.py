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