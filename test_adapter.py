import json
import httpx
import pytest
from fastapi.testclient import TestClient

import main
from agentforce_client import AgentforceClient, AgentforceUpstreamError

web_client = TestClient(main.app)


def test_health():
    response = web_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_message_is_rejected():
    response = web_client.post("/sales-assistant", json={"message": "", "user_id": "demo"})
    assert response.status_code == 422


def test_mocked_endpoint(monkeypatch):
    async def fake_ask(self, text):
        assert text == "Get Clásica vs Get Smart"
        return "Respuesta del agente de prueba"
    monkeypatch.setenv("SF_CLIENT_ID", "fake")
    monkeypatch.setenv("SF_CLIENT_SECRET", "fake")
    monkeypatch.setenv("SF_INSTANCE_URL", "https://test.my.salesforce.com")
    monkeypatch.setenv("SF_AGENT_ID", "0XxTEST")
    monkeypatch.setattr(AgentforceClient, "ask", fake_ask)
    response = web_client.post("/sales-assistant", json={"message": "Get Clásica vs Get Smart", "user_id": "demo"})
    assert response.status_code == 200
    assert response.json() == {"user_id": "demo", "response": "Respuesta del agente de prueba"}


@pytest.mark.asyncio
async def test_agentforce_request_sequence(monkeypatch):
    calls = []
    async def fake_request(self, client, method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/services/oauth2/token"):
            return {"access_token": "fake-oauth-token", "api_instance_url": "https://api.salesforce.com"}
        if method == "POST" and url.endswith("/sessions"):
            return {"sessionId": "session-123"}
        if method == "POST" and url.endswith("/messages"):
            return {"messages": [{"type": "Inform", "message": "Hola desde Agentforce"}]}
        if method == "DELETE":
            return {}
        raise AssertionError("Unexpected request: " + url)

    monkeypatch.setattr(AgentforceClient, "_request", fake_request)
    obj = AgentforceClient("id", "secret", "https://test.my.salesforce.com", "0XxTEST")
    assert await obj.ask("Hola") == "Hola desde Agentforce"
    assert [x[0] for x in calls] == ["POST", "POST", "POST", "DELETE"]
    assert calls[1][2]["json"]["instanceConfig"]["endpoint"] == "https://test.my.salesforce.com/"
    assert calls[2][2]["json"]["message"]["sequenceId"] == 1
    assert calls[2][2]["json"]["message"]["text"] == "Hola"
    assert calls[3][2]["headers"]["x-session-end-reason"] == "UserRequest"


def test_no_credentials_leaked_on_upstream_error(monkeypatch):
    async def failing_ask(self, _):
        raise AgentforceUpstreamError("Salesforce OAuth failed (HTTP 401).")
    monkeypatch.setenv("SF_CLIENT_ID", "fake")
    monkeypatch.setenv("SF_CLIENT_SECRET", "DO-NOT-LEAK")
    monkeypatch.setenv("SF_INSTANCE_URL", "https://test.my.salesforce.com")
    monkeypatch.setenv("SF_AGENT_ID", "0XxTEST")
    monkeypatch.setattr(AgentforceClient, "ask", failing_ask)
    response = web_client.post("/sales-assistant", json={"message": "Hola", "user_id": "demo"})
    assert response.status_code == 502
    assert "DO-NOT-LEAK" not in response.text
