"""Salesforce OAuth -> Agentforce start session -> send message -> end session."""
import os
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

AGENT_API_PATH = "/einstein/ai-agent/v1"

class AgentforceUpstreamError(Exception):
    pass

@dataclass(frozen=True)
class AgentforceClient:
    client_id: str
    client_secret: str
    instance_url: str
    agent_id: str

    @classmethod
    def from_env(cls) -> "AgentforceClient":
        names = ("SF_CLIENT_ID", "SF_CLIENT_SECRET", "SF_INSTANCE_URL", "SF_AGENT_ID")
        missing = [n for n in names if not os.getenv(n)]
        if missing:
            raise ValueError("Missing configuration: " + ", ".join(missing))
        return cls(
            client_id=os.environ["SF_CLIENT_ID"],
            client_secret=os.environ["SF_CLIENT_SECRET"],
            instance_url=os.environ["SF_INSTANCE_URL"].rstrip("/"),
            agent_id=os.environ["SF_AGENT_ID"],
        )

    async def _request(self, client: httpx.AsyncClient, method: str,
                       url: str, *, phase: str, **kwargs) -> dict[str, Any]:
        try:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Expected a JSON object")
            return result
        except httpx.HTTPStatusError as exc:
            raise AgentforceUpstreamError(
                f"Salesforce {phase} failed (HTTP {exc.response.status_code})."
            ) from None
        except (httpx.RequestError, ValueError) as exc:
            raise AgentforceUpstreamError(
                f"Salesforce {phase} failed (connection or response error)."
            ) from None

    async def _authenticate(self, client: httpx.AsyncClient) -> tuple[str, str]:
        data = await self._request(
            client, "POST", f"{self.instance_url}/services/oauth2/token", phase="OAuth",
            data={"grant_type": "client_credentials",
                  "client_id": self.client_id, "client_secret": self.client_secret},
        )
        access_token = data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AgentforceUpstreamError("Salesforce OAuth did not return an access token.")
        api_host = data.get("api_instance_url") or "https://api.salesforce.com"
        if not isinstance(api_host, str) or not api_host.startswith("https://"):
            raise AgentforceUpstreamError("Salesforce OAuth returned an invalid API host.")
        return access_token, api_host.rstrip("/")

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        messages = data.get("messages", [])
        if not isinstance(messages, list):
            raise AgentforceUpstreamError("Agentforce returned unexpected messages format.")
        # Avoid returning intermediary messages; prefer the final Inform message.
        for message in reversed(messages):
            if not isinstance(message, dict):
                continue
            if message.get("type") != "Inform":
                continue
            text = message.get("message")
            if isinstance(text, str) and text.strip():
                return text.strip()
        raise AgentforceUpstreamError("Agentforce returned no final text response.")

    async def ask(self, prompt: str) -> str:
        # One request = one agent session in this minimal PoC.
        timeout = httpx.Timeout(125.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            token, host = await self._authenticate(client)
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            url = f"{host}{AGENT_API_PATH}/agents/{quote(self.agent_id, safe='')}/sessions"
            session = await self._request(
                client, "POST", url, phase="start session", headers=headers,
                json={
                    "externalSessionKey": str(uuid.uuid4()),
                    "instanceConfig": {"endpoint": self.instance_url + "/"},
                    "streamingCapabilities": {"chunkTypes": ["Text"]},
                    "bypassUser": True,
                },
            )
            session_id = session.get("sessionId")
            if not isinstance(session_id, str) or not session_id:
                raise AgentforceUpstreamError("Agentforce did not return sessionId.")
            base = f"{host}{AGENT_API_PATH}/sessions/{quote(session_id, safe='')}"
            try:
                response = await self._request(
                    client, "POST", base + "/messages", phase="send message", headers=headers,
                    json={"message": {"type": "Text", "sequenceId": 1, "text": prompt}},
                )
                return self._extract_text(response)
            finally:
                # Do not obscure a successful answer because of cleanup failure.
                try:
                    await self._request(
                        client, "DELETE", base, phase="end session",
                        headers={**headers, "x-session-end-reason": "UserRequest"},
                    )
                except AgentforceUpstreamError:
                    pass
