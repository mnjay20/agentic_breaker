import pytest
from fastapi.testclient import TestClient
from auragrid.main import app
from auragrid.config import settings

client = TestClient(app)

def test_api_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "AuraGrid" in response.json()["system"]

def test_api_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "emergency_disconnect_active" in data
    assert "watchdog" in data

def test_telemetry_ingest():
    payload = {
        "timestamp": "2026-06-06T23:20:00Z",
        "active_city": "TestCity",
        "grid_frequency_hz": 49.98,
        "nodes": {
            "Node A": {
                "active_load_mw": 400.0,
                "max_capacity_mw": 800.0,
                "status": "NORMAL",
                "breaker_state": "CLOSED"
            },
            "Node B": {
                "active_load_mw": 300.0,
                "max_capacity_mw": 800.0,
                "status": "NORMAL",
                "breaker_state": "CLOSED"
            }
        },
        "cascade_risk_matrix": {
            "Node B": {
                "Node A": 78.5
            }
        }
    }
    
    response = client.post("/api/v1/telemetry/ingest", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "INGESTED"
    assert data["exposure_percentage"] == 78.5
    assert data["reasoning_triggered"] is True

def test_mitigate_unauthorized():
    payload = {
        "timestamp_utc": "2026-06-06T23:21:05Z",
        "execution_sequence": []
    }
    response = client.post("/api/v1/agent/mitigate", json=payload)
    assert response.status_code == 401  # missing auth header

def test_mitigate_authorized_success():
    # Ingest TestCity telemetry first to ensure in-memory state is clean
    test_telemetry_ingest()

    payload = {
        "timestamp_utc": "2026-06-06T23:21:05Z",
        "execution_sequence": [
            {
                "step": 1,
                "device_type": "LOAD_SHEDGER",
                "device_id": "LS_NODE_A",
                "target_state": "ACTIVE",
                "shed_limit_mw": 50.0
            }
        ]
    }
    
    headers = {"Authorization": f"Bearer {settings.agent_token}"}
    response = client.post("/api/v1/agent/mitigate", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMMANDS_DISPATCHED"
    assert "transaction_id" in data

def test_emergency_disconnect():
    headers = {"Authorization": f"Bearer {settings.agent_token}"}
    
    # Ingest TestCity telemetry first
    test_telemetry_ingest()

    # 1. Trigger disconnect
    resp = client.post("/api/v1/emergency/disconnect")
    assert resp.status_code == 200
    assert resp.json()["status"] == "DISCONNECTED"
    
    # 2. Verify health reports degraded/disconnected
    resp = client.get("/api/v1/health")
    assert resp.json()["emergency_disconnect_active"] is True
    
    # 3. Attempting mitigation should now fail with 403
    payload = {
        "timestamp_utc": "2026-06-06T23:21:05Z",
        "execution_sequence": []
    }
    resp = client.post("/api/v1/agent/mitigate", json=payload, headers=headers)
    assert resp.status_code == 403
    
    # 4. Reconnect
    resp = client.post("/api/v1/emergency/reconnect", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "RECONNECTED"
    
    # 5. Mitigation works again
    resp = client.post("/api/v1/agent/mitigate", json=payload, headers=headers)
    assert resp.status_code == 200

