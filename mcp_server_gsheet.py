import json
import logging
import os
from typing import Any, Dict, List
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

logger = logging.getLogger("gsheet_mcp_server")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Google Sheets MCP Server", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Unified credentials
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

SHEETS_BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"


# 🔐 Function: Exchange refresh token for a fresh access token
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


# 🔧 Build dynamic headers
async def build_headers() -> Dict[str, str]:
    access_token = await get_access_token()
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }


# 🧾 Create a new Google Sheet
async def create_google_sheet(title: str) -> Dict[str, Any]:
    headers = await build_headers()
    payload = {"properties": {"title": title}}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(SHEETS_BASE_URL, json=payload, headers=headers)
            response.raise_for_status()
        except Exception as exc:
            logger.exception("Error creating Google Sheet: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to create Google Sheet")

    result = response.json()
    logger.info("✅ Created Google Sheet: %s", result)
    return {
        "spreadsheetId": result["spreadsheetId"],
        "spreadsheetUrl": result["spreadsheetUrl"],
    }


# ✏️ Write data into Google Sheet
async def write_to_google_sheet(sheet_id: str, range_: str, values: List[List[str]]) -> Dict[str, Any]:
    headers = await build_headers()

    # ✅ Encode the range so `:` inside of A1:B2 doesn't conflict with the `:update` suffix
    encoded_range = quote(range_, safe="!$'()*+,-./@_~")

    # ✅ Build url without the stale ':update' suffix (Sheets API expects plain PUT on /values/{range})
    url = f"{SHEETS_BASE_URL}/{sheet_id}/values/{encoded_range}"

    # ✅ Query string parameter (required)
    params = {"valueInputOption": "RAW"}

    # ✅ Payload (no 'range' key)
    payload = {
        "majorDimension": "ROWS",
        "values": values
    }

    logger.info(f"📊 PUT {url}?valueInputOption=RAW")
    logger.info(f"📤 Payload: {json.dumps(payload, indent=2)}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.put(url, headers=headers, params=params, json=payload)
            text = response.text
            if response.status_code != 200:
                logger.error(f"❌ Google Sheets API error ({response.status_code}): {text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Google Sheets API error: {text}",
                )
            logger.info(f"✅ Successfully updated range: {range_}")
            return response.json()

        except httpx.RequestError as e:
            logger.exception(f"🔌 Connection error writing to Google Sheets: {e}")
            raise HTTPException(status_code=500, detail=f"Network error: {e}")
        except Exception as exc:
            logger.exception("💥 Unexpected error writing to Google Sheet")
            raise HTTPException(status_code=500, detail=f"Internal error: {exc}")




# 📡 FastAPI Endpoints

@app.post("/create_sheet")
async def create_sheet_endpoint(request: Request) -> JSONResponse:
    data = await request.json()
    title = data.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="Missing 'title'")
    result = await create_google_sheet(title)
    return JSONResponse({"ok": True, "sheetId": result["spreadsheetId"], "link": result["spreadsheetUrl"]})


@app.post("/write_data")
async def write_data_endpoint(request: Request) -> JSONResponse:
    data = await request.json()
    sheet_id = data.get("sheetId")
    range_ = data.get("range")
    values = data.get("values")

    if not all([sheet_id, range_, values]):
        raise HTTPException(status_code=400, detail="Missing one or more required fields")

    result = await write_to_google_sheet(sheet_id, range_, values)
    return JSONResponse({"ok": True, "updatedRange": result.get("updatedRange", "")})


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("mcp_server_gsheet:app", host="127.0.0.1", port=8083, log_level="info")
