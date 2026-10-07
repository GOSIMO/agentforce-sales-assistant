# Agentforce Sales Assistant — FastAPI PoC

This is a small **HTTP adapter** for an existing Salesforce Agentforce agent. It does **not** recreate the Agent Router, Knowledge RAG, CRM tools or reasoning.

## Architecture

`Bruno → POST /sales-assistant → FastAPI → Salesforce OAuth → Agentforce start session → send message → final answer → JSON`

Every `POST /sales-assistant` creates a fresh Agentforce session and then closes it. `user_id` is an echoed caller identifier, **not an authenticated Salesforce identity**. The service is for a **local demo only**; do not expose this unprotected endpoint publicly.

## 1. Configure locally on Windows

Extract this zip, open PowerShell inside the `agentforce_sales_assistant` folder, and copy the example file:

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in these **four** values in the local `.env` file:

```text
SF_CLIENT_ID=<Consumer Key of your External Client App>
SF_CLIENT_SECRET=<Consumer Secret>
SF_INSTANCE_URL=https://YOUR_MY_DOMAIN.my.salesforce.com
SF_AGENT_ID=<BotDefinition Id of your active agent>
```

**Don't share `.env`, screenshots containing credentials, or the Salesforce OAuth response with a token.** `.env` is excluded from the zip's Git tracking and Docker builds.

## 2. Run on Windows with Python

Requires Python 3.11+:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs for interactive API documentation.

## 3. Test with Bruno

- Request: `POST http://127.0.0.1:8000/sales-assistant`
- Header: `Content-Type: application/json`
- Body: JSON

```json
{
  "message": "¿Cuál es la diferencia entre Get Clásica y Get Smart?",
  "user_id": "demo-user"
}
```

Expected shape:

```json
{
  "user_id": "demo-user",
  "response": "Respuesta proporcionada por tu agente Agentforce..."
}
```

You can also check `GET http://127.0.0.1:8000/health`.

## 4. Automated tests

```powershell
.\.venv\Scripts\python.exe -m pip install pytest-asyncio
.\.venv\Scripts\python.exe -m pytest -q
```

These tests use mocks and **do not** consume Salesforce credits or make live Salesforce calls. Running Bruno against the real Salesforce org is the separate integration test.

## 5. Docker (once Docker Desktop is installed and running)

```powershell
docker build -t agentforce-sales-poc .
docker run --rm -p 8000:8000 --env-file .env agentforce-sales-poc
```

Bruno uses the same `POST http://localhost:8000/sales-assistant` endpoint as above.

## Test evidence for your challenge

1. Screenshot showing Agentforce active and its three subagents in Agentforce Studio.
2. Preview with Getnet RAG answer and citations.
3. Preview with Sales Context and creation of a Salesforce Task.
4. Bruno: Salesforce OAuth, Start Session, Send Message responses (mask access tokens).
5. Bruno: one call to the FastAPI adapter and response JSON.
6. `pytest -q` results and `docker build` / `docker run` once Docker is available.

## Troubleshooting

- `500 Missing configuration`: check `.env` file names and values.
- `502 ... OAuth ... 401`: check the External Client App, scopes, Run As user and consumer credentials.
- `502 ... start session ... 404`: check agent active status, correct BotDefinition ID and My Domain, and token from the same org.
- `502 ... send message ...`: verify Salesforce permissions and agent tools; test the same prompt directly in Bruno against native Agent API.
- `Connection refused`: verify Uvicorn/Docker is running and listening on port 8000.

## Production hardening (not included in PoC)

Caller authentication and authorization, stable session persistence for multi-turn conversations, restricted CORS, rate limits, secret vault, structured tracing, retries, monitoring and a separate least-privileged integration user.
