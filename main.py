"""Minimal Salesforce Agentforce HTTP adapter. For local PoC use only."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from agentforce_client import AgentforceClient, AgentforceUpstreamError

load_dotenv()  # local .env; Docker can inject the same variables with --env-file

app = FastAPI(title="Agentforce Sales Assistant PoC", version="1.0.0")

class SalesRequest(BaseModel):
    message: str = Field(min_length=1, max_length=16000)
    user_id: str = Field(min_length=1, max_length=200)

class SalesResponse(BaseModel):
    user_id: str
    response: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/sales-assistant", response_model=SalesResponse)
async def sales_assistant(request: SalesRequest):
    try:
        client = AgentforceClient.from_env()
        reply = await client.ask(request.message)
        return SalesResponse(user_id=request.user_id, response=reply)
    except ValueError as exc:
        # Names of missing env vars, but never their values.
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except AgentforceUpstreamError as exc:
        # Do not return upstream payloads: they may contain sensitive data.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
