"""Integration tests for POST /api/v1/calls client_type parameter."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


# Note: These tests use TestClient for synchronous HTTP testing
# Full e2e tests with websockets would go in tests/e2e/


class TestCreateCallClientType:
    """Integration tests for client_type parameter in POST /calls."""
    
    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        return TestClient(app)
    
    def test_api_call_without_client_type_defaults_to_browser_webrtc(self, client):
        """Test API call without client_type defaults to browser_webrtc."""
        response = client.post("/api/v1/calls")
        
        assert response.status_code == 201
        data = response.json()
        assert "call_id" in data
        assert data["status"] == "created"
        
        # The session should be created with browser_webrtc client
        # (verified by successful creation - factory would fail for unsupported types)
    
    def test_api_call_with_explicit_browser_webrtc_succeeds(self, client):
        """Test API call with client_type='browser_webrtc' succeeds."""
        response = client.post("/api/v1/calls", json={"client_type": "browser_webrtc"})
        
        assert response.status_code == 201
        data = response.json()
        assert "call_id" in data
        assert data["status"] == "created"
    
    def test_api_call_with_voip_asterisk_returns_400(self, client):
        """Test API call with client_type='voip_asterisk' returns HTTP 400."""
        response = client.post("/api/v1/calls", json={"client_type": "voip_asterisk"})
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "voip_asterisk" in data["detail"].lower()
        assert "Supported types" in data["detail"] or "supported" in data["detail"].lower()
        assert "browser_webrtc" in data["detail"].lower()
    
    def test_api_call_with_invalid_client_type_format_returns_400(self, client):
        """Test API call with invalid client_type format returns HTTP 400."""
        test_cases = [
            "BROWSER_WEBRTC",  # Uppercase
            "browser_WebRTC",  # Mixed case
            "unknown_type",    # Unknown type
            "browser-webrtc",  # Wrong separator
            "",                # Empty string
        ]
        
        for invalid_type in test_cases:
            response = client.post("/api/v1/calls", json={"client_type": invalid_type})
            
            assert response.status_code == 400, f"Failed for client_type='{invalid_type}'"
            data = response.json()
            assert "detail" in data
            # Should mention it's invalid or unsupported
            assert "invalid" in data["detail"].lower() or "unsupported" in data["detail"].lower()
    
    def test_backward_compatibility_empty_request_body(self, client):
        """Test backward compatibility: empty request body still works."""
        # POST without any JSON body
        response = client.post("/api/v1/calls")
        
        assert response.status_code == 201
        data = response.json()
        assert "call_id" in data
        assert data["status"] == "created"
    
    def test_api_returns_supported_types_in_error_message(self, client):
        """Test error message includes list of supported types."""
        response = client.post("/api/v1/calls", json={"client_type": "unsupported_type"})
        
        assert response.status_code == 400
        data = response.json()
        error_message = data["detail"]
        
        # Should list supported types
        assert "browser_webrtc" in error_message.lower()
        # Should mention what types are supported
        assert "supported" in error_message.lower()
