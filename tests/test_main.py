# -*- coding: utf-8 -*-
"""
CIL Router test file
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root():
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "CIL Router"
    assert "current_provider_index" in data
    assert "total_providers" in data

def test_select_provider():
    """Test provider selection"""
    # Switch to provider 0
    response = client.post("/select", content="0")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["current_index"] == 0

def test_select_invalid_provider():
    """Test invalid provider selection"""
    # First check how many providers we have
    response = client.get("/")
    provider_count = response.json()["total_providers"]
    
    # Try to select an invalid provider (beyond available range)
    invalid_index = provider_count + 10
    response = client.post("/select", content=str(invalid_index))
    assert response.status_code == 400