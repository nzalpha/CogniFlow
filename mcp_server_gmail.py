import base64
import json
import logging
import os
from email.message import EmailMessage
from typing import Any, Dict

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

logger = logging.getLogger("gmail_mcp_server")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Gmail MCP Server", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔐 Unified Google credentials (same as Sheets)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


# 🔁 Function to get a fresh access token each time
async def get_access_token() -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": GOOGLE_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code != 200:
            logger.error("Failed to get access token: %s", resp.text)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Google OAuth error: {resp.text}",
            )
        return resp.json()["access_token"]


# 📧 Send an email using Gmail API
async def send_email_via_gmail(to: str, subject: str, body: str) -> Dict[str, Any]:
    access_token = await get_access_token()

    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    payload = {"raw": raw_message}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(GMAIL_SEND_URL, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Gmail API error %s: %s", exc.response.status_code, exc.response.text)
            raise HTTPException(status_code=500, detail=f"Gmail API error: {exc.response.text}")
        except httpx.RequestError as exc:
            logger.error("Network error when contacting Gmail API: %s", exc)
            raise HTTPException(status_code=500, detail="Network error contacting Gmail API") from exc

    result = response.json()
    logger.info("📨 Email sent successfully to %s", to)
    return result


# 🚀 Endpoint to send an email
@app.post("/send_email")
async def send_email_endpoint(request: Request) -> JSONResponse:
    data = await request.json()

    to = data.get("to")
    subject = data.get("subject")
    body = data.get("body")

    if not all([to, subject, body]):
        raise HTTPException(status_code=400, detail="Fields 'to', 'subject', and 'body' are required.")

    result = await send_email_via_gmail(to, subject, body)
    message_id = result.get("id", "unknown")

    return JSONResponse({"ok": True, "id": message_id})


# 🩺 Health check
@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mcp_server_gmail:app", host="127.0.0.1", port=8082, log_level="info")
